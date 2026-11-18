import daily
from daily import *
bh=C.pct_change()
# ---------- dip-buy safety variants ----------
def rsi_n(n):
    d=C.diff(); up=d.clip(lower=0).ewm(alpha=1/n).mean(); dn=(-d.clip(upper=0)).ewm(alpha=1/n).mean()
    return 100-100/(1+up/dn)
def dipbuy(cols, th=10, ex=5, stop=None, max_days=None):
    r=rsi_n(2)[cols]; sma=C[cols].rolling(ex).mean(); c=C[cols]
    pos=pd.DataFrame(0.0,index=C.index,columns=cols); entry=pd.Series(np.nan,index=cols); age=pd.Series(0,index=cols)
    for t in C.index:
        holding=pos.shift(1).loc[t].fillna(0) if False else None
    hold=pd.Series(0.0,index=cols)
    for t in C.index:
        px=c.loc[t]
        exitm=(px>sma.loc[t])
        if stop: exitm|=(px<entry*(1-stop))
        if max_days: exitm|=(age>=max_days)
        hold=hold.where(~(exitm&(hold>0)),0.0)
        new=(r.loc[t]<th)&(hold==0)
        entry=entry.where(~new,px); hold=hold.where(~new,1.0)
        age=(age+1).where(hold>0,0)
        pos.loc[t]=hold
    ret=(pos.shift(1)*bh[cols]).fillna(0); ch=pos.diff().abs().fillna(pos)
    net=(ret-ch.shift(1).fillna(0)*COST).mean(axis=1)
    return net, ch.sum().sum()/2
wild=["MARA","COIN","SMCI","SOFI","PLTR","NFLX"]
calm=[s for s in C.columns if s not in wild]
header("DIP-BUY SAFETY VARIANTS (RSI2<10, exit above 5-day avg)")
for name,cols,stop,md in [("All 20, no stop",list(C.columns),None,None),
                          ("All 20, 8% stop-loss",list(C.columns),0.08,None),
                          ("All 20, sell after 10 days max",list(C.columns),None,10),
                          ("14 calmer names only, no stop",calm,None,None),
                          ("14 calmer names, 8% stop",calm,0.08,None)]:
    net,tr=dipbuy(cols,stop=stop,max_days=md); stats(net,name,trades=tr)
stats(bh[calm].mean(axis=1),"Buy & hold, 14 calmer names")

# ---------- momentum rotation ----------
header("MOMENTUM ROTATION (weekly: own the top N by past return, after costs)")
stats(bh.mean(axis=1),"Buy & hold all 20 (whole year)")
fridays=C.index[pd.Series(C.index).dt.dayofweek.diff().fillna(-1).lt(0).shift(-1,fill_value=True).values]
for look in (21,63,126):
    for top in (3,5):
        mom=C/C.shift(look)-1
        w=pd.DataFrame(0.0,index=C.index,columns=C.columns); cur=pd.Series(0.0,index=C.columns)
        for t in C.index:
            if t in fridays and mom.loc[t].notna().sum()>=10:
                best=mom.loc[t].nlargest(top).index; cur=pd.Series(0.0,index=C.columns); cur[best]=1.0/top
            w.loc[t]=cur
        start=mom.dropna(how="all").index[0]
        ret=(w.shift(1)*bh).sum(axis=1); turn=w.diff().abs().sum(axis=1).fillna(0)
        net=(ret-turn.shift(1).fillna(0)*COST).loc[start:]
        stats(net,f"Top {top} by {look}-day return",trades=(w.diff().abs()>0).sum().sum())
        if look==63 and top==3: print(f"{'':<44} (compare: buy & hold same period {(1+bh.mean(axis=1).loc[start:]).prod()-1:+.1%})")
