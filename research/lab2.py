"""Lab v2: hipótesis preregistradas en results/lab2/PREREGISTRO.md. Reutiliza data, metrics y engine."""
from __future__ import annotations
import json
import numpy as np, pandas as pd
from statistics import NormalDist
import config as C, metrics as M
from data import load_bars
from engine import walk_forward, monte_carlo, approve, combine
from strategies import StratResult

SLIP, SS = C.SLIPPAGE_FRAC_OF_SPREAD, C.STOP_FILL_SLIPPAGE
RISK = 0.005
N_TRIALS = 44

# ---------- indicadores causales ----------
def rsi(c: pd.Series, n=2):
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1/n, adjust=False, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False, min_periods=n).mean()
    return 100 - 100/(1 + up/dn.replace(0, np.nan))

def atr(df, n=14):
    pc = df.close.shift(1)
    tr = pd.concat([df.high-df.low, (df.high-pc).abs(), (df.low-pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def to_h1(df):
    g = df.resample("1h", label="left", closed="left")
    out = pd.DataFrame({"open": g.open.first(), "high": g.high.max(), "low": g.low.min(), "close": g.close.last(),
                        "spread": g.spread.mean(), "fin_long": g.fin_long.first(), "fin_short": g.fin_short.first()})
    return out.dropna(subset=["open", "close"])

def nights(a, b):
    return int((pd.Timestamp(b).normalize() - pd.Timestamp(a).normalize()).days)

def result_from_trades(df, dates, pnl):
    tr = pd.Series(pnl, index=pd.DatetimeIndex(dates), dtype=float)
    idx = pd.DatetimeIndex(np.unique(df.index.normalize()))
    d = tr.groupby(tr.index.normalize()).sum() if len(tr) else pd.Series(dtype=float)
    return StratResult(d.reindex(idx, fill_value=0.0), tr)

# ---------- motor de operaciones con stop/objetivo ----------
def bracket(df, ent, sl_d, tp_d=None, exit_l=None, exit_s=None, max_hold=None, cm=1.0, collect_r=False):
    """Señal en el cierre de i; ejecuta en la apertura de i+1. Stop antes que objetivo dentro de la vela."""
    o, h, l, c, spr = (df[k].values for k in ("open", "high", "low", "close", "spread"))
    fl, fs, t = df.fin_long.fillna(0).values, df.fin_short.fillna(0).values, df.index.values
    n = len(df); dates, rs = [], []; i = 0
    while i < n-1:
        d = int(ent[i])
        if d == 0 or not np.isfinite(sl_d[i]) or sl_d[i] <= 0:
            i += 1; continue
        e = i+1; entry = o[e]; stop = entry-d*sl_d[i]; risk = sl_d[i]
        tp = None if tp_d is None or not np.isfinite(tp_d[i]) else entry+d*tp_d[i]
        cost = cm*(1+SLIP)*spr[e]; px = None; x = e
        for j in range(e, n):
            x = j; ss = SS*cm*spr[j]
            if j > e:
                if max_hold and j-e >= max_hold: px = o[j]; break
                sig = exit_l if d == 1 else exit_s
                if sig is not None and sig[j-1]: px = o[j]; break
                if (d == 1 and o[j] <= stop) or (d == -1 and o[j] >= stop): px = o[j]-d*ss; break
            if (d == 1 and l[j] <= stop) or (d == -1 and h[j] >= stop): px = stop-d*ss; break
            if tp is not None:
                if j > e and ((d == 1 and o[j] >= tp) or (d == -1 and o[j] <= tp)): px = o[j]; break
                if (d == 1 and h[j] >= tp) or (d == -1 and l[j] <= tp): px = tp; break
        if px is None: px = c[n-1]; x = n-1
        fin = fl[e] if d == 1 else fs[e]
        swap = nights(t[e], t[x])*fin*entry*(1 if cm > 0 else 0)
        r = (d*(px-entry)-cost+swap)/risk
        dates.append(t[x]); rs.append(r)
        i = x if x > i else i+1
    if collect_r: return pd.Series(rs, index=pd.DatetimeIndex(dates), dtype=float)
    return result_from_trades(df, dates, [RISK*x for x in rs])

# ---------- H1 ----------
def h1(df, p, cm=1.0):
    o, c, spr = df.open.values, df.close.values, df.spread.values
    fin, t = df.fin_long.fillna(0).values, df.index.values
    cs = df.close; sma200 = cs.rolling(200).mean().values; sma5 = cs.rolling(5).mean().values; r = rsi(cs).values
    vol = cs.pct_change().rolling(60).std().values*np.sqrt(252)
    k = cm*(1+SLIP)/2; n = len(df); ret = np.zeros(n); dates, pnl = [], []; pos = False; w = 0.0; acc = 0.0
    for i in range(1, n):
        a = 0.0; ref = c[i-1]
        if pos:
            a += w*(o[i]/c[i-1]-1)+(w*fin[i]*nights(t[i-1], t[i]) if cm > 0 else 0)
            ref = o[i]
            ex = c[i-1] > sma5[i-1] if p["exit"] == "sma5" else r[i-1] > 70
            if ex:
                a -= w*k*spr[i]/o[i]; acc += a; dates.append(t[i]); pnl.append(acc); pos = False; acc = 0.0; ret[i] = a; continue
        elif c[i-1] > sma200[i-1] and r[i-1] < p["thr"] and np.isfinite(vol[i-1]) and vol[i-1] > 0:
            w = min(.10/vol[i-1], 3.0); pos = True; acc = 0.0; a -= w*k*spr[i]/o[i]; ref = o[i]
        if pos: a += w*(c[i]/ref-1); acc += a
        ret[i] = a
    return StratResult(pd.Series(ret, index=df.index.normalize()).groupby(level=0).sum(), pd.Series(pnl, index=pd.DatetimeIndex(dates), dtype=float))

# ---------- H2 ----------
def h2(df, p, cm=1.0):
    cs = df.close; r = rsi(cs); c = cs.values; rv = r.values; rl = r.shift(1).values; rl2 = r.shift(2).values
    n = len(df); ma200 = cs.rolling(200).mean().values; ma50 = cs.rolling(50).mean().values; ma5 = cs.rolling(5).mean().values
    hi2, lo2 = df.high.shift(1).values, df.low.shift(1).values
    v = p["v"]
    if v == 1:
        L, S = (rv < 5) & (c > ma200), (rv > 95) & (c < ma200)
        xl, xs = (c > ma5) | (c < ma200), (c < ma5) | (c > ma200); pct = .0015
    elif v == 2:
        L = (rv < 10) & (rl < 10) & (rl2 < 10) & (c > ma200); S = (rv > 90) & (rl > 90) & (rl2 > 90) & (c < ma200)
        xl, xs = (c > hi2) | (c < ma200), (c < lo2) | (c > ma200); pct = .0015
    else:
        L, S = (rv < 5) & (c > ma50), (rv > 95) & (c < ma50)
        xl, xs = rv > 70, rv < 30; pct = .01
    ent = L.astype(int)-S.astype(int)
    return bracket(df, ent, c*pct, None, xl, xs, None, cm)

# ---------- H3 ----------
def h3(df, p, cm=1.0):
    o, h, l, c, spr = (df[k].values for k in ("open", "high", "low", "close", "spread"))
    fl, fs, t = df.fin_long.fillna(0).values, df.fin_short.fillna(0).values, df.index.values
    hh = df.high.rolling(p["n"]).max().values; ll = df.low.rolling(p["n"]).min().values; a = atr(df).values
    n = len(df); i = p["n"]; dates, rs = [], []
    while i < n-1:
        if not np.isfinite(a[i]) or a[i] <= 0: i += 1; continue
        e = i+1; ss = SS*cm*spr[e]; d = 0
        if h[e] > hh[i]: d, entry = 1, max(o[e], hh[i])+ss
        elif l[e] < ll[i]: d, entry = -1, min(o[e], ll[i])-ss
        if d == 0: i += 1; continue
        risk = p["sl"]*a[i]; stop = entry-d*risk; tp = entry+d*p["tp"]*a[i]; cost = cm*(1+SLIP)*spr[e]; px = None; x = e
        if (d == 1 and l[e] <= stop) or (d == -1 and h[e] >= stop): px = stop-d*ss
        else:
            for j in range(e+1, n):
                x = j; s2 = SS*cm*spr[j]
                if j-e >= 72: px = o[j]; break
                if (d == 1 and o[j] <= stop) or (d == -1 and o[j] >= stop): px = o[j]-d*s2; break
                if (d == 1 and l[j] <= stop) or (d == -1 and h[j] >= stop): px = stop-d*s2; break
                if (d == 1 and o[j] >= tp) or (d == -1 and o[j] <= tp): px = o[j]; break
                if (d == 1 and h[j] >= tp) or (d == -1 and l[j] <= tp): px = tp; break
        if px is None: px = c[n-1]; x = n-1
        fin = fl[e] if d == 1 else fs[e]
        rs.append((d*(px-entry)-cost+nights(t[e], t[x])*fin*entry*(1 if cm > 0 else 0))/risk); dates.append(t[x])
        i = x if x > i else i+1
    return result_from_trades(df, dates, [RISK*x for x in rs])

# ---------- H4/H5 ----------
def h4_ent(df):
    r = rsi(df.close); e = df.close.ewm(span=50, adjust=False, min_periods=50).mean()
    return ((r < 10) & (df.close > e)).astype(int).values-((r > 90) & (df.close < e)).astype(int).values

def h4(df, p, cm=1.0, collect_r=False):
    a = atr(df).values; ent = h4_ent(df)
    if "k" in p: ent = np.where(a/df.spread.values >= p["k"], ent, 0)
    return bracket(df, ent, a*p["sl"], a*p["tp"], None, None, 16, cm, collect_r)

def h4_random(df, p, n_trades, sims, seed, cm=1.0):
    """Medias en R de entradas al azar (compra o venta) con las mismas salidas, sobre los mismos bars posibles."""
    a = atr(df).values; rng = np.random.default_rng(seed); out = []
    valid = np.where(np.isfinite(a) & (a > 0))[0]
    if "k" in p: valid = valid[(a[valid]/df.spread.values[valid]) >= p["k"]]
    n = len(df); valid = valid[valid < n-2]
    # tabla: resultado de cada bar en cada dirección
    cache = {}
    def one(i, d):
        key = (i, d)
        if key not in cache:
            ent = np.zeros(i+20 if i+20 < n else n, dtype=int); ent[i] = d
            sub = df.iloc[:len(ent)]
            cache[key] = float(bracket(sub, ent, a[:len(ent)]*p["sl"], a[:len(ent)]*p["tp"], None, None, 16, cm, True).iloc[0])
        return cache[key]
    pool_i = rng.choice(valid, size=min(4000, len(valid)), replace=False)
    table = {d: np.array([one(int(i), d) for i in pool_i]) for d in (1, -1)}
    for _ in range(sims):
        idx = rng.integers(0, len(pool_i), n_trades); dr = rng.integers(0, 2, n_trades)
        out.append(np.where(dr == 1, table[1][idx], table[-1][idx]).mean())
    return np.array(out)

# ---------- H6 ----------
def h6(g, s, p, cm=1.0):
    idx = g.index.intersection(s.index); g, s = g.loc[idx], s.loc[idx]
    lg, ls = np.log(g.close), np.log(s.close); L = p["L"]
    cov = ls.rolling(L).cov(lg); var = lg.rolling(L).var(); beta = cov/var
    # residuo de la regresión móvil con la beta ACTUAL; evita que el cambio de beta domine el spread
    res = (ls-ls.rolling(L).mean())-beta*(lg-lg.rolling(L).mean())
    rv = (ls.rolling(L).var()-beta**2*var).clip(lower=0)
    z = (res/np.sqrt(rv).replace(0, np.nan)).values
    # volatilidad del spread con la beta de ese momento: causal
    de = (ls.diff()-beta.shift(1)*lg.diff()); sv = (de.rolling(360).std()*np.sqrt(252*6)).values
    b = beta.values; t = idx.values; n = len(idx); k = cm*(1+SLIP)/2
    og, cg, sg, os_, cs_, ss_ = g.open.values, g.close.values, g.spread.values, s.open.values, s.close.values, s.spread.values
    fg_l, fg_s, fs_l, fs_s = g.fin_long.fillna(0).values, g.fin_short.fillna(0).values, s.fin_long.fillna(0).values, s.fin_short.fillna(0).values
    ret = np.zeros(n); dates, pnl = [], []; d = 0; held = 0; ws = wg = acc = 0.0
    for i in range(1, n):
        a = 0.0; rs, rg = cs_[i-1], cg[i-1]
        if d:
            nn = nights(t[i-1], t[i])
            a += d*ws*(os_[i]/cs_[i-1]-1)-d*wg*(og[i]/cg[i-1]-1)
            if cm > 0:
                a += nn*(ws*(fs_l[i] if d == 1 else fs_s[i])+wg*(fg_s[i] if d == 1 else fg_l[i]))
            rs, rg = os_[i], og[i]; held += 1
            if abs(z[i-1]) < .5 or abs(z[i-1]) > 4 or held >= 240:
                a -= k*(ws*ss_[i]/os_[i]+wg*sg[i]/og[i]); acc += a; ret[i] = a
                dates.append(t[i]); pnl.append(acc); d = 0; acc = 0.0; continue
        elif np.isfinite(z[i-1]) and np.isfinite(sv[i-1]) and sv[i-1] > 0 and abs(z[i-1]) > p["z"] and abs(z[i-1]) < 4 and b[i-1] > 0:
            d = -1 if z[i-1] > 0 else 1; scale = min(.10/sv[i-1], 3.0); ws = scale; wg = scale*b[i-1]; held = 0; acc = 0.0
            a -= k*(ws*ss_[i]/os_[i]+wg*sg[i]/og[i]); rs, rg = os_[i], og[i]
        if d: a += d*ws*(cs_[i]/rs-1)-d*wg*(cg[i]/rg-1); acc += a
        ret[i] = a
    return StratResult(pd.Series(ret, index=idx.normalize()).groupby(level=0).sum(), pd.Series(pnl, index=pd.DatetimeIndex(dates), dtype=float))

GRID = {
 "H1": [{"thr": t, "exit": x} for t in (5, 10) for x in ("sma5", "rsi70")],
 "H2": [{"v": v} for v in (1, 2, 3)],
 "H3": [{"n": n, "sl": s, "tp": t} for n in (20, 50) for s in (1.5, 2.0) for t in (2.0, 3.0)],
 "H4": [{"tp": t, "sl": s} for t, s in ((.5, .5), (.5, 1.5), (1, 1), (1, 2))],
 "H5": [{"tp": t, "sl": s, "k": k} for t, s in ((1, 1), (1, 2)) for k in (8, 15)],
 "H6": [{"L": L, "z": z} for L in (360, 720) for z in (1.5, 2.0)],
}
UNIV = {"H1": (["US500Cash", "US100Cash", "US30Cash", "GER40Cash"], "D1"), "H2": (["GOLD", "US500Cash"], "M30"),
        "H3": (["GOLD"], "H1"), "H4": (["GOLD", "US500Cash"], "M30"), "H5": (["GOLD", "US500Cash"], "M30"), "H6": (["GOLD", "SILVER"], "H4")}
FN = {"H1": h1, "H2": h2, "H3": h3, "H4": h4, "H5": h4}

def load_family(fam, data_dir, specs):
    syms, tf = UNIV[fam]; bars = {}
    for s in syms:
        df = load_bars(data_dir, s, "M30" if tf == "H1" else tf, specs)
        bars[s] = to_h1(df) if tf == "H1" else df
    return bars

def build(fam, bars, cm):
    out = {}
    for p in GRID[fam]:
        lab = json.dumps(p)
        if fam == "H6": out[lab] = h6(bars["GOLD"], bars["SILVER"], p, cm)
        else: out[lab] = combine([FN[fam](b, p, cm) for b in bars.values()])
    return out

def dsr(daily: pd.Series, sr_var: float, n=N_TRIALS):
    """Deflated Sharpe (Bailey y López de Prado). SR en base diaria."""
    r = daily.fillna(0).values; T = len(r); sd = r.std(ddof=1)
    if T < 3 or sd == 0: return 0.0
    sr = r.mean()/sd; z = (r-r.mean())/sd; g3 = (z**3).mean(); g4 = (z**4).mean()
    nd = NormalDist(); gamma = .5772156649
    sr0 = np.sqrt(sr_var)*((1-gamma)*nd.inv_cdf(1-1/n)+gamma*nd.inv_cdf(1-1/(n*np.e)))
    den = 1-g3*sr+(g4-1)/4*sr**2
    return nd.cdf((sr-sr0)*np.sqrt(T-1)/np.sqrt(max(den, 1e-12)))

def evaluate(fam, bars, sr_var=None):
    runs, stress, zero = build(fam, bars, 1.0), build(fam, bars, 2.0), build(fam, bars, 0.0)
    wf = walk_forward(runs, C.WF_TRAIN_YEARS, C.WF_TEST_MONTHS)
    ws = walk_forward(stress, C.WF_TRAIN_YEARS, C.WF_TEST_MONTHS, forced=wf.chosen)
    wz = walk_forward(zero, C.WF_TRAIN_YEARS, C.WF_TEST_MONTHS, forced=wf.chosen)
    st = M.summary(wf.oos_daily, wf.oos_trades)
    st.update(monte_carlo(wf.oos_daily, C.MC_SIMULATIONS, C.MC_BLOCK_DAYS, C.RANDOM_SEED))
    st["wfe"] = st["annual_return"]/wf.is_annual_mean if wf.is_annual_mean > 0 else np.nan
    st["pct_positive_windows"] = float((wf.windows.test_return > 0).mean())
    st["stress_sharpe"] = M.sharpe(ws.oos_daily)
    st["zero_cost_sharpe"] = M.sharpe(wz.oos_daily); st["zero_cost_annual"] = M.annual_return(wz.oos_daily)
    st["is_annual"] = wf.is_annual_mean; st["oos_start"] = str(wf.oos_daily.index.min().date()); st["oos_end"] = str(wf.oos_daily.index.max().date())
    st["chosen"] = wf.chosen; st["windows"] = len(wf.windows)
    full = {k: (r.daily.mean()/r.daily.std() if r.daily.std() > 0 else 0.0) for k, r in runs.items()}
    return st, wf, runs, full

def verdict(st, sr_var):
    st["dsr"] = dsr(st["_daily"], sr_var)
    checks = approve(st, C.APPROVAL)
    checks = [(a, b, bool(c)) for a, b, c in checks]+[("Deflated Sharpe", f"{st['dsr']:.3f} (mín. 0.95)", st["dsr"] >= .95)]
    return checks

_NV = {}
def null_var(B, fams, seeds):
    """Varianza del Sharpe diario solo por azar: mismas reglas sobre velas barajadas, centrada por intento."""
    key = tuple(seeds)
    if key in _NV: return _NV[key]
    res = []
    for f in fams:
        for p in GRID[f]:
            vals = []
            for sd in seeds:
                b = {k: shuffle(v, sd*10+i) for i, (k, v) in enumerate(B[f].items())}
                r = h6(b["GOLD"], b["SILVER"], p, 1.0) if f == "H6" else combine([FN[f](v, p, 1.0) for v in b.values()])
                vals.append(r.daily.mean()/r.daily.std() if r.daily.std() > 0 else 0.0)
            res += list(np.array(vals)-np.mean(vals))
    _NV[key] = float(np.var(res, ddof=1)); return _NV[key]

def shuffle(df, seed, phi=0.0, drift=0.0):
    """Baraja velas: destruye toda estructura temporal. phi<0 planta reversión, drift>0 planta tendencias por régimen."""
    rng = np.random.default_rng(seed); p = rng.permutation(len(df)); n = len(df)
    pc = df.close.shift(1).fillna(df.open)
    gap = np.log(df.open/pc).values[p]; co = np.log(df.close/df.open).values[p]
    hi = np.log(df.high/df.open).values[p]; lo = np.log(df.low/df.open).values[p]
    sig = np.nanstd(gap+co); o = np.empty(n); c = np.empty(n); h = np.empty(n); l = np.empty(n); x = float(np.log(df.close.iloc[0])); prev = 0.0
    reg = 1.0
    for i in range(n):
        if drift and rng.random() < 1/200: reg = -reg
        extra = phi*prev+(drift*sig*reg if drift else 0.0)
        o[i] = x+gap[i]; c[i] = o[i]+co[i]+extra; h[i] = o[i]+max(hi[i], co[i]+extra, 0); l[i] = o[i]+min(lo[i], co[i]+extra, 0)
        prev = c[i]-x; x = c[i]
    out = df.copy(); out["open"], out["high"], out["low"], out["close"] = np.exp(o), np.exp(h), np.exp(l), np.exp(c)
    return out
