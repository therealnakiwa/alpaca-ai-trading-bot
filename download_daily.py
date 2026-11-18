"""Download ~10 years of DAILY bars (split/dividend adjusted) for the swing-trading research.

Example:  python download_daily.py --start 2016-01-01
Saves data/daily/<SYMBOL>_1d.csv
"""
import argparse
import os
from datetime import datetime, timedelta, timezone

from alpaca.data.enums import Adjustment, DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

import config

UNIVERSE = [
    # broad + sector ETFs
    "SPY", "QQQ", "IWM", "DIA", "XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLU",
    # large, established companies across sectors
    "AAPL", "MSFT", "AMZN", "GOOGL", "META", "NVDA", "TSLA", "AMD", "INTC", "CSCO", "ORCL", "CRM",
    "ADBE", "QCOM", "TXN", "IBM", "NFLX", "JPM", "BAC", "WFC", "GS", "V", "MA", "JNJ", "PFE", "UNH",
    "MRK", "ABBV", "LLY", "PG", "KO", "PEP", "WMT", "COST", "HD", "MCD", "NKE", "DIS", "XOM", "CVX",
    "CAT", "BA", "GE", "MMM", "HON", "UPS", "T", "VZ",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="+", default=UNIVERSE)
    ap.add_argument("--start", default="2016-01-01")
    args = ap.parse_args()

    client = StockHistoricalDataClient(config.API_KEY, config.SECRET_KEY)
    start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
    end = datetime.now(timezone.utc) - timedelta(minutes=20)
    os.makedirs("data/daily", exist_ok=True)

    for sym in args.symbols:
        df = None
        for feed in (DataFeed.SIP, DataFeed.IEX):     # SIP = full market history; IEX as fallback
            try:
                req = StockBarsRequest(symbol_or_symbols=sym, timeframe=TimeFrame.Day, start=start,
                                       end=end, adjustment=Adjustment.ALL, feed=feed)
                df = client.get_stock_bars(req).df.xs(sym, level="symbol")
                break
            except Exception as e:
                err = e
        if df is None or df.empty:
            print(f"{sym:6} FAILED: {err}")
            continue
        df.to_csv(f"data/daily/{sym}_1d.csv")
        print(f"{sym:6} {len(df):>5} days  {df.index[0].date()} -> {df.index[-1].date()}  ({feed.value})")
    print("\nDone. Tell Claude the daily data is downloaded.")


if __name__ == "__main__":
    main()
