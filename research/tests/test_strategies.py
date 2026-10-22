"""Unit tests: no look-ahead bias, cost sensitivity and metric sanity."""
import numpy as np
import pandas as pd
import pytest

import config as C
import metrics as M
from data import load_bars, load_specs
from strategies import run_asian_breakout, run_intraday_mom, run_trend, trend_signal


@pytest.fixture(scope="module")
def bars(random_walk_data):
    specs = load_specs(random_walk_data)
    return {
        "D1": load_bars(random_walk_data, "GOLD", "D1", specs),
        "M30_gold": load_bars(random_walk_data, "GOLD", "M30", specs),
        "M30_us500": load_bars(random_walk_data, "US500Cash", "M30", specs),
    }


def _shock_future(df: pd.DataFrame, cut: pd.Timestamp) -> pd.DataFrame:
    """Return a copy where every bar after `cut` is replaced by garbage."""
    out = df.copy()
    mask = out.index > cut
    rng = np.random.default_rng(0)
    factor = rng.choice([0.2, 5.0], mask.sum())  # cambios extremos: cualquier fuga se nota
    for c in ["open", "high", "low", "close"]:
        out.loc[mask, c] = out.loc[mask, c] * factor
    out.loc[mask, "high"] = out.loc[mask, ["open", "high", "low", "close"]].max(axis=1)
    out.loc[mask, "low"] = out.loc[mask, ["open", "high", "low", "close"]].min(axis=1)
    return out


@pytest.mark.parametrize("params", C.TREND["param_grid"])
def test_trend_signal_has_no_lookahead(bars, params):
    """The signal for day k computed with data up to k must equal the one computed with the full history."""
    df = bars["D1"]
    full = trend_signal(df, params)
    for k in range(260, len(df), 4):
        only_past = trend_signal(df.iloc[: k + 1], params)
        assert only_past[-1] == full[k], f"look-ahead at {df.index[k].date()}"


def _assert_past_unchanged(fn, df, params, cfg, n_cuts=8):
    base = fn(df, params, cfg, 1.0).daily
    for frac in np.linspace(0.3, 0.9, n_cuts):
        cut = df.index[int(len(df) * frac)].normalize() - pd.Timedelta(days=1)
        shocked = fn(_shock_future(df, cut + pd.Timedelta(hours=23, minutes=59)), params, cfg, 1.0).daily
        past = base.index <= cut
        pd.testing.assert_series_equal(base[past], shocked.reindex(base.index)[past], check_names=False)


def test_trend_returns_have_no_lookahead(bars):
    _assert_past_unchanged(run_trend, bars["D1"], C.TREND["param_grid"][3], C.TREND)


def test_intraday_momentum_has_no_lookahead(bars):
    _assert_past_unchanged(run_intraday_mom, bars["M30_us500"], C.INTRADAY_MOM["param_grid"][0], C.INTRADAY_MOM)


def test_asian_breakout_has_no_lookahead(bars):
    _assert_past_unchanged(run_asian_breakout, bars["M30_gold"], C.ASIAN_BREAKOUT["param_grid"][0], C.ASIAN_BREAKOUT)


@pytest.mark.parametrize("fn,key,cfg", [
    (run_trend, "D1", C.TREND),
    (run_intraday_mom, "M30_us500", C.INTRADAY_MOM),
    (run_asian_breakout, "M30_gold", C.ASIAN_BREAKOUT),
])
def test_higher_costs_never_help(bars, fn, key, cfg):
    p = cfg["param_grid"][0]
    total = [M.summary(fn(bars[key], p, cfg, m).daily, pd.Series(dtype=float))["total_return"] for m in (0.0, 1.0, 2.0)]
    assert total[0] >= total[1] >= total[2]


def test_max_drawdown_known_value():
    # +10%, -50%, +20%  -> peak 1.10, trough 0.55 -> drawdown 50%
    assert M.max_drawdown(np.array([0.10, -0.50, 0.20])) == pytest.approx(0.50)
