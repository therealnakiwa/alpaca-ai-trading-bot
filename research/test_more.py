import daily
from daily import *
bh=C.pct_change()
wild=["MARA","COIN","SMCI","SOFI","PLTR","NFLX"]; calm=[s for s in C.columns if s not in wild]
d=C.diff(); up=d.clip(lower=0).ewm(alpha=1/2).mean(); dn=(-d.clip(upper=0)).ewm(alpha=1/2).mean(); rsi2=100-100/(1+up/dn)
sma5=C.rolling(5).mean()
def signals(cols):
    pos=pd.DataFrame(0.0,index=C.index,columns=cols); hold=pd.Series(0.0,index=cols); entry=pd.Series(np.nan,index=cols)
    for t in C.index:
        px=C.loc[t,cols]; ex=(px>sma5.loc[t,cols])|(px<entry*0.92)
        hold=hold.where(~(ex&(hold>0)),0.0); new=(rsi2.loc[t,cols]<10)&(hold==0)
        entry=entry.where(~new,px); hold=hold.where(~new,1.0); pos.loc[t]=hold
    return pos
pos=signals(calm)
def run(w, name):
    """w = portfolio weights per day (rows sum <= 1). Returns are close-to-close; cost on weight changes."""
    ret=(w.shift(1)*bh[w.columns]).sum(axis=1); turn=w.diff().abs().sum(axis=1).fillna(w.sum(axis=1))
    net=ret-turn.shift(1).fillna(0)*COST; stats(net,name,trades=None); return net
header("USING THE IDLE MONEY (14 calmer stocks, 8% stop, after costs)")
stats(bh[calm].mean(axis=1),"Buy & hold the 14")
stats(bh["SPY"],"Buy & hold SPY")
n=len(calm)
run(pos/n, "A) Dip-buy, 1/14 per stock (77% sits idle)")
# B) idle money in SPY
w=pos/n; w=w.copy(); w["SPY"]=w.get("SPY",0)+(1-w.sum(axis=1))
run(w, "B) Dip-buy + idle money parked in SPY")
# C) concentrate: up to K positions, each 1/K of the account (most oversold first)
for K in (3,5):
    W=pd.DataFrame(0.0,index=C.index,columns=calm); held=[]
    for t in C.index:
        held=[s for s in held if pos.loc[t,s]>0]
        cands=[s for s in rsi2.loc[t,calm].sort_values().index if pos.loc[t,s]>0 and s not in held]
        held+=cands[:max(0,K-len(held))]
        for s in held: W.loc[t,s]=1.0/K
    run(W, f"C) Dip-buy, max {K} at a time, 1/{K} each")
    W2=W.copy(); W2["SPY"]=W2.get("SPY",0)+(1-W2.sum(axis=1))
    run(W2, f"D) Same as C{K} + idle money in SPY")
