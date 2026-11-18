import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, wf
from strategy import NY
COST = 0.0005  # per side, same as the intraday tests
wf.init('data')
syms = wf.symbols()
O, C = {}, {}
for s in syms:
    df = wf.DATA[(s,5)]
    day = df.index.tz_convert(NY).date
    g = df.groupby(day)
    O[s] = g["open"].first(); C[s] = g["close"].last()
O = pd.DataFrame(O); C = pd.DataFrame(C)
O.index = pd.to_datetime(O.index); C.index = pd.to_datetime(C.index)
O, C = O.ffill(), C.ffill()
def stats(daily_ret, name, trades=None):
    eq = (1 + daily_ret.fillna(0)).cumprod()
    dd = (eq / eq.cummax() - 1).min()
    h = len(daily_ret)//2
    r1 = (1+daily_ret.iloc[:h].fillna(0)).prod()-1; r2 = (1+daily_ret.iloc[h:].fillna(0)).prod()-1
    t = f"{trades:>6.0f}" if trades is not None else "     -"
    print(f"{name:<44} {eq.iloc[-1]-1:>+8.1%} {r1:>+8.1%} {r2:>+8.1%} {dd:>8.1%} {t}")
def header(title):
    print(f"\n{title}\n{'':<44} {'total':>8} {'1st half':>8} {'2nd half':>8} {'max DD':>8} {'trades':>6}")
