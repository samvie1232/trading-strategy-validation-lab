"""H7 and H8: causality, cost monotonicity and calendar rules on synthetic data."""
import numpy as np
import pandas as pd
import pytest

import lab_funding as F
import lab_tom as T
from data import load_bars, load_specs


@pytest.fixture(scope="module")
def index_bars(random_walk_data):
    return load_bars(random_walk_data, "US500Cash", "D1", load_specs(random_walk_data))


@pytest.fixture(scope="module")
def carry():
    n = 1200
    days = pd.date_range("2020-01-01", periods=n, freq="D")
    rng = np.random.default_rng(3)
    spot = pd.Series(100*np.exp(np.cumsum(rng.normal(0, .03, n))), index=days)
    perp = spot*(1+rng.normal(0, .0003, n))
    ts = pd.date_range(days[0], periods=n*3, freq="8h")
    funding = pd.DataFrame({"timestamp": ts, "fundingRate": rng.normal(1e-4, 2e-4, len(ts))})
    return F.prepare(spot, perp, funding)


def test_month_turn_dates_use_the_calendar(index_bars):
    for a, b in T.windows_tom(index_bars, {"before": 1, "after": 3})[:20]:
        assert index_bars.index[a].to_period("M") != index_bars.index[b].to_period("M")
        assert (index_bars.index[a].to_period("M")+1) == index_bars.index[b].to_period("M")


@pytest.mark.parametrize("p", T.GRID)
def test_month_turn_is_causal_and_costs_never_help(index_bars, p):
    cut = index_bars.index[int(len(index_bars)*.6)]
    limit = cut-pd.Timedelta(days=20)
    a, b = T.run(index_bars, p).trades, T.run(index_bars[index_bars.index <= cut], p).trades
    a, b = a[a.index < limit], b[b.index < limit]
    assert len(a) == len(b) and np.allclose(a.values, b.values, atol=1e-12)
    totals = [T.run(index_bars, p, c).daily.sum() for c in (0., 1., 2.)]
    assert totals[0] >= totals[1] >= totals[2]


@pytest.mark.parametrize("p", F.GRID)
def test_funding_is_causal_and_costs_never_help(carry, p):
    cut = carry.index[int(len(carry)*.6)]
    st = carry.attrs["settle"]
    short = F.prepare(carry.spot[carry.index <= cut], carry.perp[carry.index <= cut], st[st.timestamp <= cut])
    limit = cut-pd.Timedelta(days=10)
    a, b = F.run_asset(carry, p).daily, F.run_asset(short, p).daily
    keep = a.index[a.index < limit]
    assert np.allclose(a[keep].values, b[keep].values, atol=1e-12)
    totals = [F.run_asset(carry, p, c).daily.sum() for c in (0., 1., 2.)]
    assert totals[0] >= totals[1] >= totals[2]


def test_funding_payment_before_entry_is_not_collected():
    days = pd.date_range("2024-01-01", periods=3, freq="D")
    flat = pd.Series(100., index=days)
    ts = pd.to_datetime(["2024-01-02 00:00", "2024-01-03 00:00"])
    df = F.prepare(flat, flat, pd.DataFrame({"timestamp": ts, "fundingRate": [.01, .02]}))
    assert df.f.iloc[0] == pytest.approx(.01) and df.f.iloc[1] == pytest.approx(.02)
