"""Strategy logic, shared by the live bot, the backtester and the optimizer so they always agree.

Three strategies (all long-only, all flat by end of day):
  ema      - trend: buy when the fast EMA crosses above the slow EMA (RSI filter), sell on cross back down
  orb      - opening range breakout: buy the first close above the high of the first N minutes of the day
  meanrev  - mean reversion: buy when price drops K standard deviations below its average (RSI oversold),
             sell when it gets back to the average
"""
import numpy as np
import pandas as pd

NY = "America/New_York"
OPEN_MIN = 9 * 60 + 30          # 9:30 New York, in minutes after midnight


# ---------------- indicators ----------------
def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss
    return 100 - 100 / (1 + rs)


# ---------------- data helpers ----------------
def regular_hours(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only 9:30-16:00 New York bars (drops pre/post-market)."""
    idx = df.index.tz_convert(NY)
    mins = idx.hour * 60 + idx.minute
    return df[(mins >= OPEN_MIN) & (mins < 16 * 60)]


def resample(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """Turn smaller candles into bigger ones (e.g. 5-min -> 15-min)."""
    out = df.resample(f"{minutes}min", origin="start_day", offset="30min").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
    return out.dropna(subset=["open"])


# ---------------- signals ----------------
DEFAULTS = {
    "strategy": "ema",
    # ema
    "fast": 9, "slow": 21, "rsi_period": 14, "rsi_max": 70,
    # orb
    "orb_minutes": 30, "orb_cutoff": 120,
    # meanrev
    "mr_period": 20, "mr_std": 2.0, "mr_rsi_max": 30,
    # exits / sizing
    "stop": 0.01, "target": 0.02, "risk": 0.01, "max_pos": 0.20,
}


def warmup_bars(p: dict) -> int:
    """How many bars an indicator needs before its signals mean anything."""
    p = {**DEFAULTS, **p}
    if p["strategy"] == "ema":
        return int(p["slow"])
    if p["strategy"] == "meanrev":
        return int(max(p["mr_period"], p["rsi_period"]))
    return 1


def compute_signals(df: pd.DataFrame, params: dict):
    """Return (df_with_indicators, buy, sell): buy/sell are boolean arrays, one per bar.
    The live bot looks at the last element; the backtester walks through all of them."""
    p = {**DEFAULTS, **params}
    df = df.copy()
    close = df["close"]
    n = len(df)
    sell = np.zeros(n, dtype=bool)

    if p["strategy"] == "ema":
        df["ema_fast"] = ema(close, int(p["fast"]))
        df["ema_slow"] = ema(close, int(p["slow"]))
        df["rsi"] = rsi(close, int(p["rsi_period"]))
        diff = (df["ema_fast"] - df["ema_slow"]).to_numpy()
        prev = np.r_[np.nan, diff[:-1]]
        buy = (prev <= 0) & (diff > 0) & (df["rsi"].to_numpy() < p["rsi_max"])
        sell = (prev >= 0) & (diff < 0)

    elif p["strategy"] == "orb":
        ny = df.index.tz_convert(NY)
        mins = np.asarray(ny.hour * 60 + ny.minute)
        day = pd.Series(ny.date, index=df.index)
        range_end = OPEN_MIN + int(p["orb_minutes"])
        in_range = mins < range_end
        range_high = df["high"].where(in_range).groupby(day).transform("max")
        df["orb_high"] = range_high
        after = (mins >= range_end) & (mins < OPEN_MIN + int(p["orb_cutoff"]))
        above = (close > range_high).to_numpy()
        prev_above = (pd.Series(above, index=df.index).groupby(day).shift(1)
                      .fillna(False).astype(bool).to_numpy())
        cross = after & above & ~prev_above
        # only the FIRST breakout of each day counts
        first = pd.Series(cross, index=df.index).groupby(day).cumsum().to_numpy() == 1
        buy = cross & first

    elif p["strategy"] == "meanrev":
        period = int(p["mr_period"])
        mean = close.rolling(period).mean()
        sd = close.rolling(period).std()
        df["mr_mean"] = mean
        df["mr_z"] = (close - mean) / sd
        df["rsi"] = rsi(close, int(p["rsi_period"]))
        buy = ((df["mr_z"] < -p["mr_std"]) & (df["rsi"] < p["mr_rsi_max"])).to_numpy()
        sell = (close >= mean).to_numpy()

    else:
        raise ValueError(f"Unknown strategy '{p['strategy']}' (use ema, orb or meanrev)")

    return df, np.asarray(buy, dtype=bool), np.asarray(sell, dtype=bool)


def describe(p: dict) -> str:
    """Short human-readable summary of a setting."""
    p = {**DEFAULTS, **p}
    s = p["strategy"]
    if s == "ema":
        return f"EMA {int(p['fast'])}/{int(p['slow'])} rsi<{'off' if p['rsi_max'] >= 100 else int(p['rsi_max'])}"
    if s == "orb":
        return f"ORB first {int(p['orb_minutes'])}m, buy until +{int(p['orb_cutoff'])}m"
    return (f"MeanRev {int(p['mr_period'])}bar -{p['mr_std']}sd "
            f"rsi<{'off' if p['mr_rsi_max'] >= 100 else int(p['mr_rsi_max'])}")


# ---------------- sizing ----------------
def position_size(equity: float, price: float, buying_power: float,
                  risk_per_trade: float, stop_pct: float, max_position_pct: float) -> int:
    """Shares to buy so that hitting the stop loses ~risk_per_trade of equity,
    capped by max position size and available buying power."""
    if price <= 0:
        return 0
    by_risk = (equity * risk_per_trade) / (price * stop_pct)
    by_cap = (equity * max_position_pct) / price
    by_bp = buying_power / price
    return max(0, int(min(by_risk, by_cap, by_bp)))
