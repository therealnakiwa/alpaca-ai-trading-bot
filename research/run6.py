import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, itertools, wf, lab, newsexp
exec(open(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)),"run4.py")).read().split("base={")[0])
def trailing_burst(mult, window=30):
    for s in syms:
        n=newsexp.load_news(s)
        days=pd.date_range(n.time.min().date(), END)
        daily=n.groupby(n.time.dt.tz_convert(None).dt.normalize()).size().reindex(days, fill_value=0)
        base=daily.rolling(window, min_periods=10).mean().shift(1).clip(lower=1.0)   # only past days
        for m in (5,15):
            df=D[(s,m)]
            b=base.reindex(df.index.tz_convert(None).normalize()).to_numpy()
            df["burst"]=((df["news24"].to_numpy()>=mult*np.nan_to_num(b,nan=np.inf))).astype(int)
for mult in (1.5,2,3):
    trailing_burst(mult)
    res=[];pers={}
    for om,stop,rr,cut in itertools.product((15,30),(0.005,0.01,0.02),(1.5,2,3),(120,240)):
        p=dict(strategy='orb',minutes=5,orb_minutes=om,orb_cutoff=cut,stop=stop,target=round(stop*rr,4),news="req_burst")
        h=[];ntr=0
        for a,b in ((START,MID),(MID,END)):
            rs=[lab.backtest(lab.by_date(D[(s,5)],a,b),p) for s in syms]
            h.append(np.mean([x[0] for x in rs])); ntr+=sum(x[1] for x in rs)
        res.append((h[0],h[1],ntr,(om,stop,rr,cut)))
    a=np.array([(x[0],x[1],x[2]) for x in res])
    both=((a[:,0]>0)&(a[:,1]>0)).mean()
    print(f"ORB + burst {mult}x (trailing baseline): positive both halves {both:.0%} | median 1st {np.median(a[:,0]):+.2%} 2nd {np.median(a[:,1]):+.2%} | avg trades {a[:,2].mean():.0f}")
    if mult==2:
        for x in sorted(res,key=lambda x:-(x[0]+x[1]))[:3]: print(f"     {x[0]:+.2%} {x[1]:+.2%} trades {x[2]} settings(range,stop,rr,cutoff)={x[3]}")
        p=dict(strategy='orb',minutes=5,orb_minutes=30,orb_cutoff=120,stop=0.01,target=0.02,news="req_burst")
        per={s:sum(lab.backtest(lab.by_date(D[(s,5)],a,b),p)[0] for a,b in ((START,MID),(MID,END))) for s in syms}
        print("     per stock (30m,1%,2:1,120m):", {k:f"{v:+.1%}" for k,v in sorted(per.items(),key=lambda x:-x[1])})
for strat,p in {"EMA":dict(strategy='ema',minutes=5,stop=0.01,target=0.02),"MeanRev":dict(strategy='meanrev',minutes=15,mr_std=2.0,mr_rsi_max=30,stop=0.01,target=0.02)}.items():
    trailing_burst(2)
    h=[np.mean([lab.backtest(lab.by_date(D[(s,p['minutes'])],a,b),{**p,"news":"req_burst"})[0] for s in syms]) for a,b in ((START,MID),(MID,END))]
    print(f"{strat} + burst 2x: {h[0]:+.2%} / {h[1]:+.2%}")
