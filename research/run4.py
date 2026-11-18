import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, wf, lab, newsexp, os
from datetime import date
wf.init(newsexp.D)
syms=[s for s in wf.symbols() if os.path.exists(f"{newsexp.D}/{s}_news.csv") and len(pd.read_csv(f"{newsexp.D}/{s}_news.csv"))>30]
START, MID, END = date(2026,4,30), date(2026,8,8), date(2026,11,18)
D={}
for s in syms:
    n=newsexp.load_news(s)
    for m in (5,15): D[(s,m)]=newsexp.attach2(wf.DATA[(s,m)], n, m)
base={"EMA":dict(strategy='ema',minutes=5,stop=0.01,target=0.02),
      "ORB":dict(strategy='orb',minutes=5,orb_minutes=30,orb_cutoff=120,stop=0.01,target=0.02),
      "MeanRev":dict(strategy='meanrev',minutes=15,mr_std=2.0,mr_rsi_max=30,stop=0.01,target=0.02)}
modes=[None,"req_fresh","avoid_fresh","req_burst","avoid_burst","avoid_earn"]
print("stocks:", syms)
for name,p in base.items():
    print(f"\n{name}:  {'news mode':<12} {'1st half':>9} {'2nd half':>9} {'trades':>7}")
    for m in modes:
        q={**p,"news":m}; halves=[]; ntr=0
        for a,b in ((START,MID),(MID,END)):
            rs=[]
            for s in syms:
                df=lab.by_date(D[(s,p['minutes'])],a,b)
                r,n,_=lab.backtest(df,q,wf.MKT.get(p['minutes'])); rs.append(r); ntr+=n
            halves.append(np.mean(rs))
        print(f"        {str(m or 'off'):<12} {halves[0]:>+9.2%} {halves[1]:>+9.2%} {ntr:>7}")
