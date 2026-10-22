import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

RESEARCH_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RESEARCH_DIR))

import make_synthetic  # noqa: E402

VERDICT_RE = re.compile(r"\[(\w+)\] (NO APRUEBA|APRUEBA)")


def run_engine(data_dir: Path, out_dir: Path) -> dict[str, str]:
    """Run the full pipeline as a user would and return {family: verdict}."""
    env = {**os.environ, "XM_DATA_DIR": str(data_dir), "XM_OUT_DIR": str(out_dir), "MPLBACKEND": "Agg"}
    proc = subprocess.run([sys.executable, "run.py"], cwd=RESEARCH_DIR, env=env,
                          capture_output=True, text=True, encoding="utf-8", timeout=600)
    assert proc.returncode == 0, proc.stderr
    return {fam: verdict for fam, verdict in VERDICT_RE.findall(proc.stdout)}


@pytest.fixture(scope="session")
def random_walk_data(tmp_path_factory) -> Path:
    return make_synthetic.main(seed=7, out=tmp_path_factory.mktemp("random_walk"))


@pytest.fixture(scope="session")
def planted_edge_data(tmp_path_factory) -> Path:
    """Random walk + two real, known effects planted on purpose."""
    d = make_synthetic.main(seed=7, out=tmp_path_factory.mktemp("planted_edge"))
    rng = np.random.default_rng(1)

    # 1) Persistent drift regimes on daily bars -> trend following should find it
    for f in d.glob("*_D1.csv"):
        df = pd.read_csv(f)
        n = len(df)
        drift = np.zeros(n)
        i = 0
        while i < n:
            length = rng.integers(80, 250)
            drift[i:i + length] = rng.choice([-1, 1]) * 0.0009
            i += length
        lc = np.log(df["close"].values)
        step = np.diff(lc, prepend=lc[0]) + drift
        ratio = np.exp(lc[0] + np.cumsum(step)) / df["close"].values
        for c in ["open", "high", "low", "close"]:
            df[c] = (df[c] * ratio).round(5)
        df.to_csv(f, index=False)

    # 2) Last half hour follows the first half hour -> intraday momentum should find it
    for sym in ["US500Cash", "US100Cash"]:
        f = d / f"{sym}_M30.csv"
        df = pd.read_csv(f)
        t = pd.to_datetime(df["time"], format="%Y.%m.%d %H:%M")
        mins = t.dt.hour * 60 + t.dt.minute
        day = t.dt.normalize()
        first = df[mins == 16 * 60 + 30]
        r1 = pd.Series(first["close"].values / first["open"].values - 1, index=day[first.index].values)
        for idx in df[mins == 22 * 60 + 30].index:
            if day[idx] in r1.index:
                o = df.at[idx, "open"]
                c = df.at[idx, "close"] * (1 + 0.6 * r1.loc[day[idx]])
                df.at[idx, "close"] = c
                df.at[idx, "high"] = max(df.at[idx, "high"], c, o)
                df.at[idx, "low"] = min(df.at[idx, "low"], c, o)
        df.to_csv(f, index=False)
    return d
