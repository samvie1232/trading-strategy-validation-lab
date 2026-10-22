"""
End-to-end controls. A validation engine is only trustworthy if it
  - rejects strategies on data where no edge can exist (negative control), and
  - detects an edge that was planted on purpose (positive control).
"""
from conftest import run_engine


def test_negative_control_random_walk_never_approves(random_walk_data, tmp_path):
    verdicts = run_engine(random_walk_data, tmp_path / "out")
    assert set(verdicts) == {"trend", "intraday_mom", "asian_breakout"}
    assert all(v == "NO APRUEBA" for v in verdicts.values()), verdicts


def test_positive_control_planted_edges_are_detected(planted_edge_data, tmp_path):
    verdicts = run_engine(planted_edge_data, tmp_path / "out")
    assert verdicts["trend"] == "APRUEBA", verdicts
    assert verdicts["intraday_mom"] == "APRUEBA", verdicts
    # No edge was planted for the Asian breakout -> it must still be rejected
    assert verdicts["asian_breakout"] == "NO APRUEBA", verdicts
