import re, numpy as np, pandas as pd, wf, lab
from strategy import NY
D='data'
EARN = re.compile(r"earnings|EPS|Q[1-4] (results|revenue|sales)|quarterly (results|revenue)|reports? (first|second|third|fourth)[- ]quarter|guidance", re.I)

def load_news(sym):
    n = pd.read_csv(f"{D}/{sym}_news.csv")
    n["time"] = pd.to_datetime(n["time"], utc=True, format="mixed")
    n = n.sort_values("time")
    return n

def attach(df, n, minutes):
    """news24/earn24 = headlines in the 24h before each bar CLOSES (no peeking)."""
    tc = (df.index + pd.Timedelta(minutes=minutes)).values.astype("datetime64[ns]")
    t = n["time"].values.astype("datetime64[ns]")
    te = n.loc[n.headline.fillna("").str.contains(EARN), "time"].values.astype("datetime64[ns]")
    day = np.timedelta64(24, "h")
    df = df.copy()
    df["news24"] = np.searchsorted(t, tc, "right") - np.searchsorted(t, tc - day, "right")
    df["earn24"] = np.searchsorted(te, tc, "right") - np.searchsorted(te, tc - day, "right")
    return df

def attach2(df, n, minutes):
    df = attach(df, n, minutes)
    tc = (df.index + pd.Timedelta(minutes=minutes)).values.astype("datetime64[ns]")
    t = n["time"].values.astype("datetime64[ns]")
    df["fresh"] = np.searchsorted(t, tc, "right") - np.searchsorted(t, tc - np.timedelta64(4, "h"), "right")
    daily = n.groupby(n.time.dt.date).size()
    base = max(1.0, daily.reindex(pd.date_range(n.time.min().date(), n.time.max().date()).date, fill_value=0).mean())
    df["burst"] = (df["news24"] >= 2 * base).astype(int)
    return df
