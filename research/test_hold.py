from daily import *
# ---- where do the returns come from? ----
intraday = (C / O - 1)                       # buy open, sell close
overnight = (O / C.shift(1) - 1)             # buy close, sell next open
bh = C.pct_change()
header("1) WHERE THE MONEY IS (equal-weight across all 20 stocks, before costs)")
stats(bh.mean(axis=1), "Buy & hold (always own them)")
stats(intraday.mean(axis=1), "Only during market hours (day trading)")
stats(overnight.mean(axis=1), "Only overnight (close -> next open)")
header("   ...same, after paying 0.05% per buy and per sell")
stats(intraday.mean(axis=1) - 2*COST, "Day trading every day", trades=len(C)*20)
stats(overnight.mean(axis=1) - 2*COST, "Overnight every day", trades=len(C)*20)

# ---- swing versions: hold for days ----
def run_positions(pos, name):
    """pos[t]=1 means hold that stock from close t to close t+1. Pays cost on every change."""
    pos = pos.fillna(0)
    ret = (pos.shift(1) * bh).fillna(0)
    changes = pos.diff().abs().fillna(pos.abs())
    net = ret - changes.shift(1).fillna(0) * COST
    stats(net.mean(axis=1), name, trades=changes.sum().sum())
header("2) SWING TRADING: same ideas, held for days (after costs)")
stats(bh.mean(axis=1), "Buy & hold all 20 (the bar to beat)", trades=20)
for n in (20, 50):
    run_positions((C > C.rolling(n).mean()).astype(float).where(C.rolling(n).mean().notna()), f"Trend: own while price > {n}-day average")
fast, slow = C.ewm(span=10).mean(), C.ewm(span=30).mean()
run_positions((fast > slow).astype(float), "Trend: 10/30-day EMA crossover")
# classic short-term mean reversion: RSI(2) < 10 buy, sell when close > 5-day average
d = C.diff(); up = d.clip(lower=0).ewm(alpha=1/2).mean(); dn = (-d.clip(upper=0)).ewm(alpha=1/2).mean()
rsi2 = 100 - 100/(1+up/dn)
pos = pd.DataFrame(0.0, index=C.index, columns=C.columns); hold = pd.Series(0.0, index=C.columns)
sma5 = C.rolling(5).mean()
for t in C.index:
    hold = hold.where(~(C.loc[t] > sma5.loc[t]), 0.0)
    hold = hold.where(~(rsi2.loc[t] < 10), 1.0)
    pos.loc[t] = hold
run_positions(pos, "Dip-buy: RSI(2)<10, sell above 5-day avg")
