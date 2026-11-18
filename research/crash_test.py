import warnings; warnings.filterwarnings("ignore")
import time, numpy as np, pandas as pd, swing
C, O = swing.load_daily('data/daily')
C = C.ffill()
cols = list(C.columns)
ret = C.pct_change()
def bench(series_ret, name):
    o = pd.DataFrame({"ret": series_ret.fillna(0), "exposure": 1.0}); return swing.report(o.iloc[200:], name)
rows = [bench(ret["SPY"], "Buy & hold SPY"), bench(ret[cols].mean(axis=1), "Buy & hold all 60 (equal)")]
configs = [
  ("Dip-buy 1x, no protection", dict(lev=1.0)),
  ("Dip-buy 2x, no protection", dict(lev=2.0)),
  ("Dip-buy 1x + trend filter", dict(lev=1.0, trend_filter=True)),
  ("Dip-buy 2x + trend filter", dict(lev=2.0, trend_filter=True)),
  ("Dip-buy 2x + trend + vol control", dict(lev=2.0, trend_filter=True, vol_target=0.15)),
  ("Dip-buy 2x + all 3 protections", dict(lev=2.0, trend_filter=True, vol_target=0.15, dd_breaker=0.15)),
  ("Dip-buy 1.5x + all 3 protections", dict(lev=1.5, trend_filter=True, vol_target=0.15, dd_breaker=0.15)),
]
for name, kw in configs:
    t = time.time(); o = swing.run(C, cols, K=5, **kw).iloc[199:]; rows.append(swing.report(o, name))
    print(f"ran {name} in {time.time()-t:.0f}s", flush=True)
pd.to_pickle(rows, "crash_rows.pkl")
print(f"\n{'':<36} {'per yr':>7} {'10-yr total':>11} {'worst drop':>10} {'worst month':>11} {'invested':>8}")
for r in rows:
    print(f"{r['name']:<36} {r['cagr']:>+7.1%} {r['total']:>+11.0%} {r['maxdd']:>10.1%} {r['worst_month']:>11.1%} {r['exposure']:>8.0%}")
print("\nYEAR BY YEAR")
yrs = rows[0]['yearly'].index
print(f"{'':<36}" + "".join(f"{y:>7}" for y in yrs))
for r in rows:
    print(f"{r['name']:<36}" + "".join(f"{r['yearly'].get(y,np.nan):>+7.0%}" for y in yrs))
