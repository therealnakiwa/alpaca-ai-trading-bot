"""Daily swing backtester: RSI(2) dip-buy, max K positions, leverage, stops, crash protection."""
import glob, os, numpy as np, pandas as pd
COST = 0.0005; MARGIN = 0.06

def load_daily(d):
    C, O = {}, {}
    for f in sorted(glob.glob(f"{d}/*_1d.csv")):
        s = os.path.basename(f).split("_")[0]
        df = pd.read_csv(f, index_col=0); df.index = pd.to_datetime(df.index, utc=True).tz_convert(None).normalize()
        C[s] = df["close"]; O[s] = df["open"]
    return pd.DataFrame(C).sort_index(), pd.DataFrame(O).sort_index()

def rsi(C, n=2):
    d = C.diff(); up = d.clip(lower=0).ewm(alpha=1/n).mean(); dn = (-d.clip(upper=0)).ewm(alpha=1/n).mean()
    return 100 - 100 / (1 + up / dn)

def run(C, cols, K=5, lev=1.0, th=10, exit_n=5, stop=0.08, trend_filter=False, vol_target=None,
        dd_breaker=None, cash_days=20):
    """Returns daily net returns of the portfolio. Signals at close t, held from close t to close t+1.
    trend_filter: only open new longs while SPY > its 200-day average.
    vol_target:   scale leverage down when SPY's 20-day volatility (annualized) exceeds this.
    dd_breaker:   if equity falls this far below its peak, go to cash for `cash_days` days."""
    R = rsi(C[cols]); sma = C[cols].rolling(exit_n).mean(); ret = C.pct_change()
    spy = C["SPY"]; spy_ok = spy > spy.rolling(200).mean()
    spy_vol = ret["SPY"].rolling(20).std() * np.sqrt(252)
    held = {}; out = []; eq = 1.0; peak = 1.0; cooldown = 0; prev_w = pd.Series(0.0, index=cols)
    dates = C.index
    for i, t in enumerate(dates[:-1]):
        px = C.loc[t, cols]
        for s in list(held):
            if px[s] > sma.loc[t, s] or px[s] < held[s] * (1 - stop) or np.isnan(px[s]): del held[s]
        L = lev
        if vol_target and spy_vol.loc[t] > 0: L = min(lev, lev * vol_target / spy_vol.loc[t])
        allow_new = cooldown == 0 and (not trend_filter or bool(spy_ok.loc[t]))
        if cooldown > 0:
            held = {}; cooldown -= 1
        if allow_new:
            r = R.loc[t]; cands = r[(r < th) & px.notna()].sort_values().index
            for s in cands:
                if len(held) >= K: break
                if s not in held: held[s] = px[s]
        w = pd.Series(0.0, index=cols)
        for s in held: w[s] = L / K
        nxt = ret.loc[dates[i + 1], cols].fillna(0)
        gross = (w * nxt).sum()
        cost = (w - prev_w).abs().sum() * COST
        interest = max(0.0, w.sum() - 1) * MARGIN / 252
        r_net = gross - cost - interest
        eq *= 1 + r_net; peak = max(peak, eq); prev_w = w
        if dd_breaker and eq < peak * (1 - dd_breaker) and cooldown == 0:
            cooldown = cash_days; peak = eq
        out.append((dates[i + 1], r_net, w.sum()))
    o = pd.DataFrame(out, columns=["date", "ret", "exposure"]).set_index("date")
    return o

def report(o, name, bench=None):
    eq = (1 + o.ret).cumprod(); dd = (eq / eq.cummax() - 1)
    yrs = (o.index[-1] - o.index[0]).days / 365.25
    cagr = eq.iloc[-1] ** (1 / yrs) - 1
    yearly = (1 + o.ret).groupby(o.index.year).prod() - 1
    worst_month = ((1 + o.ret).groupby([o.index.year, o.index.month]).prod() - 1).min()
    return dict(name=name, cagr=cagr, total=eq.iloc[-1] - 1, maxdd=dd.min(), worst_month=worst_month,
                exposure=o.exposure.mean(), yearly=yearly)
