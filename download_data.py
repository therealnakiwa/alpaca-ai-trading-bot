"""Download historical 5-minute bars to the data/ folder as CSV files.

Lets you (or Claude) run lots of experiments without re-downloading every time.
Example:  python download_data.py --days 365
"""
import argparse
import os

from backtest import load_bars

DEFAULT_SYMBOLS = ["SPY", "QQQ", "IWM", "DIA", "AAPL", "MSFT", "NVDA", "TSLA", "AMD", "META",
                   "AMZN", "GOOGL", "NFLX", "COIN", "PLTR", "MARA", "SOFI", "SMCI", "XLE", "XLF"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    ap.add_argument("--days", type=int, default=365)
    args = ap.parse_args()

    os.makedirs("data", exist_ok=True)
    for sym in args.symbols:
        sym = sym.strip().upper()
        try:
            df = load_bars(sym, args.days, 5)
            path = f"data/{sym}_5min.csv"
            df.to_csv(path)
            print(f"{sym:6} {len(df):>7,} bars  {df.index[0].date()} -> {df.index[-1].date()}  saved {path}")
        except Exception as e:
            print(f"{sym:6} FAILED: {e}")
    print("\nDone. Tell Claude the data is downloaded.")


if __name__ == "__main__":
    main()
