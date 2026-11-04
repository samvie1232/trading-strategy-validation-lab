import json,numpy as np,pandas as pd,lab_funding as X,metrics as M
from pathlib import Path
import config as C
B={a:X.load(Path('data_funding'),a) for a in('btc','eth')};nv=X.null_var(B,[1,2,3,4,5])
s,wf,runs=X.evaluate(B,nv)
out=Path('output_funding');out.mkdir(exist_ok=True);wf.windows.to_csv(out/'windows.csv',index=False);wf.oos_daily.to_csv(out/'oos_daily.csv')
print('OOS',wf.oos_daily.index.min().date(),wf.oos_daily.index.max().date());print({k:(round(v,4) if isinstance(v,float) else v) for k,v in s.items() if k in('annual_return','sharpe','max_drawdown','trades','win_rate','zero','zero_ann','stress','settle','last24','dsr','wfe','pos','mc_p95_drawdown','is_ann','mc_prob_loss')})
print('VEREDICTO','APRUEBA' if s['ok'] else 'NO APRUEBA');[print(' ',c) for c in s['checks']]
pd.set_option('display.width',200,'display.max_colwidth',60);print(wf.windows.to_string(index=False))
d=wf.oos_daily
# exposicion y retorno en posicion
inpos=[];
for _,row in wf.windows.iterrows():
    p=json.loads(row.chosen_params);A=pd.Timestamp(row.test_start);Z=pd.Timestamp(row.test_end)
    for df in B.values():
        sg=pd.Series(X.signal(df,p),index=df.index);m=(sg.index>=A)&(sg.index<=Z);inpos+=[float(sg[m].mean())]*int(m.sum())
expo=float(np.mean(inpos));print('exposicion media',round(expo*100,1),'%')
print('exceso anual',round(X.ann(d)*100,2),'% sharpe',round(X.sharpe365(d),2));gross=d+X.RF
print('retorno bruto si efectivo renta 4 %',round(X.ann(gross)*100,2))
print('por ano exceso',(d.groupby(d.index.year).apply(lambda r:(1+r).prod()-1)*100).round(2).to_dict())
print('peores dias',{str(k.date()):round(v*100,3) for k,v in d.nsmallest(3).items()})
print('asimetria',round(d.skew(),2),'curtosis',round(d.kurt(),1))
for a,b in B.items():
    st=b.attrs['settle'];print(a,'funding anual % nocional',(st.groupby(st.timestamp.dt.year).fundingRate.mean()*3*365*100).round(1).to_dict(),'neg%',round((st.fundingRate<0).mean()*100,1),'neg% 2025+',round((st[st.timestamp>='2025'].fundingRate<0).mean()*100,1))
print('--- cada parametro completo: exceso, sharpe, ultimos 24m')
for k,r in runs.items():print(k,round(X.ann(r.daily)*100,2),round(X.sharpe365(r.daily),2),round(X.ann(r.daily[r.daily.index>=r.daily.index.max()-pd.DateOffset(months=24)])*100,2))
e=X.ann(d);print('quiebra: prob anual de equilibrio perdiendo 100%',round(e*100,2))
print('--- 1000 USD: bruto',round(1000*X.ann(gross),0),'exceso',round(1000*e,0))
# sensibilidad comisiones bajas y dejar de cobrar
X.ONE_WAY_B=X.ONE_WAY
for ow in (0.0006,0.0019,0.004):
    X.ONE_WAY=ow;t,_,_=X.evaluate(B,nv);print('costo una via pb',ow*1e4,'sharpe',round(t['sharpe'],2),'exceso',round(t['annual_return']*100,2),'ok',t['ok'])
X.ONE_WAY=X.ONE_WAY_B
