"""
Genera datos FALSOS (caminata aleatoria, sin ventaja) en el mismo formato que exporta MT5.
Sirve para comprobar que el motor corre antes de tener tus datos reales.

Uso:  python make_synthetic.py                 -> crea la carpeta data_synthetic/
      Windows (PowerShell):  $env:XM_DATA_DIR="data_synthetic"; $env:XM_OUT_DIR="output_synthetic"; python run.py
      Linux/Mac:             XM_DATA_DIR=data_synthetic XM_OUT_DIR=output_synthetic python run.py

Con datos de caminata aleatoria lo esperado es "NO APRUEBA" en todas las familias.
Si algo aprueba con datos aleatorios, el motor tiene un error.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent / "data_synthetic"

SYMBOLS = {
    # símbolo: (precio inicial, vol diaria, spread en puntos, punto)
    "GOLD": (1800.0, 0.010, 35, 0.01),
    "SILVER": (24.0, 0.018, 30, 0.001),
    "EURUSD": (1.10, 0.005, 16, 0.00001),
    "GBPUSD": (1.25, 0.006, 20, 0.00001),
    "USDJPY": (110.0, 0.006, 20, 0.001),
    "US500Cash": (3800.0, 0.011, 60, 0.01),
    "US100Cash": (12000.0, 0.014, 180, 0.01),
    "OILCash": (70.0, 0.022, 4, 0.01),
}


def bars_from_path(times: pd.DatetimeIndex, price0: float, vol_bar: float, rng, sub: int = 6, drift_series=None):
    n = len(times)
    steps = rng.normal(0, vol_bar / np.sqrt(sub), size=(n, sub))
    if drift_series is not None:
        steps += (drift_series / sub)[:, None]
    logp = np.log(price0) + np.cumsum(steps.ravel())
    logp = logp.reshape(n, sub)
    close = np.exp(logp[:, -1])
    open_ = np.r_[price0, close[:-1]]
    high = np.maximum(np.exp(logp.max(axis=1)), np.maximum(open_, close))
    low = np.minimum(np.exp(logp.min(axis=1)), np.minimum(open_, close))
    return open_, high, low, close


def write(sym, tf, times, o, h, l, c, spread_pts, point, rng, out=OUT):
    digits = int(round(-np.log10(point)))
    spr = np.maximum(1, rng.normal(spread_pts, spread_pts * 0.2, len(times))).round().astype(int)
    df = pd.DataFrame({
        "time": times.strftime("%Y.%m.%d %H:%M"),
        "open": np.round(o, digits), "high": np.round(h, digits),
        "low": np.round(l, digits), "close": np.round(c, digits),
        "tick_volume": rng.integers(100, 5000, len(times)), "spread_points": spr,
    })
    df.to_csv(out / f"{sym}_{tf}.csv", index=False)


def main(seed: int = 7, out: Path | None = None) -> Path:
    out = Path(out) if out else OUT
    rng = np.random.default_rng(seed)
    out.mkdir(parents=True, exist_ok=True)
    days = pd.bdate_range("2015-01-01", "2026-10-20")
    m30 = pd.date_range("2021-01-01", "2026-10-20 23:30", freq="30min")
    m30 = m30[m30.dayofweek < 5]
    spec_rows = []
    for sym, (p0, vol_d, spr, point) in SYMBOLS.items():
        o, h, l, c = bars_from_path(days, p0, vol_d, rng)
        write(sym, "D1", days, o, h, l, c, spr, point, rng, out)
        o, h, l, c = bars_from_path(m30, c[days < "2021-01-01"][-1], vol_d / np.sqrt(48), rng, sub=30)
        write(sym, "M30", m30, o, h, l, c, spr, point, rng, out)
        spec_rows.append({"symbol": sym, "digits": int(round(-np.log10(point))), "point": point,
                          "contract_size": 100, "tick_size": point, "tick_value": 1, "volume_min": 0.01,
                          "volume_step": 0.01, "currency_profit": "USD", "spread_now_points": spr,
                          "swap_long": 0, "swap_short": 0, "swap_mode": "SYMBOL_SWAP_MODE_POINTS",
                          "description": f"{sym} sintetico"})
    pd.DataFrame(spec_rows).to_csv(out / "symbols_spec.csv", index=False)
    print(f"Datos sintéticos en {out}")
    return out


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 7)
