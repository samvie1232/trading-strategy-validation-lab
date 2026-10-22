"""Walk-forward, Monte Carlo y criterios de aprobación."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

import metrics as M
from strategies import StratResult


def combine(results: list[StratResult]) -> StratResult:
    """Portafolio de igual peso entre símbolos."""
    results = [r for r in results if len(r.daily)]
    if not results:
        return StratResult(pd.Series(dtype=float), pd.Series(dtype=float))
    daily = pd.concat([r.daily for r in results], axis=1).fillna(0.0).mean(axis=1)
    n = len(results)
    trades = pd.concat([r.trades / n for r in results]).sort_index()
    return StratResult(daily.sort_index(), trades)


@dataclass
class WFResult:
    oos_daily: pd.Series
    oos_trades: pd.Series
    windows: pd.DataFrame
    is_annual_mean: float
    chosen: list = field(default_factory=list)


def walk_forward(runs: dict[str, StratResult], train_years: float, test_months: int,
                 forced: list[str] | None = None) -> WFResult | None:
    """En cada ventana elige el parámetro con mejor Sharpe en entrenamiento y lo aplica a la prueba.
    Con `forced` se reutilizan las elecciones de otra corrida (para el stress de costos)."""
    labels = list(runs)
    all_days = sorted(set().union(*[set(r.daily.index) for r in runs.values()]))
    if not all_days:
        return None
    start, end = pd.Timestamp(all_days[0]), pd.Timestamp(all_days[-1])
    test_start = start + pd.DateOffset(months=int(train_years * 12))
    if test_start >= end:
        return None

    oos_d, oos_t, rows, is_rets = [], [], [], []
    w = 0
    while test_start < end:
        test_end = min(test_start + pd.DateOffset(months=test_months), end + pd.Timedelta(days=1))
        train_start = test_start - pd.DateOffset(months=int(train_years * 12))

        best_label, best_sh = None, -np.inf
        for lab in labels:
            d = runs[lab].daily
            tr = d[(d.index >= train_start) & (d.index < test_start)]
            sh = M.sharpe(tr)
            if sh > best_sh:
                best_label, best_sh = lab, sh
        if forced is not None and w < len(forced):
            best_label = forced[w]
            d = runs[best_label].daily
            best_sh = M.sharpe(d[(d.index >= train_start) & (d.index < test_start)])
        w += 1

        d = runs[best_label].daily
        tr = d[(d.index >= train_start) & (d.index < test_start)]
        te = d[(d.index >= test_start) & (d.index < test_end)]
        t = runs[best_label].trades
        tt = t[(t.index >= test_start) & (t.index < test_end)]

        is_rets.append(M.annual_return(tr))
        oos_d.append(te)
        oos_t.append(tt)
        rows.append({
            "test_start": test_start.date(),
            "test_end": (test_end - pd.Timedelta(days=1)).date(),
            "chosen_params": best_label,
            "train_sharpe": round(best_sh, 2),
            "test_return": round(float(np.prod(1 + te.values) - 1), 4),
            "test_sharpe": round(M.sharpe(te), 2),
            "test_trades": len(tt),
        })
        test_start = test_end

    oos_daily = pd.concat(oos_d).sort_index()
    oos_trades = pd.concat(oos_t).sort_index() if oos_t else pd.Series(dtype=float)
    return WFResult(oos_daily, oos_trades, pd.DataFrame(rows), float(np.mean(is_rets)),
                    [r["chosen_params"] for r in rows])


def monte_carlo(daily: pd.Series, sims: int, block: int, seed: int) -> dict:
    """Bootstrap por bloques: reordena trozos de la curva para ver otros caminos posibles."""
    r = daily.fillna(0.0).values
    n = len(r)
    if n < block * 3:
        return {}
    rng = np.random.default_rng(seed)
    finals, dds = np.empty(sims), np.empty(sims)
    for s in range(sims):
        starts = rng.integers(0, n - block, size=n // block + 1)
        path = np.concatenate([r[i:i + block] for i in starts])[:n]
        finals[s] = np.prod(1 + path) - 1
        dds[s] = M.max_drawdown(path)
    return {
        "mc_p05_total_return": float(np.percentile(finals, 5)),
        "mc_median_total_return": float(np.median(finals)),
        "mc_prob_loss": float((finals < 0).mean()),
        "mc_median_drawdown": float(np.median(dds)),
        "mc_p95_drawdown": float(np.percentile(dds, 95)),
    }


def approve(stats: dict, crit: dict) -> list[tuple[str, str, bool]]:
    wfe = stats.get("wfe", np.nan)
    checks = [
        ("Operaciones fuera de muestra", f"{stats['trades']} (mín. {crit['min_trades_oos']})",
         stats["trades"] >= crit["min_trades_oos"]),
        ("Sharpe fuera de muestra", f"{stats['sharpe']:.2f} (mín. {crit['min_oos_sharpe']})",
         stats["sharpe"] >= crit["min_oos_sharpe"]),
        ("Eficiencia walk-forward", f"{wfe:.2f} (mín. {crit['min_wfe']})" if not np.isnan(wfe) else "n/d (IS ≤ 0)",
         (not np.isnan(wfe)) and wfe >= crit["min_wfe"]),
        ("Ventanas OOS positivas", f"{stats['pct_positive_windows']:.0%} (mín. {crit['min_pct_positive_windows']:.0%})",
         stats["pct_positive_windows"] >= crit["min_pct_positive_windows"]),
        ("Caída p95 Monte Carlo", f"{stats.get('mc_p95_drawdown', np.nan):.1%} (máx. {crit['max_mc_p95_drawdown']:.0%})",
         stats.get("mc_p95_drawdown", 1.0) <= crit["max_mc_p95_drawdown"]),
        ("Sharpe con doble costo", f"{stats.get('stress_sharpe', np.nan):.2f} (mín. {crit['min_stress_sharpe']})",
         stats.get("stress_sharpe", -1) >= crit["min_stress_sharpe"]),
    ]
    return checks
