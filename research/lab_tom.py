"""H8: cambio de mes en índices. Reglas en results/tom/PREREGISTRO.md."""
from __future__ import annotations
import json
import numpy as np, pandas as pd
import config as C, metrics as M
from engine import walk_forward, monte_carlo, approve, combine
from strategies import StratResult
from lab2 import dsr, shuffle, nights, SLIP

SYMS = ["US500Cash", "US100Cash", "US30Cash", "GER40Cash"]
GRID = [{"before": b, "after": a} for b in (1, 2) for a in (2, 3)]
N_TRIALS = 53

def entry_date(month: pd.Period, before: int):
    end = pd.offsets.BMonthEnd().rollforward(month.to_timestamp())
    return end-pd.offsets.BDay(before-1)

def weights(df):
    vol = df.close.pct_change().rolling(60).std().values*np.sqrt(252)
    return vol

def windows_tom(df, p):
    """Lista de (i_entrada, i_salida) con índices de vela, decididos solo con calendario y conteo de velas pasadas."""
    idx = df.index; per = idx.to_period("M"); out = []; i = 0; n = len(df); done = set()
    while i < n:
        m = per[i]
        if m not in done and idx[i] >= entry_date(m, p["before"]):
            done.add(m); nx = m+1; j = i; c = 0
            while j+1 < n:
                j += 1
                if per[j] >= nx:
                    c += 1
                    if c == p["after"] or per[j] > nx: break
            if c == p["after"]: out.append((i, j))
            i = j+1; continue
        i += 1
    return out

def run_windows(df, wins, cm=1.0):
    o, c, spr = df.open.values, df.close.values, df.spread.values; fin = df.fin_long.fillna(0).values; t = df.index.values
    vol = weights(df); k = cm*(1+SLIP)/2; n = len(df); ret = np.zeros(n); dates, pnl = [], []
    for a, b in wins:
        if a < 1 or not np.isfinite(vol[a-1]) or vol[a-1] <= 0: continue
        w = min(.10/vol[a-1], 3.0); acc = -w*k*spr[a]/o[a]+w*(c[a]/o[a]-1); ret[a] += acc
        for j in range(a+1, b+1):
            x = w*(c[j]/c[j-1]-1)+(w*fin[j]*nights(t[j-1], t[j]) if cm > 0 else 0.0); ret[j] += x; acc += x
        x = -w*k*spr[b]/c[b]; ret[b] += x; acc += x
        dates.append(t[b]); pnl.append(acc)
    return StratResult(pd.Series(ret, index=df.index.normalize()).groupby(level=0).sum(), pd.Series(pnl, index=pd.DatetimeIndex(dates), dtype=float))

def run(df, p, cm=1.0):
    return run_windows(df, windows_tom(df, p), cm)

def build(B, cm):
    return {json.dumps(p): combine([run(b, p, cm) for b in B.values()]) for p in GRID}

def random_baseline(B, p, start, sims=2000, seed=5):
    """Una ventana al azar de igual duración por mes y por índice; devuelve la distribución del resultado medio por operación."""
    rng = np.random.default_rng(seed); H = p["before"]+p["after"]
    tables = []
    for b in B.values():
        per = b.index.to_period("M"); idx = np.arange(len(b)); rows = []
        for m in pd.unique(per[b.index >= start]):
            cand = idx[(per == m)]; cand = cand[cand+H-1 < len(b)]
            if len(cand):
                vals = []
                for i in cand:
                    t = run_windows(b, [(int(i), int(i)+H-1)]).trades
                    vals.append(t.iloc[0] if t.size else np.nan)
                rows.append(vals)
        tables.append(rows)
    out = np.empty(sims)
    for s in range(sims):
        v = [x[rng.integers(len(x))] for rows in tables for x in rows]
        out[s] = np.nanmean(v)
    return out

def null_var(B, seeds):
    res = []
    for p in GRID:
        v = []
        for sd in seeds:
            r = combine([run(shuffle(b, sd*10+i), p) for i, b in enumerate(B.values())]); v.append(r.daily.mean()/r.daily.std() if r.daily.std() > 0 else 0.)
        res += list(np.array(v)-np.mean(v))
    return float(np.var(res, ddof=1))

def evaluate(B, nv):
    runs, st_r, z = build(B, 1.), build(B, 2.), build(B, 0.)
    wf = walk_forward(runs, C.WF_TRAIN_YEARS, C.WF_TEST_MONTHS)
    ws = walk_forward(st_r, C.WF_TRAIN_YEARS, C.WF_TEST_MONTHS, forced=wf.chosen)
    wz = walk_forward(z, C.WF_TRAIN_YEARS, C.WF_TEST_MONTHS, forced=wf.chosen)
    d = wf.oos_daily; s = M.summary(d, wf.oos_trades); s.update(monte_carlo(d, C.MC_SIMULATIONS, C.MC_BLOCK_DAYS, C.RANDOM_SEED))
    s["wfe"] = s["annual_return"]/wf.is_annual_mean if wf.is_annual_mean > 0 else np.nan
    s["pct_positive_windows"] = float((wf.windows.test_return > 0).mean()); s["stress_sharpe"] = M.sharpe(ws.oos_daily)
    s["zero"] = M.sharpe(wz.oos_daily); s["dsr"] = dsr(d, nv, N_TRIALS); s["chosen"] = wf.chosen; s["_daily"] = d; s["is_ann"] = wf.is_annual_mean
    ch = [(a, b, bool(c)) for a, b, c in approve(s, C.APPROVAL)]+[("Deflated Sharpe", f"{s['dsr']:.3f}", s["dsr"] >= .95)]
    s["checks"] = ch; s["ok6"] = all(c for _, _, c in ch)
    return s, wf, runs
