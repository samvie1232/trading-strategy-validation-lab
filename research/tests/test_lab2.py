"""Lab v2: causality, cost monotonicity, Deflated Sharpe and controls on synthetic data."""
import numpy as np
import pandas as pd
import pytest

import config as C
import lab2 as X
from data import load_bars, load_specs, swap_fractions
from engine import combine

FAMS = ["H1", "H2", "H3", "H4", "H5"]


@pytest.fixture(scope="module")
def data(random_walk_data):
    specs = load_specs(random_walk_data)
    m30 = load_bars(random_walk_data, "GOLD", "M30", specs)
    return {
        "H1": load_bars(random_walk_data, "US500Cash", "D1", specs),
        "H2": m30, "H3": X.to_h1(m30), "H4": m30, "H5": m30,
        "H6": {"GOLD": load_bars(random_walk_data, "GOLD", "D1", specs),
               "SILVER": load_bars(random_walk_data, "SILVER", "D1", specs)},
    }


@pytest.mark.parametrize("fam", FAMS)
def test_truncating_the_future_does_not_change_the_past(data, fam):
    df = data[fam]
    cut = df.index[int(len(df) * 0.6)]
    limit = cut - pd.Timedelta(days=30)
    for p in X.GRID[fam]:
        a = X.FN[fam](df, p, 1.0).trades
        b = X.FN[fam](df[df.index <= cut], p, 1.0).trades
        a, b = a[a.index < limit], b[b.index < limit]
        assert len(a) == len(b) and np.allclose(a.values, b.values, atol=1e-12)


def test_pair_trade_truncation(data):
    g, s = data["H6"]["GOLD"], data["H6"]["SILVER"]
    cut = g.index[int(len(g) * 0.7)]
    limit = cut - pd.Timedelta(days=30)
    for p in X.GRID["H6"]:
        a = X.h6(g, s, p, 1.0).trades
        b = X.h6(g[g.index <= cut], s[s.index <= cut], p, 1.0).trades
        a, b = a[a.index < limit], b[b.index < limit]
        assert len(a) == len(b) and np.allclose(a.values, b.values, atol=1e-12)


@pytest.mark.parametrize("fam", FAMS)
def test_more_costs_never_help(data, fam):
    p = X.GRID[fam][0]
    totals = [X.FN[fam](data[fam], p, c).daily.sum() for c in (0.0, 1.0, 2.0)]
    assert totals[0] >= totals[1] >= totals[2]


def test_deflated_sharpe_penalizes_more_trials():
    r = pd.Series(np.random.default_rng(1).normal(0.0005, 0.01, 1500))
    assert X.dsr(r, 1e-3, n=1000) < X.dsr(r, 1e-3, n=10) < X.dsr(r, 0.0, n=10) + 1e-12


def test_constant_pct_swap_ignores_historical_price(monkeypatch):
    specs = pd.DataFrame({"point": [0.01], "tick_size": [0.01], "tick_value": [1.0], "swap_long": [-80.0],
                          "swap_short": [20.0], "swap_mode": ["SYMBOL_SWAP_MODE_POINTS"]}, index=["GOLD"])
    close = pd.Series([1000.0, 4000.0])
    monkeypatch.setattr(C, "SWAP_MODEL", "legacy_fixed")
    legacy, _ = swap_fractions("GOLD", close, specs)
    monkeypatch.setattr(C, "SWAP_MODEL", "constant_pct")
    constant, _ = swap_fractions("GOLD", close, specs)
    assert legacy.iloc[0] == pytest.approx(4 * legacy.iloc[1])
    assert constant.iloc[0] == pytest.approx(constant.iloc[1]) == pytest.approx(legacy.iloc[1])


@pytest.mark.parametrize("fam", ["H1", "H4"])
def test_shuffled_prices_have_no_positive_expectancy_after_costs(data, fam):
    df = X.shuffle(data[fam], 11)
    total = np.mean([X.FN[fam](df, p, 1.0).daily.sum() for p in X.GRID[fam]])
    gross = np.mean([X.FN[fam](df, p, 0.0).daily.sum() for p in X.GRID[fam]])
    assert total <= gross


def test_planted_mean_reversion_is_detected(data):
    df = X.shuffle(data["H1"], 3, phi=-0.3)
    st, *_ = X.evaluate("H1", {"US500Cash": df})
    assert st["sharpe"] > 0.5
