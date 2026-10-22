"""Carga de los CSV exportados por ExportData.mq5."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def load_specs(data_dir: Path) -> pd.DataFrame:
    path = data_dir / "symbols_spec.csv"
    if not path.exists():
        return pd.DataFrame()
    specs = pd.read_csv(path, encoding="latin-1")
    return specs.set_index("symbol")


def available_symbols(data_dir: Path, timeframe: str) -> list[str]:
    suffix = f"_{timeframe}.csv"
    return sorted(p.name[: -len(suffix)] for p in data_dir.glob(f"*{suffix}"))


def load_bars(data_dir: Path, symbol: str, timeframe: str, specs: pd.DataFrame) -> pd.DataFrame | None:
    """Devuelve DataFrame indexado por fecha/hora con open, high, low, close, spread (en precio)."""
    path = data_dir / f"{symbol}_{timeframe}.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path, encoding="latin-1")
    df["time"] = pd.to_datetime(df["time"], format="%Y.%m.%d %H:%M")
    df = df.set_index("time").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    for c in ["open", "high", "low", "close"]:
        df[c] = df[c].astype(float)

    point = float(specs.loc[symbol, "point"]) if symbol in specs.index else np.nan
    spread_now = float(specs.loc[symbol, "spread_now_points"]) if symbol in specs.index else np.nan
    if np.isnan(point):
        # Sin especificaciones: estimar el punto a partir de los decimales del precio
        decimals = df["close"].astype(str).str.split(".").str[-1].str.len().max()
        point = 10.0 ** (-int(decimals))

    spread_pts = df["spread_points"].astype(float).replace(0, np.nan)
    if not np.isnan(spread_now) and spread_now > 0:
        spread_pts = spread_pts.fillna(spread_now)
    spread_pts = spread_pts.ffill().bfill()
    df["spread"] = spread_pts * point
    df = df.dropna(subset=["open", "high", "low", "close", "spread"])
    df = df[(df["close"] > 0) & (df["high"] >= df["low"])]
    fl, fs = swap_fractions(symbol, df["close"], specs)
    df["fin_long"], df["fin_short"] = fl, fs
    return df[["open", "high", "low", "close", "spread", "fin_long", "fin_short"]]


def swap_fractions(symbol: str, close: pd.Series, specs: pd.DataFrame):
    """Swap por noche como fracción del nocional (positivo = te pagan, negativo = te cobran).
    Usa el swap ACTUAL del símbolo para todo el historial (aproximación)."""
    nan = pd.Series(np.nan, index=close.index)
    if symbol not in specs.index:
        return nan, nan
    sp = specs.loc[symbol]
    mode = str(sp.get("swap_mode", ""))
    point, tick_size, tick_value = float(sp["point"]), float(sp["tick_size"]), float(sp["tick_value"])
    if tick_size <= 0 or tick_value <= 0:
        return nan, nan
    notional_per_lot = close / tick_size * tick_value          # en moneda de la cuenta
    out = []
    for sw in (float(sp["swap_long"]), float(sp["swap_short"])):
        if "DISABLED" in mode:
            out.append(pd.Series(0.0, index=close.index))
        elif "POINTS" in mode:
            out.append(sw * point / close)
        elif "INTEREST" in mode:
            out.append(pd.Series(sw / 100.0 / 360.0, index=close.index))
        elif "CURRENCY" in mode:                              # dinero por lote por noche
            out.append(sw / notional_per_lot)
        else:
            out.append(nan)
    return out[0], out[1]


def data_quality(df: pd.DataFrame, timeframe: str) -> dict:
    """Resumen simple de calidad para el reporte."""
    gaps = df.index.to_series().diff().dropna()
    expected = {"D1": pd.Timedelta(days=1), "H4": pd.Timedelta(hours=4), "M30": pd.Timedelta(minutes=30)}.get(timeframe)
    big_gaps = int((gaps > pd.Timedelta(days=4)).sum()) if expected is not None else 0
    rel_spread = (df["spread"] / df["close"]).median()
    return {
        "bars": len(df),
        "start": df.index[0].strftime("%Y-%m-%d"),
        "end": df.index[-1].strftime("%Y-%m-%d"),
        "gaps_over_4_days": big_gaps,
        "median_spread_bps": round(float(rel_spread) * 1e4, 2),
    }
