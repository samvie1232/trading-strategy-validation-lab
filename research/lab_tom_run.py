import json,numpy as np,pandas as pd,lab_tom as X,config as C,metrics as M
from pathlib import Path
from data import load_specs,load_bars
from lab2 import nights
print('swap',C.SWAP_MODEL)
sp=load_specs(C.DATA_DIR);B={s:load_bars(C.DATA_DIR,s,'D1',sp) for s in X.SYMS};nv=X.null_var(B,[1,2,3])
s,wf,runs=X.evaluate(B,nv);d=wf.oos_daily
out=C.OUT_DIR;out.mkdir(exist_ok=True);wf.windows.to_csv(out/'windows.csv',index=False)
p=json.loads(pd.Series(wf.chosen).value_counts().index[0]);print('param mas elegido',p,pd.Series(wf.chosen).value_counts().to_dict())
t=pd.concat([X.run(b,p).trades for b in B.values()]);t=t[t.index>=d.index.min()]
rd=X.random_baseline(B,p,d.index.min());p95=np.percentile(rd,95);pct=(rd<t.mean()).mean()
s['checks'].append(('Mejor que ventanas al azar',f'{t.mean():.5f} vs p95 {p95:.5f} (mediana azar {np.median(rd):.5f}, pct {pct:.3f})',t.mean()>p95))
print('VEREDICTO','APRUEBA' if all(c for _,_,c in s['checks']) else 'NO APRUEBA')
for c in s['checks']:print(' ',c)
print({k:round(s[k],4) for k in('annual_return','sharpe','max_drawdown','trades','win_rate','profit_factor','zero','stress_sharpe','dsr','is_ann','mc_p95_drawdown')},d.index.min().date(),d.index.max().date())
print('exposicion',round((d!=0).mean()*100,1),'%')
print('por ano',(d.groupby(d.index.year).apply(lambda r:(1+r).prod()-1)*100).round(1).to_dict())
l=d[d.index>=d.index.max()-pd.DateOffset(months=24)];print('ultimos 24m anual',round(M.annual_return(l)*100,2),'sharpe',round(M.sharpe(l),2))
print('--- por indice');
for k,b in B.items():
    r=X.run(b,p);dd=r.daily[r.daily.index>=d.index.min()];tt=r.trades[r.trades.index>=d.index.min()];print(k,len(tt),'sharpe',round(M.sharpe(dd),2),'anual',round(M.annual_return(dd)*100,1),'aciertos',round((tt>0).mean()*100,1),'media',round(tt.mean()*100,3))
    g=b.close.pct_change().fillna(0).values+b.fin_long.fillna(0).values*np.r_[0,[nights(x,y) for x,y in zip(b.index.values[:-1],b.index.values[1:])]];g=pd.Series(g,index=b.index);g=g[g.index>=d.index.min()];print('   comprar y mantener sharpe',round(M.sharpe(g),2),'anual',round(M.annual_return(g)*100,1),'caida',round(M.max_drawdown(g)*100,1))
print('--- cada parametro completo');
for k,r in runs.items():print(k,'sharpe',round(M.sharpe(r.daily),2),'anual',round(M.annual_return(r.daily)*100,2))
print(wf.windows[['test_start','test_return','test_sharpe','test_trades']].to_string(index=False))
