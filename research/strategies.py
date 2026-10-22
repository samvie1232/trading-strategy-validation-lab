"""
Tres familias de estrategias. Todas son causales: la decisión en la vela t solo usa datos hasta t.

Cada función devuelve un StratResult:
  daily  -> retorno diario como fracción del capital (índice = fecha)
  trades -> resultado de cada operación como fracción del capital (índice = fecha de cierre)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from config import FINANCING_ANNUAL, SLIPPAGE_FRAC_OF_SPREAD, STOP_FILL_SLIPPAGE, USE_REAL_SWAPS


@dataclass
class StratResult:
    daily: pd.Series
    trades: pd.Series


def _hhmm(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def param_label(p: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in p.items())


# ======================================================================
# Familia 1: seguimiento de tendencia (velas diarias)
# ======================================================================
def trend_signal(df: pd.DataFrame, p: dict) -> np.ndarray:
    close, high, low = df["close"], df["high"], df["low"]
    t = p["type"]
    if t == "ema":
        fast = close.ewm(span=p["fast"], adjust=False).mean()
        slow = close.ewm(span=p["slow"], adjust=False).mean()
        sig = np.sign(fast - slow).to_numpy(copy=True)
        sig[: p["slow"]] = 0  # calentamiento
    elif t == "tsmom":
        sig = np.sign(close / close.shift(p["lookback"]) - 1.0).fillna(0).to_numpy(copy=True)
    elif t == "donchian":
        hh = high.rolling(p["entry"]).max().shift(1).values
        ll = low.rolling(p["entry"]).min().shift(1).values
        hx = high.rolling(p["exit"]).max().shift(1).values
        lx = low.rolling(p["exit"]).min().shift(1).values
        c = close.values
        sig = np.zeros(len(c))
        state = 0
        for i in range(len(c)):
            if np.isnan(hh[i]) or np.isnan(lx[i]):
                continue
            if state == 1 and c[i] < lx[i]:
                state = 0
            elif state == -1 and c[i] > hx[i]:
                state = 0
            if state == 0:
                if c[i] > hh[i]:
                    state = 1
                elif c[i] < ll[i]:
                    state = -1
            sig[i] = state
    else:
        raise ValueError(f"Tipo de tendencia desconocido: {t}")
    sig = np.nan_to_num(sig)
    if p.get("long_only"):
        sig = np.clip(sig, 0, 1)
    return sig


def run_trend(df: pd.DataFrame, p: dict, cfg: dict, cost_mult: float) -> StratResult:
    close = df["close"].values
    spread = df["spread"].values
    n = len(close)
    sig = trend_signal(df, p)

    daily_ret = pd.Series(close).pct_change()
    vol = daily_ret.ewm(span=cfg["vol_lookback"], min_periods=cfg["vol_lookback"]).std().values
    target_daily = cfg["target_vol_annual"] / np.sqrt(252)
    # Swap por vela: real de XM si está disponible; si no, costo fijo aproximado.
    # Con velas solo de lunes a viernes, cada vela carga 7/5 noches (incluye el triple swap).
    weekend = bool((df.index.dayofweek >= 5).any())
    nights = 1.0 if weekend else 7.0 / 5.0
    if USE_REAL_SWAPS and "fin_long" in df and df["fin_long"].notna().all():
        fin_l = df["fin_long"].values * nights
        fin_s = df["fin_short"].values * nights
    else:
        fin_l = fin_s = np.full(n, -FINANCING_ANNUAL / 252)
    cost_k = cost_mult * (1.0 + SLIPPAGE_FRAC_OF_SPREAD) / 2.0  # medio spread por cada lado

    rets = np.zeros(n)
    trade_dates, trade_pnls = [], []
    pos = 0.0
    acc = 0.0  # resultado acumulado de la operación abierta
    for t in range(1, n):
        fin = fin_l[t - 1] if pos > 0 else fin_s[t - 1]
        r = pos * (close[t] / close[t - 1] - 1.0) + abs(pos) * fin
        acc += r

        s = sig[t]
        target = pos
        if np.sign(pos) != s:
            if s == 0 or np.isnan(vol[t]) or vol[t] <= 0:
                target = 0.0
            else:
                target = s * min(target_daily / vol[t], cfg["max_leverage"])
        if target != pos:
            c = cost_k * spread[t] / close[t]
            if pos != 0:  # cerrar la operación actual
                exit_cost = abs(pos) * c
                r -= exit_cost
                acc -= exit_cost
                trade_dates.append(df.index[t])
                trade_pnls.append(acc)
                acc = 0.0
            if target != 0:  # abrir la nueva
                entry_cost = abs(target) * c
                r -= entry_cost
                acc = -entry_cost
        rets[t] = r
        pos = target

    idx = df.index.normalize()
    daily = pd.Series(rets, index=idx).groupby(level=0).sum()
    trades = pd.Series(trade_pnls, index=pd.DatetimeIndex(trade_dates).normalize(), dtype=float)
    return StratResult(daily, trades)


# ======================================================================
# Familia 2: momentum intradía (1ª media hora -> última media hora)
# ======================================================================
def run_intraday_mom(df: pd.DataFrame, p: dict, cfg: dict, cost_mult: float) -> StratResult:
    mins = df.index.hour * 60 + df.index.minute
    dates = df.index.normalize()
    fb, lb = _hhmm(cfg["first_bar"]), _hhmm(cfg["last_bar"])

    first = df[mins == fb].copy()
    first.index = dates[mins == fb]
    last = df[mins == lb].copy()
    last.index = dates[mins == lb]
    first = first[~first.index.duplicated()]
    last = last[~last.index.duplicated()]

    prev_close = last["close"].shift(1)
    common = first.index.intersection(last.index).intersection(prev_close.dropna().index)
    if len(common) < 50:
        return StratResult(pd.Series(dtype=float), pd.Series(dtype=float))

    f, l, pc = first.loc[common], last.loc[common], prev_close.loc[common]
    if p["from_prev_close"]:
        r1 = f["close"] / pc - 1.0
    else:
        r1 = f["close"] / f["open"] - 1.0
    r_last = l["close"] / l["open"] - 1.0

    vol = r_last.rolling(cfg["vol_lookback"], min_periods=20).std().shift(1)
    lev = (cfg["target_trade_vol"] / vol).clip(upper=cfg["max_leverage"]).fillna(0.0)
    sig = np.sign(r1).where(r1.abs() > p["threshold"], 0.0)
    cost = (l["spread"] / l["open"]) * cost_mult * (1.0 + SLIPPAGE_FRAC_OF_SPREAD)
    pnl = lev * (sig * r_last - cost * (sig != 0))
    pnl = pnl.fillna(0.0)
    trades = pnl[(sig != 0) & (lev > 0)]
    return StratResult(pnl, trades)


# ======================================================================
# Familia 3: ruptura del rango asiático
# ======================================================================
def run_asian_breakout(df: pd.DataFrame, p: dict, cfg: dict, cost_mult: float) -> StratResult:
    rs, re_, ee, ex = (_hhmm(cfg[k]) for k in ("range_start", "range_end", "entry_end", "exit_time"))
    o, h, l, c, spr = (df[k].values for k in ("open", "high", "low", "close", "spread"))
    mins = (df.index.hour * 60 + df.index.minute).values
    day_vals = df.index.normalize().values
    uniq, starts = np.unique(day_vals, return_index=True)
    ends = np.append(starts[1:], len(df))
    cost_k = cost_mult * (1.0 + SLIPPAGE_FRAC_OF_SPREAD)

    out_dates, out_pnl = [], []
    for d, a, b in zip(uniq, starts, ends):
        m = mins[a:b]
        rmask = (m >= rs) & (m < re_)
        if rmask.sum() < 4:
            continue
        rh, rl = h[a:b][rmask].max(), l[a:b][rmask].min()
        rng = rh - rl
        if rng <= 0:
            continue
        mid = (rh + rl) / 2.0

        direction, entry, stop, tp, cost, exit_px = 0, None, None, None, 0.0, None
        last_i = None
        for k in np.where(m >= re_)[0]:
            i = a + k
            last_i = i
            if entry is None:
                if m[k] >= ee:
                    break
                ss = STOP_FILL_SLIPPAGE * cost_mult * spr[i]  # la orden stop se llena peor que el nivel
                if h[i] > rh:  # si rompe ambos lados en la misma vela, se toma la compra y casi seguro sale por stop (supuesto conservador)
                    direction, entry = 1, max(o[i], rh) + ss
                    stop = rl if p["stop"] == "opposite" else mid
                elif l[i] < rl:
                    direction, entry = -1, min(o[i], rl) - ss
                    stop = rh if p["stop"] == "opposite" else mid
                else:
                    continue
                tp = entry + direction * p["tp_mult"] * rng
                cost = cost_k * spr[i]
                if (direction == 1 and l[i] <= stop) or (direction == -1 and h[i] >= stop):
                    exit_px = stop - direction * ss
                    break
                continue
            # Posición abierta
            if m[k] >= ex:
                exit_px = o[i]
                break
            ss = STOP_FILL_SLIPPAGE * cost_mult * spr[i]
            if direction == 1:
                if o[i] <= stop:
                    exit_px = o[i] - ss
                elif l[i] <= stop:
                    exit_px = stop - ss
                elif h[i] >= tp:
                    exit_px = o[i] if o[i] >= tp else tp
            else:
                if o[i] >= stop:
                    exit_px = o[i] + ss
                elif h[i] >= stop:
                    exit_px = stop + ss
                elif l[i] <= tp:
                    exit_px = o[i] if o[i] <= tp else tp
            if exit_px is not None:
                break
        if entry is None:
            continue
        if exit_px is None:
            exit_px = c[last_i] if last_i is not None else entry
        risk = abs(entry - stop)
        if risk <= 0:
            continue
        r_mult = (direction * (exit_px - entry) - cost) / risk
        out_dates.append(pd.Timestamp(d))
        out_pnl.append(cfg["risk_per_trade"] * r_mult)

    trades = pd.Series(out_pnl, index=pd.DatetimeIndex(out_dates), dtype=float)
    daily = trades.groupby(level=0).sum()
    # Días sin operación = 0, para que las métricas diarias sean comparables
    all_days = pd.DatetimeIndex(np.unique(day_vals))
    daily = daily.reindex(all_days, fill_value=0.0)
    return StratResult(daily, trades)
