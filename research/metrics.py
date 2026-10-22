"""Métricas de rendimiento sobre series diarias de retorno (fracción del capital)."""
from __future__ import annotations

import numpy as np
import pandas as pd

DAYS_PER_YEAR = 252


def equity_curve(returns: pd.Series) -> pd.Series:
    return (1.0 + returns.fillna(0.0)).cumprod()


def max_drawdown(returns: pd.Series | np.ndarray) -> float:
    r = np.asarray(returns, dtype=float)
    if r.size == 0:
        return 0.0
    eq = np.cumprod(1.0 + np.nan_to_num(r))
    peak = np.maximum.accumulate(eq)
    return float(np.max(1.0 - eq / peak))


def annual_return(returns: pd.Series) -> float:
    r = returns.fillna(0.0)
    if len(r) == 0:
        return 0.0
    total = float(np.prod(1.0 + r.values))
    years = len(r) / DAYS_PER_YEAR
    if total <= 0 or years <= 0:
        return -1.0
    return total ** (1.0 / years) - 1.0


def sharpe(returns: pd.Series) -> float:
    r = returns.fillna(0.0)
    sd = r.std()
    if len(r) < 2 or sd == 0 or np.isnan(sd):
        return 0.0
    return float(r.mean() / sd * np.sqrt(DAYS_PER_YEAR))


def trade_stats(trade_pnl: pd.Series) -> dict:
    t = trade_pnl.dropna()
    if len(t) == 0:
        return {"trades": 0, "win_rate": 0.0, "profit_factor": 0.0, "avg_win": 0.0, "avg_loss": 0.0}
    wins = t[t > 0]
    losses = t[t < 0]
    pf = float(wins.sum() / -losses.sum()) if len(losses) and losses.sum() != 0 else float("inf")
    return {
        "trades": int(len(t)),
        "win_rate": float(len(wins) / len(t)),
        "profit_factor": pf,
        "avg_win": float(wins.mean()) if len(wins) else 0.0,
        "avg_loss": float(losses.mean()) if len(losses) else 0.0,
    }


def summary(returns: pd.Series, trade_pnl: pd.Series) -> dict:
    out = {
        "annual_return": annual_return(returns),
        "annual_vol": float(returns.fillna(0).std() * np.sqrt(DAYS_PER_YEAR)),
        "sharpe": sharpe(returns),
        "max_drawdown": max_drawdown(returns.values),
        "total_return": float(np.prod(1.0 + returns.fillna(0).values) - 1.0),
    }
    out.update(trade_stats(trade_pnl))
    return out
