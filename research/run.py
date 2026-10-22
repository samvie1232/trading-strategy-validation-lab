"""
Motor de investigación: corre las 3 familias con walk-forward + Monte Carlo + stress de costos
y escribe output/report.md con el veredicto APRUEBA / NO APRUEBA de cada una.

Uso:  python run.py
"""
from __future__ import annotations

import sys
import time
from collections import Counter

import numpy as np
import pandas as pd

import config as C
import metrics as M
from data import available_symbols, data_quality, load_bars, load_specs
from engine import approve, combine, monte_carlo, walk_forward
from strategies import param_label, run_asian_breakout, run_intraday_mom, run_trend

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError:  # los gráficos son opcionales
    plt = None


FAMILIES = [
    ("Tendencia multi-mercado (D1)", "trend", C.TREND, run_trend),
    ("Momentum intradía índices EE.UU. (M30)", "intraday_mom", C.INTRADAY_MOM, run_intraday_mom),
    ("Ruptura del rango asiático (M30)", "asian_breakout", C.ASIAN_BREAKOUT, run_asian_breakout),
]


def pct(x: float) -> str:
    return "n/d" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.1%}"


def md_table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(str(c) for c in cols) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
    for _, row in df.iterrows():
        lines.append("| " + " | ".join(str(v) for v in row.values) + " |")
    return "\n".join(lines)


def run_family(title: str, key: str, cfg: dict, fn, specs: pd.DataFrame, report: list[str]) -> dict | None:
    tf = cfg["timeframe"]
    avail = available_symbols(C.DATA_DIR, tf)
    wanted = cfg["symbols"] or avail
    symbols = [s for s in wanted if s in avail]
    missing = [s for s in wanted if s not in avail]

    report.append(f"\n## {title}\n")
    if not symbols:
        report.append(f"Sin datos: no hay archivos `*_{tf}.csv` para {wanted}. "
                      "Revisa los nombres en `all_symbols.csv` y ajústalos en `config.py`.\n")
        print(f"  [{key}] sin datos, se omite")
        return None
    if missing:
        report.append(f"Símbolos sin datos (omitidos): {', '.join(missing)}\n")

    bars = {s: load_bars(C.DATA_DIR, s, tf, specs) for s in symbols}
    bars = {s: b for s, b in bars.items() if b is not None and len(b) > 200}
    dq = pd.DataFrame([{"símbolo": s, **data_quality(b, tf)} for s, b in bars.items()])
    report.append("**Datos usados**\n\n" + md_table(dq) + "\n")

    def build(cost_mult: float) -> dict:
        runs = {}
        for p in cfg["param_grid"]:
            per_sym = [fn(b, p, cfg, cost_mult) for b in bars.values()]
            runs[param_label(p)] = combine(per_sym)
        return runs

    t0 = time.time()
    runs = build(C.COST_MULTIPLIER)
    stress_runs = build(C.STRESS_COST_MULTIPLIER)
    gross_runs = build(0.0)  # diagnóstico: sin spread ni deslizamiento (el swap se mantiene)
    print(f"  [{key}] {len(bars)} símbolos x {len(cfg['param_grid'])} parámetros en {time.time() - t0:.1f}s")

    # Sensibilidad: periodo completo con cada parámetro
    sens = []
    for lab, r in runs.items():
        s = M.summary(r.daily, r.trades)
        sens.append({"parámetros": lab, "retorno anual": pct(s["annual_return"]), "Sharpe": f"{s['sharpe']:.2f}",
                     "caída máx.": pct(s["max_drawdown"]), "operaciones": s["trades"],
                     "factor beneficio": f"{s['profit_factor']:.2f}"})
    report.append("**Sensibilidad de parámetros (periodo completo, solo referencia)**\n\n"
                  "Si solo un parámetro funciona y sus vecinos no, es señal de sobreajuste.\n\n"
                  + md_table(pd.DataFrame(sens)) + "\n")

    wf = walk_forward(runs, C.WF_TRAIN_YEARS, C.WF_TEST_MONTHS)
    if wf is None or len(wf.oos_daily) == 0:
        report.append("Historial insuficiente para walk-forward "
                      f"(se necesitan más de {C.WF_TRAIN_YEARS} años).\n")
        return None

    # Stress: mismos parámetros elegidos en cada ventana, pero con el doble de costos
    wf_stress = walk_forward(stress_runs, C.WF_TRAIN_YEARS, C.WF_TEST_MONTHS, forced=wf.chosen)
    wf_gross = walk_forward(gross_runs, C.WF_TRAIN_YEARS, C.WF_TEST_MONTHS, forced=wf.chosen)
    stats = M.summary(wf.oos_daily, wf.oos_trades)
    is_ann = wf.is_annual_mean
    stats["wfe"] = stats["annual_return"] / is_ann if is_ann > 0 else np.nan
    stats["pct_positive_windows"] = float((wf.windows["test_return"] > 0).mean())
    stats["stress_sharpe"] = M.sharpe(wf_stress.oos_daily) if wf_stress is not None else np.nan
    stats.update(monte_carlo(wf.oos_daily, C.MC_SIMULATIONS, C.MC_BLOCK_DAYS, C.RANDOM_SEED))

    checks = approve(stats, C.APPROVAL)
    passed = all(ok for _, _, ok in checks)
    verdict = "APRUEBA" if passed else "NO APRUEBA"

    report.append(f"### Veredicto: **{verdict}**\n")
    if wf_gross is not None:
        g = M.summary(wf_gross.oos_daily, wf_gross.oos_trades)
        report.append(f"Diagnóstico (no cuenta para el veredicto): **sin spread ni deslizamiento** el resultado "
                      f"fuera de muestra sería Sharpe {g['sharpe']:.2f} y retorno anual {pct(g['annual_return'])}. "
                      "Si aquí es positivo y con costos negativo, la idea tiene algo pero los costos de XM se la comen.\n")
    report.append(md_table(pd.DataFrame(
        [{"criterio": n, "valor": v, "resultado": "OK" if ok else "FALLA"} for n, v, ok in checks])) + "\n")

    report.append("**Resultado fuera de muestra (walk-forward encadenado)**\n\n" + md_table(pd.DataFrame([{
        "periodo": f"{wf.oos_daily.index[0].date()} a {wf.oos_daily.index[-1].date()}",
        "retorno anual": pct(stats["annual_return"]),
        "volatilidad anual": pct(stats["annual_vol"]),
        "Sharpe": f"{stats['sharpe']:.2f}",
        "caída máx.": pct(stats["max_drawdown"]),
        "operaciones": stats["trades"],
        "% ganadoras": pct(stats["win_rate"]),
        "factor beneficio": f"{stats['profit_factor']:.2f}",
        "retorno anual IS (promedio)": pct(is_ann),
    }])) + "\n")

    if "mc_p95_drawdown" in stats:
        report.append("**Monte Carlo (" + f"{C.MC_SIMULATIONS}" + " caminos)**\n\n" + md_table(pd.DataFrame([{
            "prob. de terminar en pérdida": pct(stats["mc_prob_loss"]),
            "retorno total (peor 5%)": pct(stats["mc_p05_total_return"]),
            "retorno total (mediana)": pct(stats["mc_median_total_return"]),
            "caída máx. (mediana)": pct(stats["mc_median_drawdown"]),
            "caída máx. (peor 5%)": pct(stats["mc_p95_drawdown"]),
        }])) + "\n")

    chosen = Counter(wf.chosen).most_common()
    report.append("**Parámetros elegidos por ventana**: " +
                  "; ".join(f"{lab} ({n} veces)" for lab, n in chosen) + "\n")
    report.append("<details><summary>Detalle por ventana</summary>\n\n" + md_table(wf.windows) + "\n\n</details>\n")

    # Detalle por símbolo con el parámetro más elegido
    top_p = next(p for p in cfg["param_grid"] if param_label(p) == chosen[0][0])
    per_sym = []
    for s, b in bars.items():
        r = fn(b, top_p, cfg, C.COST_MULTIPLIER)
        st = M.summary(r.daily, r.trades)
        per_sym.append({"símbolo": s, "retorno anual": pct(st["annual_return"]), "Sharpe": f"{st['sharpe']:.2f}",
                        "caída máx.": pct(st["max_drawdown"]), "operaciones": st["trades"]})
    report.append(f"**Por símbolo (periodo completo, parámetro más elegido: {chosen[0][0]})**\n\n"
                  + md_table(pd.DataFrame(per_sym)) + "\n")

    # Archivos de salida
    wf.oos_daily.rename("oos_return").to_csv(C.OUT_DIR / f"{key}_oos_daily.csv")
    wf.windows.to_csv(C.OUT_DIR / f"{key}_windows.csv", index=False)
    if plt is not None:
        fig, ax = plt.subplots(1, 2, figsize=(13, 4.5))
        for lab, r in runs.items():
            ax[0].plot(M.equity_curve(r.daily), lw=1, label=lab)
        ax[0].set_title("Periodo completo por parámetro (referencia)")
        ax[0].legend(fontsize=6)
        ax[1].plot(M.equity_curve(wf.oos_daily), color="black", lw=1.5, label="Costos reales")
        if wf_stress is not None:
            ax[1].plot(M.equity_curve(wf_stress.oos_daily), color="red", lw=1, ls="--", label="Doble costo")
        ax[1].axhline(1.0, color="grey", lw=0.5)
        ax[1].set_title(f"Fuera de muestra (walk-forward) — {verdict}")
        ax[1].legend(fontsize=8)
        fig.suptitle(title)
        fig.tight_layout()
        img = f"{key}_equity.png"
        fig.savefig(C.OUT_DIR / img, dpi=110)
        plt.close(fig)
        report.append(f"![{title}]({img})\n")

    print(f"  [{key}] {verdict} | OOS Sharpe {stats['sharpe']:.2f} | operaciones {stats['trades']}")
    return {"family": title, "verdict": verdict, **stats}


def main() -> int:
    C.OUT_DIR.mkdir(exist_ok=True)
    if not C.DATA_DIR.exists() or not any(C.DATA_DIR.glob("*.csv")):
        print(f"No hay datos en {C.DATA_DIR}. Copia ahí los CSV exportados desde MT5 (ver README).")
        return 1
    specs = load_specs(C.DATA_DIR)
    report = ["# Informe de investigación\n",
              f"Generado: {pd.Timestamp.now():%Y-%m-%d %H:%M}. Costos: spread real x{C.COST_MULTIPLIER} "
              f"+ deslizamiento {C.SLIPPAGE_FRAC_OF_SPREAD:.0%} del spread; "
              f"{'swaps reales de XM' if C.USE_REAL_SWAPS else f'swap aprox. {C.FINANCING_ANNUAL:.0%} anual'}. "
              f"Walk-forward: entrenar {C.WF_TRAIN_YEARS:g} años, probar {C.WF_TEST_MONTHS} meses.\n"]

    results = []
    for title, key, cfg, fn in FAMILIES:
        if not cfg.get("enabled", True):
            continue
        print(f"> {title}")
        res = run_family(title, key, cfg, fn, specs, report)
        if res:
            results.append(res)

    if results:
        summary = pd.DataFrame([{
            "familia": r["family"], "veredicto": r["verdict"], "Sharpe OOS": f"{r['sharpe']:.2f}",
            "retorno anual OOS": pct(r["annual_return"]), "caída máx. OOS": pct(r["max_drawdown"]),
            "operaciones OOS": r["trades"]} for r in results])
        report.insert(2, "\n## Resumen\n\n" + md_table(summary) + "\n")

    (C.OUT_DIR / "report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"\nListo. Informe: {C.OUT_DIR / 'report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
