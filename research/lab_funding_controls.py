import numpy as np,pandas as pd,lab_funding as X
from pathlib import Path
B={a:X.load(Path('data_funding'),a) for a in('btc','eth')}
nv=X.null_var(B,[1,2,3,4,5]);print('var nula',nv);bad=0
print('--- causalidad')
for a,b in B.items():
    cut=b.index[int(len(b)*.6)];lim=cut-pd.Timedelta(days=10)
    st=b.attrs['settle'];tr=X.prepare(b.spot[b.index<=cut],b.perp[b.index<=cut],st[st.timestamp<=cut])
    for p in X.GRID:
        x=X.signal(b,p)[:len(tr)-1];y=X.signal(tr,p)[:len(tr)-1]
        r1=X.run_asset(b,p).daily;r2=X.run_asset(tr,p).daily
        k=r1.index[(r1.index<lim)];ok=(x==y).all() and np.allclose(r1[k].values,r2[k].values,atol=1e-12);bad+=not ok;print(a,p,'ok' if ok else 'FALLA')
print('--- monotonia')
for p in X.GRID:
    s=[X.combine([X.run_asset(b,p,c) for b in B.values()]).daily.sum() for c in(0,1,2)];ok=s[0]>=s[1]>=s[2];bad+=not ok;print(p,[round(v,3) for v in s],'ok' if ok else 'FALLA')
print('--- negativo');n=0
for sd in range(1,6):
    F={a:X.fake(b,sd*7+i) for i,(a,b) in enumerate(B.items())};s,_,_=X.evaluate(F,nv);n+=s['ok'];print(sd,'APRUEBA' if s['ok'] else 'rechaza','sharpe',round(s['sharpe'],2),'anual',round(s['annual_return']*100,1),'dsr',round(s['dsr'],3))
print('aprobados',n)
print('--- positivo')
for sd in (1,2):
    F={a:X.fake(b,sd*7+i,add=3e-4) for i,(a,b) in enumerate(B.items())};s,_,_=X.evaluate(F,nv);print(sd,'APRUEBA' if s['ok'] else 'rechaza','sharpe',round(s['sharpe'],2),'anual',round(s['annual_return']*100,1),'dsr',round(s['dsr'],3),[c[0] for c in s['checks'] if not c[1]])
print('fallas',bad)
