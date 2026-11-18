import daily
from daily import *
def rsi_n(n):
    d=C.diff(); up=d.clip(lower=0).ewm(alpha=1/n).mean(); dn=(-d.clip(upper=0)).ewm(alpha=1/n).mean()
    return 100-100/(1+up/dn)
def dipbuy(th=10, exit_n=5, rsi_len=2, cost=COST, stop=None):
    r=rsi_n(rsi_len); sma=C.rolling(exit_n).mean()
    pos=pd.DataFrame(0.0,index=C.index,columns=C.columns); hold=pd.Series(0.0,index=C.columns)
    for t in C.index:
        hold=hold.where(~(C.loc[t]>sma.loc[t]),0.0)
        hold=hold.where(~(r.loc[t]<th),1.0)
        pos.loc[t]=hold
    ret=(pos.shift(1)*bh).fillna(0); ch=pos.diff().abs().fillna(pos)
    net=ret-ch.shift(1).fillna(0)*cost
    eq=(1+net.mean(axis=1)).cumprod(); h=len(net)//2
    port=net.mean(axis=1)
    return dict(total=eq.iloc[-1]-1, h1=(1+port.iloc[:h]).prod()-1, h2=(1+port.iloc[h:]).prod()-1,
                dd=(eq/eq.cummax()-1).min(), trades=ch.sum().sum()/2, per=(1+net).prod()-1, exposure=pos.mean().mean(), pos=pos, net=net)
bh=C.pct_change()
rows=[]
for th in (5,10,15,20,30):
    for ex in (3,5,10):
        x=dipbuy(th,ex); rows.append((th,ex,x['total'],x['h1'],x['h2'],x['dd'],x['trades']))
r=pd.DataFrame(rows,columns=["rsi_below","exit_avg_days","total","h1","h2","maxDD","trades"])
print("NEIGHBOR SETTINGS (15 combos):"); print(r.to_string(index=False,formatters={k:"{:+.1%}".format for k in ["total","h1","h2","maxDD"]}))
print(f"-> positive in both halves: {((r.h1>0)&(r.h2>0)).sum()}/15")
base=dipbuy()
print(f"\nDEFAULT (RSI2<10, exit above 5-day avg): {base['total']:+.1%} | time in market {base['exposure']:.0%} | round trips {base['trades']:.0f}")
print("per stock:", {k:f"{v:+.0%}" for k,v in base['per'].sort_values(ascending=False).items()})
print(f"stocks profitable: {(base['per']>0).sum()}/20")
for c in (0.001,0.002):
    x=dipbuy(cost=c); print(f"with costs {c:.2%} per side: {x['total']:+.1%}")
# win rate & avg trade
pos=base['pos']; entries=(pos.diff()==1)
tr=[]
for s in C.columns:
    p=pos[s]; ins=list(p.index[(p.diff()==1)]); outs=list(p.index[(p.diff()==-1)])
    for i in ins:
        o=[x for x in outs if x>i]
        if o: tr.append(C[s][o[0]]/C[s][i]-1-2*COST)
tr=np.array(tr); print(f"trades {len(tr)} | win rate {np.mean(tr>0):.0%} | avg trade {tr.mean():+.2%} | avg win {tr[tr>0].mean():+.2%} | avg loss {tr[tr<=0].mean():+.2%} | worst {tr.min():+.1%}")
# hold length
lens=[]
for s in C.columns:
    p=pos[s].values; c=0
    for v in p:
        if v: c+=1
        elif c: lens.append(c); c=0
print(f"avg days held {np.mean(lens):.1f}")
