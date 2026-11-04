"""H7: carry de funding delta neutral. Reglas en results/funding/PREREGISTRO.md."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np, pandas as pd
import config as C, metrics as M
from engine import walk_forward, monte_carlo, combine
from strategies import StratResult
from lab2 import dsr

RF = 0.04/365
DEPLOYED = 2/3
GRID = [{"mode": "always_on"}]+[{"mode": "threshold", "w": w, "e": e, "x": .5} for w in (3, 21) for e in (1., 2.)]
ONE_WAY = (10+5+2+2)/1e4
N_TRIALS = 49

def ann(r):
    """Retorno anualizado con 365 días: cripto opera todos los días (metrics.py asume 252)."""
    return float(np.prod(1+r.fillna(0).values)**(365/len(r))-1) if len(r) else 0.0

def sharpe365(r):
    sd = r.fillna(0).std()
    return float(r.fillna(0).mean()/sd*np.sqrt(365)) if sd > 0 else 0.0

def load(d: Path, a: str) -> pd.DataFrame:
    def read(name, cols=None):
        x = pd.read_csv(d/name, usecols=cols)
        x["timestamp"] = pd.to_datetime(x.timestamp, format="ISO8601", utc=True).dt.tz_localize(None)
        return x
    s = read(f"{a}_spot.csv").set_index("timestamp").close.rename("spot")
    p = read(f"{a}_perp.csv").set_index("timestamp").close.rename("perp")
    return prepare(s, p, read(f"{a}_funding_rate.csv", ["timestamp", "fundingRate"]))

def prepare(s, p, f):
    # (00:00, 00:00 siguiente]: el pago de las 00:00 pertenece al día anterior
    f = f.copy(); f["day"] = (f.timestamp-pd.Timedelta(milliseconds=500)).dt.floor("D")
    day = f.groupby("day").fundingRate.agg(["sum", "count"])
    df = pd.DataFrame({"spot": pd.Series(s.values, index=s.index), "perp": pd.Series(p.values, index=p.index)}).dropna()
    df.index = df.index.floor("D")
    df["f"] = day["sum"].reindex(df.index).fillna(0.0); df["n"] = day["count"].reindex(df.index).fillna(0).astype(int)
    df.attrs["settle"] = f[["timestamp", "fundingRate"]].sort_values("timestamp").reset_index(drop=True)
    return df

def signal(df, p):
    n = len(df); sig = np.zeros(n, dtype=bool)
    if p["mode"] == "always_on": sig[:] = True; return sig
    st = df.attrs["settle"]; r = st.fundingRate.rolling(p["w"]).mean()*1e4; t = st.timestamp.values
    closes = (df.index+pd.Timedelta(days=1)).values
    idx = np.searchsorted(t, closes, side="right")-1
    m = np.where(idx >= 0, r.values[np.clip(idx, 0, None)], np.nan); on = False
    for i in range(n):
        if not on and m[i] >= p["e"]: on = True
        elif on and m[i] <= p["x"]: on = False
        sig[i] = on
    return sig

def run_asset(df, p, cm=1.0):
    sig = signal(df, p); s, q, f, cnt = df.spot.values, df.perp.values, df.f.values, df.n.values; n = len(df)
    ret = np.zeros(n); dates, pnl = [], []; pos = False; acc = 0.; ref = 0.; settle = 0; k = cm*ONE_WAY
    for i in range(1, n):
        a = 0.
        if pos:
            a += f[i]+(s[i]/s[i-1]-1)-(q[i]/q[i-1]-1); settle += cnt[i]
            if abs(s[i]/ref-1) >= .25: a -= k/3; ref = s[i]
        if pos and not sig[i]:
            a -= k; acc += a; dates.append(df.index[i]); pnl.append(acc*DEPLOYED); pos = False; acc = 0.; ret[i] = a*DEPLOYED-RF; continue
        if not pos and sig[i]:
            a -= k; pos = True; ref = s[i]; acc = 0.
            ret[i] = a*DEPLOYED; acc += a; continue
        if pos: acc += a; ret[i] = a*DEPLOYED-RF
    if pos: dates.append(df.index[n-1]); pnl.append(acc*DEPLOYED)
    return StratResult(pd.Series(ret, index=df.index), pd.Series(pnl, index=pd.DatetimeIndex(dates), dtype=float))

def build(B, cm):
    return {json.dumps(p): combine([run_asset(b, p, cm) for b in B.values()]) for p in GRID}

def evaluate(B, nv):
    runs, st_r, z = build(B, 1.), build(B, 2.), build(B, 0.)
    wf = walk_forward(runs, C.WF_TRAIN_YEARS, C.WF_TEST_MONTHS)
    ws = walk_forward(st_r, C.WF_TRAIN_YEARS, C.WF_TEST_MONTHS, forced=wf.chosen)
    wz = walk_forward(z, C.WF_TRAIN_YEARS, C.WF_TEST_MONTHS, forced=wf.chosen)
    d = wf.oos_daily; s = M.summary(d, wf.oos_trades); s.update(monte_carlo(d, C.MC_SIMULATIONS, C.MC_BLOCK_DAYS, C.RANDOM_SEED))
    # días con posición en el parámetro elegido de cada ventana x pagos por día
    held = 0
    for _, row in wf.windows.iterrows():
        p = json.loads(row.chosen_params); a = pd.Timestamp(row.test_start); b = pd.Timestamp(row.test_end)
        for df in B.values():
            sig = pd.Series(signal(df, p), index=df.index)
            m = (sig.index >= a) & (sig.index <= b)
            held += int(df.n[m & sig.shift(1, fill_value=False).values].sum())
    last = d[d.index >= d.index.max()-pd.DateOffset(months=24)]
    s["annual_return"], s["sharpe"] = ann(d), sharpe365(d)
    is_y = wf.is_annual_mean*0  # WFE: se recalcula con 365 días, ventana por ventana
    tr_ann = []
    for _, row in wf.windows.iterrows():
        a0 = pd.Timestamp(row.test_start); dd = runs[row.chosen_params].daily
        tr_ann.append(ann(dd[(dd.index >= a0-pd.DateOffset(years=2)) & (dd.index < a0)]))
    is_y = float(np.mean(tr_ann))
    s.update(wfe=s["annual_return"]/is_y if is_y > 0 else np.nan, pos=float((wf.windows.test_return > 0).mean()),
             stress=sharpe365(ws.oos_daily), zero=sharpe365(wz.oos_daily), zero_ann=ann(wz.oos_daily), settle=held,
             last24=ann(last), dsr=dsr(d, nv, N_TRIALS), is_ann=is_y, chosen=wf.chosen)
    a = C.APPROVAL
    wfe = s["wfe"]
    s["checks"] = [("Pagos de funding OOS", s["settle"] >= 100, s["settle"]), ("Sharpe en exceso", s["sharpe"] >= .5, round(s["sharpe"], 2)),
                   ("Eficiencia WF", wfe == wfe and wfe >= .5, None if wfe != wfe else round(wfe, 2)), ("Ventanas positivas", s["pos"] >= .55, round(s["pos"], 2)),
                   ("Caída p95", s["mc_p95_drawdown"] <= .25, round(s["mc_p95_drawdown"], 3)), ("Sharpe doble costo", s["stress"] >= .2, round(s["stress"], 2)),
                   ("Deflated Sharpe", s["dsr"] >= .95, round(s["dsr"], 3)), ("Exceso 24 meses", s["last24"] > 0, round(s["last24"], 3))]
    s["ok"] = all(c for _, c, _ in s["checks"])
    return s, wf, runs

def fake(df, seed, add=0.0):
    st = df.attrs["settle"].copy(); rng = np.random.default_rng(seed)
    v = st.fundingRate.values-st.fundingRate.mean(); st["fundingRate"] = rng.permutation(v)+add
    return prepare(df.spot.rename("spot"), df.perp.rename("perp"), st)

def null_var(B, seeds):
    res = []
    for p in GRID:
        v = []
        for sd in seeds:
            r = combine([run_asset(fake(b, sd+i), p) for i, b in enumerate(B.values())]); v.append(r.daily.mean()/r.daily.std() if r.daily.std() > 0 else 0.)
        res += list(np.array(v)-np.mean(v))
    return float(np.var(res, ddof=1))
