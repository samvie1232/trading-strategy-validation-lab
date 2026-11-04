"""Controles del Lab v2 sobre datos barajados o con efectos plantados."""
import time
import config as C
import lab2 as X,numpy as np,pandas as pd
from data import load_specs
d=C.DATA_DIR;sp=load_specs(d);F=list(X.GRID)
B={f:X.load_family(f,d,sp) for f in F}
def run_one(f,b,p,cm=1.):
    if f=='H6':return X.h6(b['GOLD'],b['SILVER'],p,cm)
    return X.combine([X.FN[f](v,p,cm) for v in b.values()])
print('--- causalidad (truncar el futuro no cambia lo pasado)');bad=0
for f in F:
    b=B[f];last=min(v.index[-1] for v in b.values());first=max(v.index[0] for v in b.values());cut=first+(last-first)*.6
    tb={k:v[v.index<=cut] for k,v in b.items()};lim=cut-pd.Timedelta(days=30)
    pairs=[(b,tb)] if f=='H6' else [({k:b[k]},{k:tb[k]}) for k in b]
    for full,tr in pairs:
      for p in X.GRID[f]:
        a=run_one(f,full,p);t=run_one(f,tr,p)
        x=a.trades[a.trades.index<lim];y=t.trades[t.trades.index<lim]
        ok=len(x)==len(y) and np.allclose(x.values,y.values,atol=1e-12)
        bad+=not ok;print(f,list(full)[0],p,'ok' if ok else 'FALLA',len(x),len(y))
print('--- monotonia de costos');
for f in F:
    for p in X.GRID[f][:2]:
        s=[run_one(f,B[f],p,c).daily.sum() for c in (0,1,2)]
        ok=s[0]>=s[1]>=s[2];bad+=not ok;print(f,p,[round(v,3) for v in s],'ok' if ok else 'FALLA')
print('--- control negativo: velas barajadas');passes=0
def ev(f,b):
    st,wf,runs,full=X.evaluate(f,b);st['_daily']=wf.oos_daily
    var=X.null_var(B,F,[1,2,3])
    ch=X.verdict(st,var);return st,all(c for _,_,c in ch),[n for n,_,c in ch if not c]
for f in F:
    for seed in (1,2,3):
        t0=time.time();b={k:X.shuffle(v,seed*10+i) for i,(k,v) in enumerate(B[f].items())}
        st,ap,fa=ev(f,b);passes+=ap;print(f,seed,'APRUEBA' if ap else 'rechaza','sharpe',round(st['sharpe'],2),'ops',st['trades'],'zero',round(st['zero_cost_sharpe'],2),'dsr',round(st['dsr'],3),'%.0fs'%(time.time()-t0),flush=True)
print('negativos aprobados:',passes)
print('--- control positivo: efecto plantado')
cases={'H1':dict(phi=-.30),'H2':dict(phi=-.25),'H3':dict(drift=.35),'H4':dict(phi=-.30),'H5':dict(phi=-.30)}
for f,k in cases.items():
    b={s:X.shuffle(v,100+i,**k) for i,(s,v) in enumerate(B[f].items())}
    st,ap,fa=ev(f,b);print(f,k,'APRUEBA' if ap else 'rechaza','sharpe',round(st['sharpe'],2),'ops',st['trades'],'dsr',round(st['dsr'],3),'falla',fa,flush=True)
# H6: plata = beta*oro + OU
g=X.shuffle(B['H6']['GOLD'],7);s0=B['H6']['SILVER'].loc[g.index.intersection(B['H6']['SILVER'].index)].copy();g=g.loc[s0.index]
rng=np.random.default_rng(8);e=np.zeros(len(g))
for i in range(1,len(g)):e[i]=.97*e[i-1]+rng.normal(0,.006)
c=np.exp(.9*np.log(g.close.values/g.close.values[0])+e)*s0.close.values[0];o=np.r_[c[0],c[:-1]]
s0['open'],s0['close']=o,c;s0['high']=np.maximum(o,c)*1.0005;s0['low']=np.minimum(o,c)*.9995
st,ap,fa=ev('H6',{'GOLD':g,'SILVER':s0});print('H6 plantado','APRUEBA' if ap else 'rechaza','sharpe',round(st['sharpe'],2),'ops',st['trades'],'dsr',round(st['dsr'],3),'falla',fa)
print('fallas estructurales',bad)
