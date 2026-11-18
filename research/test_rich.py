import daily
from daily import *
bh=C.pct_change()
wild=["MARA","COIN","SMCI","SOFI","PLTR","NFLX"]; calm=[s for s in C.columns if s not in wild]
d=C.diff(); up=d.clip(lower=0).ewm(alpha=1/2).mean(); dn=(-d.clip(upper=0)).ewm(alpha=1/2).mean(); rsi2=100-100/(1+up/dn)
sma5=C.rolling(5).mean()
MARGIN_RATE=0.06   # ASSUMPTION: ~6%/yr interest on borrowed money (check your broker's real rate)
def book(side, cols, K, lev, stop=0.08):
    """side=+1 long dip-buys (RSI2<10), -1 short pops (RSI2>90). Max K positions, each lev/K of equity."""
    W=pd.DataFrame(0.0,index=C.index,columns=cols); held={}; 
    for t in C.index:
        px=C.loc[t,cols]
        for s in list(held):
            e=held[s]; out = (px[s]>sma5.loc[t,s]) if side>0 else (px[s]<sma5.loc[t,s])
            hit = (px[s]<e*(1-stop)) if side>0 else (px[s]>e*(1+stop))
            if out or hit: del held[s]
        r=rsi2.loc[t,cols]
        cands=(r[r<10].sort_values() if side>0 else r[r>90].sort_values(ascending=False)).index
        for s in cands:
            if len(held)>=K: break
            if s not in held: held[s]=px[s]
        for s in held: W.loc[t,s]=side*lev/K
    return W
def run(W,name):
    ret=(W.shift(1)*bh[W.columns]).sum(axis=1)
    turn=W.diff().abs().sum(axis=1).fillna(W.abs().sum(axis=1))
    borrowed=(W.clip(lower=0).sum(axis=1)-1).clip(lower=0)            # longs above 100% of equity
    shorts=W.clip(upper=0).abs().sum(axis=1)
    net=ret-turn.shift(1).fillna(0)*COST-borrowed.shift(1).fillna(0)*MARGIN_RATE/252-shorts.shift(1).fillna(0)*0.01/252
    stats(net,name); return net
header("MILLIONAIRE LEVERS (14 calmer stocks, 8% stops, after costs + margin interest)")
stats(bh[calm].mean(axis=1),"Buy & hold the 14")
for lev in (1.0,1.5,2.0):
    run(book(+1,calm,5,lev), f"Long dip-buy, max 5, {lev:.1f}x money")
run(book(-1,calm,5,1.0), "Short the pops only (RSI2>90), max 5, 1x")
L=book(+1,calm,5,1.0); S=book(-1,calm,5,1.0)
run(L.add(S,fill_value=0), "Long dips + short pops together, 1x each")
L2=book(+1,calm,5,1.5); S2=book(-1,calm,5,0.5)
run(L2.add(S2,fill_value=0), "Long 1.5x + short 0.5x")
