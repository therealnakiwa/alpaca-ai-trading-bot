"""Download a year of news headlines for every stock in data/ (or the ones you name).

Example:  python download_news.py --days 365
Saves data/<SYMBOL>_news.csv, one row per headline.
"""
import argparse
import glob
import os
from datetime import datetime, timedelta, timezone

import pandas as pd

from news import fetch_news


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="+")
    ap.add_argument("--days", type=int, default=365)
    args = ap.parse_args()

    symbols = args.symbols or sorted(os.path.basename(f).split("_")[0]
                                     for f in glob.glob("data/*_5min.csv"))
    if not symbols:
        raise SystemExit("No symbols. Run 6_download_data.bat first, or pass --symbols.")

    os.makedirs("data", exist_ok=True)
    end = datetime.now(timezone.utc)
    for sym in symbols:
        sym = sym.strip().upper()
        rows, t = [], end - timedelta(days=args.days)
        try:
            while t < end:                       # one month at a time
                t2 = min(t + timedelta(days=30), end)
                rows += fetch_news(sym, t, t2)
                t = t2
            df = pd.DataFrame(rows, columns=["time", "headline", "source", "symbols", "summary"])
            df = df.drop_duplicates(subset=["time", "headline"])
            df.to_csv(f"data/{sym}_news.csv", index=False)
            print(f"{sym:6} {len(df):>6,} headlines saved")
        except Exception as e:
            print(f"{sym:6} FAILED: {e}")
    print("\nDone. Tell Claude the news is downloaded.")


if __name__ == "__main__":
    main()
