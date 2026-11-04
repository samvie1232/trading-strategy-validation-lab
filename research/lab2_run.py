"""Corre las hipótesis preregistradas. Con datos reales:
  XM_SWAP_MODEL=legacy_fixed XM_OUT_DIR=output_lab2 python lab2_run.py   (tal como se preregistró)
"""
import json
import config as C
import lab2 as X,numpy as np,pandas as pd,metrics as M
from data import load_specs
d=C.DATA_DIR;out=C.OUT_DIR;out.mkdir(exist_ok=True);sp=load_specs(d);F=list(X.GRID)
print('swap',C.SWAP_MODEL)
B={f:X.load_family(f,d,sp) for f in F}
nv=X.null_var(B,F,[1,2,3])
res={};full={};W={}
for f in F:
    st,wf,runs,fl=X.evaluate(f,B[f]);st['_daily']=wf.oos_daily;res[f]=st;W[f]=wf;full[f]=fl
    pd.DataFrame(wf.windows).to_csv(out/f'{f}_windows.csv',index=False);wf.oos_daily.to_csv(out/f'{f}_oos_daily.csv')
    print(f,'sharpe OOS',round(st['sharpe'],2),flush=True)
allsr=[v for f in F for v in full[f].values()];rv=float(np.var(allsr,ddof=1))
print('var nula',nv,'var real',rv,'n',len(allsr))
rows=[];detail={}
for f in F:
    st=res[f];ch=X.verdict(st,nv);d_s=X.dsr(st['_daily'],rv)
    extra=None
    if f in('H4','H5'):
        wf=W[f];ps=[]
        for p_s in pd.Series(wf.chosen).value_counts().index[:1]:
            p=json.loads(p_s)
            rs=pd.concat([X.h4(b,p,1.0,True) for b in B[f].values()]);rs=rs[rs.index>=wf.oos_daily.index.min()]
            dist=[]
            for k,b in enumerate(B[f].values()):
                dist.append(X.h4_random(b,p,max(len(rs)//2,50),2000,123+k))
            rd=np.mean(dist,axis=0);extra=dict(param=p,meanR=float(rs.mean()),rand_p95=float(np.percentile(rd,95)),rand_mean=float(rd.mean()),pct=float((rd<rs.mean()).mean()))
        ch.append(('Mejor que azar (p95)',f"{extra['meanR']:.3f}R vs p95 {extra['rand_p95']:.3f}R",extra['meanR']>extra['rand_p95']))
    ap=all(c for _,_,c in ch)
    rows.append(dict(fam=f,veredicto='APRUEBA' if ap else 'NO APRUEBA',oos=st['oos_start']+'→'+st['oos_end'],ops=st['trades'],sharpe=round(st['sharpe'],2),anual=round(st['annual_return']*100,1),dd=round(st['max_drawdown']*100,1),wfe=None if st['wfe']!=st['wfe'] else round(st['wfe'],2),pos=round(st['pct_positive_windows']*100),mc95=round(st.get('mc_p95_drawdown',np.nan)*100,1),estres=round(st['stress_sharpe'],2),sin_costo=round(st['zero_cost_sharpe'],2),dsr=round(st['dsr'],3),dsr_real=round(d_s,3),aciertos=round(st['win_rate']*100,1),pf=round(st['profit_factor'],2),is_anual=round(st['is_annual']*100,1),fallos=[n for n,_,c in ch if not c]))
    detail[f]=dict(checks=[(a,b,bool(c)) for a,b,c in ch],chosen=pd.Series(st['chosen']).value_counts().to_dict(),extra=extra)
T=pd.DataFrame(rows);pd.set_option('display.width',260,'display.max_columns',30,'display.max_colwidth',90);print(T.drop(columns='fallos').to_string(index=False))
for r in rows:print(r['fam'],r['veredicto'],r['fallos'])
print(json.dumps(detail,indent=0,default=str)[:6000])
T.to_csv(out/'resumen.csv',index=False)
print('--- Sharpe anual, muestra completa, cada intento')
for f in F:
    for k,v in full[f].items():print(f,k,round(v*np.sqrt(252),2))
# B&H H1 contexto
print('--- comprar y mantener con swap (OOS H1)')
oos0=res['H1']['_daily'].index.min()
for s,b in B['H1'].items():
    g=b.close.pct_change().fillna(0)+b.fin_long.fillna(0)*[X.nights(a,c) for a,c in zip(np.r_[b.index.values[0],b.index.values[:-1]],b.index.values)]
    g.index=g.index.normalize();g=g[g.index>=oos0];print(s,'sharpe',round(M.sharpe(g),2),'anual',round(M.annual_return(g)*100,1),'dd',round(M.max_drawdown(g)*100,1))
# por simbolo con el parametro mas elegido
print('--- por mercado, parametro mas elegido, solo OOS')
for f in F:
    if f=='H6':continue
    p=json.loads(pd.Series(res[f]['chosen']).value_counts().index[0]);o0=res[f]['_daily'].index.min()
    for s,b in B[f].items():
        r=X.FN[f](b,p,1.0);dd=r.daily[r.daily.index>=o0];t=r.trades[r.trades.index>=o0];print(f,p,s,'ops',len(t),'sharpe',round(M.sharpe(dd),2),'anual',round(M.annual_return(dd)*100,1),'aciertos',round((t>0).mean()*100,1))
