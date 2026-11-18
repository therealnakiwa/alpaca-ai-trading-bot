"""Research harness: walk-forward tests across many symbols with extra filters and trailing stops.
Reuses the bot's strategy code so anything found here can go straight into the bot."""
import sys, itertools, glob, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np, pandas as pd
from strategy import compute_signals, resample, NY, OPEN_MIN, position_size, warmup_bars

SLIP = 0.0005

def load(path):
    df = pd.read_csv(path, index_col=0)
    df.index = pd.to_datetime(df.index, utc=True)
    return df[["open", "high", "low", "close", "volume"]]

def add_filters(df, buy, p, market=None):
    ny = df.index.tz_convert(NY); mins = np.asarray(ny.hour * 60 + ny.minute)
    ok = np.ones(len(df), bool)
    if p.get("skip_open", 0):
        ok &= mins >= OPEN_MIN + p["skip_open"]
    if p.get("last_entry", 0):
        ok &= mins < OPEN_MIN + p["last_entry"]
    if p.get("mkt") and market is not None:
        # market filter: SPY above its own open for the day at this bar
        m = market.reindex(df.index)
        up = m["above_open"].astype(float).fillna(0).to_numpy().astype(bool)
        ok &= up if p["mkt"] == "up" else ~up
    nm = p.get("news")
    if nm:
        col = {"fresh": "fresh", "burst": "burst", "earn": "earn24"}[nm.split("_")[1]]
        has = df[col].to_numpy() > 0
        ok &= has if nm.startswith("req") else ~has
    if p.get("relvol", 0):
        rv = df["relvol"] if "relvol" in df else relvol(df)
        ok &= rv.fillna(0).to_numpy() >= p["relvol"]
    return buy & ok

def relvol(df):
    """Volume so far today vs the average volume by this time of day over the prior 20 days."""
    ny = df.index.tz_convert(NY); mins = ny.hour * 60 + ny.minute
    day = pd.Series(ny.date, index=df.index)
    cum = df["volume"].groupby(day).cumsum()
    key = pd.Series(np.asarray(mins), index=df.index)
    hist = cum.groupby(key).transform(lambda s: s.shift(1).rolling(20, min_periods=5).mean())
    return cum / hist

def market_frame(spy):
    ny = spy.index.tz_convert(NY); day = pd.Series(ny.date, index=spy.index)
    day_open = spy["open"].groupby(day).transform("first")
    return pd.DataFrame({"above_open": spy["close"] > day_open})

def backtest(df, p, market=None, cash=10_000):
    d, buy, sell = compute_signals(df, p)
    buy = add_filters(d, buy, p, market)
    o, h, l, c = (d[k].to_numpy() for k in ("open", "high", "low", "close"))
    days = np.asarray(d.index.tz_convert(NY).date)
    n = len(d); start = cash; pos = None; pnls = []; trail = p.get("trail", 0)
    def close(price):
        nonlocal cash, pos
        f = price * (1 - SLIP); cash += pos[0] * f; pnls.append(pos[0] * (f - pos[1])); pos = None
    for i in range(min(warmup_bars(p), max(n - 1, 0)), n):
        lod = i == n - 1 or days[i + 1] != days[i]
        if pos:
            qty, entry, stop, tgt = pos
            if l[i] <= stop: close(min(o[i], stop))
            elif tgt and h[i] >= tgt: close(max(o[i], tgt))
            elif lod: close(c[i])
            elif p["strategy"] != "orb" and sell[i]: close(o[i + 1])
            elif trail:
                pos[2] = max(stop, h[i] * (1 - trail))
        elif not lod and buy[i]:
            e = o[i + 1] * (1 + SLIP)
            q = position_size(cash, e, cash, 0.01, p["stop"], 0.20)
            if q:
                cash -= q * e
                pos = [q, e, e * (1 - p["stop"]), (e * (1 + p["target"]) if p["target"] else 0)]
    if pos: close(c[-1])
    return cash / start - 1, len(pnls), (np.array(pnls) > 0).mean() if pnls else 0.0

def by_date(df, a, b):
    d = np.asarray(df.index.tz_convert(NY).date)
    return df[(d >= a) & (d < b)]
