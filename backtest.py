"""Backtest the strategy on historical Alpaca data.

Example:  python backtest.py --symbol SPY --days 60 --cash 10000
"""
import argparse
import os
from datetime import datetime, timedelta, timezone

import pandas as pd

import config
from strategy import NY, compute_signals, describe, position_size, regular_hours, warmup_bars

SLIPPAGE = 0.0005   # 0.05% worse fill on every entry and exit


def load_bars(symbol: str, days: int, minutes: int = None) -> pd.DataFrame:
    from alpaca.data.enums import DataFeed
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    client = StockHistoricalDataClient(config.API_KEY, config.SECRET_KEY)
    end = datetime.now(timezone.utc) - timedelta(minutes=20)
    req = StockBarsRequest(symbol_or_symbols=symbol,
                           timeframe=TimeFrame(minutes or config.BAR_MINUTES, TimeFrameUnit.Minute),
                           start=end - timedelta(days=days), end=end, feed=DataFeed.IEX)
    df = client.get_stock_bars(req).df.xs(symbol, level="symbol")
    return regular_hours(df)


def run_backtest(df: pd.DataFrame, cash: float, params: dict = None):
    p = {**config.strategy_params(), **(params or {})}
    df, buy_sig, sell_sig = compute_signals(df, p)
    o, h, l, c = (df[k].to_numpy() for k in ("open", "high", "low", "close"))
    days = df.index.tz_convert(NY).date
    times = df.index
    n = len(df)
    start_cash = cash
    pos = None          # dict(qty, entry, stop, target, time)
    trades, curve = [], []

    def close(i, price, reason):
        nonlocal cash, pos
        fill = price * (1 - SLIPPAGE)
        cash += pos["qty"] * fill
        trades.append({"entry_time": pos["time"], "exit_time": times[i], "qty": pos["qty"],
                       "entry": round(pos["entry"], 2), "exit": round(fill, 2),
                       "pnl": round(pos["qty"] * (fill - pos["entry"]), 2), "reason": reason})
        pos = None

    warmup = min(warmup_bars(p), max(n - 1, 0))
    for i in range(warmup, n):
        last_of_day = i == n - 1 or days[i + 1] != days[i]

        if pos:
            # stop checked before target = conservative assumption
            if l[i] <= pos["stop"]:
                close(i, min(o[i], pos["stop"]), "stop")
            elif h[i] >= pos["target"]:
                close(i, max(o[i], pos["target"]), "target")
            elif last_of_day:
                close(i, c[i], "end of day")
            elif sell_sig[i]:
                close(i + 1, o[i + 1], "exit signal")

        elif not last_of_day and buy_sig[i]:
            entry = o[i + 1] * (1 + SLIPPAGE)
            qty = position_size(cash, entry, cash, p["risk"], p["stop"], p["max_pos"])
            if qty > 0:
                cash -= qty * entry
                pos = {"qty": qty, "entry": entry, "time": times[i + 1],
                       "stop": entry * (1 - p["stop"]), "target": entry * (1 + p["target"])}

        curve.append(cash + (pos["qty"] * c[i] if pos else 0))

    if pos:
        close(n - 1, c[-1], "end of data")
        curve[-1] = cash

    trades = pd.DataFrame(trades, columns=["entry_time", "exit_time", "qty", "entry", "exit", "pnl", "reason"])
    equity = pd.Series(curve, dtype=float)
    drawdown = (equity / equity.cummax() - 1).min() if len(equity) else 0.0
    stats = {
        "trades": len(trades),
        "win_rate": (trades.pnl > 0).mean() if len(trades) else 0.0,
        "total_pnl": trades.pnl.sum() if len(trades) else 0.0,
        "return": cash / start_cash - 1,
        "max_drawdown": drawdown,
        "buy_and_hold": c[-1] / c[min(warmup, n - 1)] - 1 if n else 0.0,
    }
    return stats, trades


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="SPY")
    p.add_argument("--days", type=int, default=60)
    p.add_argument("--cash", type=float, default=10_000)
    args = p.parse_args()
    args.symbol = args.symbol.strip().upper()
    if not args.symbol.replace(".", "").isalnum():
        raise SystemExit(f"'{args.symbol}' is not a valid ticker. Try SPY, AAPL, TSLA...")

    df = load_bars(args.symbol, args.days)
    stats, trades = run_backtest(df, args.cash)

    print(f"\nBacktest {args.symbol} | {args.days} days | {config.BAR_MINUTES}-min bars | "
          f"{describe(config.strategy_params())}")
    print(f"  Trades:        {stats['trades']}")
    print(f"  Win rate:      {stats['win_rate']:.1%}")
    print(f"  Total P&L:     ${stats['total_pnl']:,.2f}")
    print(f"  Return:        {stats['return']:+.2%}")
    print(f"  Max drawdown:  {stats['max_drawdown']:.2%}")
    print(f"  Buy & hold:    {stats['buy_and_hold']:+.2%}  <- the bar to beat")

    os.makedirs("logs", exist_ok=True)
    out = f"logs/backtest_{args.symbol}.csv"
    trades.to_csv(out, index=False)
    print(f"  Trade list saved to {out}\n")


if __name__ == "__main__":
    main()
