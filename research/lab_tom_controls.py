import numpy as np,pandas as pd,lab_tom as X,config as C
from data import load_specs,load_bars
sp=load_specs(C.DATA_DIR);B={s:load_bars(C.DATA_DIR,s,'D1',sp) for s in X.SYMS};nv=X.null_var(B,[1,2,3]);print('var nula',nv);bad=0
print('--- causalidad')
for s,b in B.items():
    cut=b.index[int(len(b)*.6)];lim=cut-pd.Timedelta(days=20)
    for p in X.GRID:
        r1=X.run(b,p).trades;r2=X.run(b[b.index<=cut],p).trades;x=r1[r1.index<lim];y=r2[r2.index<lim];ok=len(x)==len(y) and np.allclose(x.values,y.values,atol=1e-12);bad+=not ok;print(s,p,'ok' if ok else 'FALLA',len(x))
print('--- calendario, muestra US500');w=X.windows_tom(B['US500Cash'],X.GRID[3])[:3]
for a,z in w:print(B['US500Cash'].index[a].date(),'→',B['US500Cash'].index[z].date())
print('--- monotonia')
for p in X.GRID:
    v=[X.combine([X.run(b,p,c) for b in B.values()]).daily.sum() for c in(0,1,2)];ok=v[0]>=v[1]>=v[2];bad+=not ok;print(p,[round(x,3) for x in v],'ok' if ok else 'FALLA')
print('--- negativo');n=0
for sd in range(1,6):
    F={k:X.shuffle(v,sd*20+i) for i,(k,v) in enumerate(B.items())};s,_,_=X.evaluate(F,nv);n+=s['ok6'];print(sd,'APRUEBA' if s['ok6'] else 'rechaza','sharpe',round(s['sharpe'],2),'dsr',round(s['dsr'],3))
print('aprobados',n)
print('--- positivo')
for sd in (1,2):
    F={}
    for i,(k,v) in enumerate(B.items()):
        f=X.shuffle(v,sd*30+i);bump=np.zeros(len(f))
        for a,z in X.windows_tom(f,X.GRID[3]):bump[a:z+1]=.0040
        cum=np.exp(np.cumsum(bump));
        g=f.copy()
        for c in('open','high','low','close'):g[c]=f[c].values*cum
        F[k]=g
    s,_,_=X.evaluate(F,nv);print(sd,'APRUEBA' if s['ok6'] else 'rechaza','sharpe',round(s['sharpe'],2),'dsr',round(s['dsr'],3),[a for a,_,c in s['checks'] if not c])
print('fallas',bad)
