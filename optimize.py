"""Find settings that work on past data, then check them on newer data they never saw.

How it works:
  1. Download ~120 days of 5-minute bars for each symbol.
  2. Split by date: the older 70% is TRAIN, the newest 30% is TEST.
  3. For each strategy (ema, orb, meanrev), try every combination of settings on TRAIN.
  4. Run the top few of each strategy on TEST. Only TEST results tell you if a setting is real.

Example:  python optimize.py --symbols SPY TSLA NVDA --days 120
          python optimize.py --symbols TSLA --strategies orb meanrev
"""
import argparse
import itertools
import os

import pandas as pd

import config
from backtest import load_bars, run_backtest
from strategy import NY, describe, resample

# ---- the settings it tries for each strategy (edit these lists to explore) ----
GRIDS = {
    "ema": {
        "minutes": [5, 15],
        "ema": [(5, 13), (9, 21), (12, 26), (20, 50)],
        "rsi_max": [70, 100],                       # 100 = RSI filter off
        "stop": [0.003, 0.005, 0.01],
        "reward_ratio": [1.5, 2.0, 3.0],            # target = stop x this
    },
    "orb": {
        "minutes": [5, 15],
        "orb_minutes": [15, 30],
        "orb_cutoff": [60, 120, 240],
        "stop": [0.003, 0.005, 0.01],
        "reward_ratio": [1.5, 2.0, 3.0],
    },
    "meanrev": {
        "minutes": [5, 15],
        "mr_std": [1.5, 2.0, 2.5],
        "mr_rsi_max": [30, 40, 100],
        "stop": [0.005, 0.01, 0.02],
        "reward_ratio": [1.0, 2.0, 3.0],
    },
}
MIN_TRAIN_TRADES = 10    # ignore settings that barely traded (luck, not skill)
MIN_TEST_TRADES = 5


def split_by_date(df: pd.DataFrame, train_frac: float):
    dates = pd.Index(df.index.tz_convert(NY).date)
    unique = sorted(set(dates))
    cutoff = unique[int(len(unique) * train_frac)]
    return df[dates < cutoff], df[dates >= cutoff], cutoff


def combos(strategy: str):
    grid = GRIDS[strategy]
    for values in itertools.product(*grid.values()):
        c = dict(zip(grid, values))
        if "ema" in c:
            c["fast"], c["slow"] = c.pop("ema")
        c["target"] = round(c["stop"] * c.pop("reward_ratio"), 4)
        c["strategy"] = strategy
        yield c


def to_params(c) -> dict:
    """Clean a result row into backtest params (ints stay ints)."""
    p = {}
    for k, v in dict(c).items():
        if k in ("strategy",):
            p[k] = v
        elif k in ("fast", "slow", "orb_minutes", "orb_cutoff", "minutes") and pd.notna(v):
            p[k] = int(v)
        elif k in ("stop", "target", "rsi_max", "mr_std", "mr_rsi_max") and pd.notna(v):
            p[k] = float(v)
    return p


def config_snippet(c, symbol) -> str:
    p = to_params(c)
    lines = [f'SYMBOLS = ["{symbol}"]', f'BAR_MINUTES = {p["minutes"]}', f'STRATEGY = "{p["strategy"]}"']
    if p["strategy"] == "ema":
        lines += [f'FAST_EMA = {p["fast"]}', f'SLOW_EMA = {p["slow"]}', f'RSI_MAX_ENTRY = {int(p["rsi_max"])}']
    elif p["strategy"] == "orb":
        lines += [f'ORB_MINUTES = {p["orb_minutes"]}', f'ORB_CUTOFF_MINUTES = {p["orb_cutoff"]}']
    else:
        lines += [f'MR_STD = {p["mr_std"]}', f'MR_RSI_MAX = {int(p["mr_rsi_max"])}']
    lines += [f'STOP_LOSS_PCT = {p["stop"]}', f'TAKE_PROFIT_PCT = {p["target"]}']
    return "\n".join("    " + l for l in lines)


def pct(x):
    return f"{x:+.2%}"


def evaluate_strategy(strategy, splits, cash, top):
    rows = []
    for c in combos(strategy):
        train, _, _ = splits[c["minutes"]]
        s, _ = run_backtest(train, cash, to_params(c))
        rows.append({**c, "train_return": s["return"], "train_trades": s["trades"],
                     "train_win": s["win_rate"], "train_bh": s["buy_and_hold"]})
    res = pd.DataFrame(rows)
    res = res[res.train_trades >= MIN_TRAIN_TRADES].sort_values("train_return", ascending=False)
    best = res.head(top).copy()
    for idx, row in best.iterrows():
        _, test, _ = splits[int(row.minutes)]
        s, _ = run_backtest(test, cash, to_params(row))
        best.loc[idx, ["test_return", "test_trades", "test_win", "test_bh"]] = [
            s["return"], s["trades"], s["win_rate"], s["buy_and_hold"]]
    return best, len(res)


def verdict(best) -> tuple:
    """Returns (label, message, passing_rows)."""
    if best.empty:
        return "NO DATA", "No setting made enough trades to judge.", best
    if (best.train_return <= 0).all():
        return "NO EDGE", "Even the best settings lost money on TRAIN. TEST results would be noise.", best.iloc[0:0]
    good = best[(best.train_return > 0) & (best.test_trades >= MIN_TEST_TRADES)]
    held = good[(good.test_return > 0) & (good.test_return > good.test_bh)]
    if len(held):
        return "PROMISING", (f"{len(held)} setting(s) made money on TRAIN, stayed profitable on TEST "
                             f"({MIN_TEST_TRADES}+ trades) and beat buy & hold."), held
    if len(good) and (good.test_return > 0).any():
        return "WEAK", "Made money on TEST but didn't beat buy & hold.", best.iloc[0:0]
    if len(good) == 0:
        return "TOO FEW TRADES", f"Fewer than {MIN_TEST_TRADES} TEST trades. Try --days 200.", best.iloc[0:0]
    return "FAILED", "Best TRAIN settings lost money on TEST (fitted to luck).", best.iloc[0:0]


def optimize_symbol(symbol, days, train_frac, cash, top, strategies):
    raw = load_bars(symbol, days, 5)
    if raw.empty:
        print(f"{symbol}: no data returned, skipping")
        return [], []
    bars = {5: raw, 15: resample(raw, 15)}
    splits = {m: split_by_date(df, train_frac) for m, df in bars.items()}
    cutoff = splits[5][2]
    _, test5, _ = splits[5]
    train5 = splits[5][0]
    bh_tr = train5.close.iloc[-1] / train5.close.iloc[0] - 1
    bh_te = test5.close.iloc[-1] / test5.close.iloc[0] - 1

    print(f"\n{'=' * 84}\n{symbol}   TRAIN = before {cutoff}   TEST = {cutoff} onward   "
          f"Buy & hold: train {pct(bh_tr)}  test {pct(bh_te)}\n{'=' * 84}")

    all_rows, summary = [], []
    for strat in strategies:
        best, n_ok = evaluate_strategy(strat, splits, cash, top)
        label, msg, passing = verdict(best)
        print(f"\n[{strat.upper()}]  {n_ok} settings had enough trades")
        if not best.empty:
            print(f"{'#':>2} {'bars':>4}  {'setting':<36} {'stop':>6} {'target':>6} | "
                  f"{'TRAIN':>8} {'trd':>4} | {'TEST':>8} {'trd':>4} {'win%':>5}")
            for n, (_, r) in enumerate(best.iterrows(), 1):
                print(f"{n:>2} {int(r.minutes):>3}m  {describe(to_params(r)):<36} "
                      f"{r.stop:>6.2%} {r.target:>6.2%} | {pct(r.train_return):>8} {int(r.train_trades):>4} | "
                      f"{pct(r.test_return):>8} {int(r.test_trades):>4} {r.test_win:>5.0%}")
        print(f"   -> {label}: {msg}")
        for _, r in passing.iterrows():
            summary.append((symbol, r))
        best = best.copy()
        best.insert(0, "symbol", symbol)
        best["verdict"] = label
        all_rows.append(best)
    return all_rows, summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="+", default=["SPY", "QQQ", "AAPL", "TSLA", "NVDA"])
    ap.add_argument("--strategies", nargs="+", default=list(GRIDS), choices=list(GRIDS))
    ap.add_argument("--days", type=int, default=120)
    ap.add_argument("--train", type=float, default=0.7, help="fraction of days used to train")
    ap.add_argument("--cash", type=float, default=10_000)
    ap.add_argument("--top", type=int, default=3, help="settings per strategy to check on TEST")
    args = ap.parse_args()

    rows, winners = [], []
    for sym in args.symbols:
        sym = sym.strip().upper()
        if not sym.replace(".", "").isalnum():
            print(f"Skipping '{sym}' (not a ticker)")
            continue
        print(f"\nDownloading and testing {sym}...")
        r, w = optimize_symbol(sym, args.days, args.train, args.cash, args.top, args.strategies)
        rows += r
        winners += w

    os.makedirs("logs", exist_ok=True)
    rows = [r for r in rows if not r.empty]
    (pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()).to_csv(
        "logs/optimize_results.csv", index=False)

    print(f"\n{'#' * 84}\nSUMMARY")
    if not winners:
        print("Nothing passed. No strategy showed an edge that held up on unseen data.\n"
              "Don't trade real money on any of these. Try other symbols or more days.")
    else:
        winners.sort(key=lambda w: w[1].test_return, reverse=True)
        print(f"{len(winners)} setting(s) passed. Best first. To use one, paste its lines into config.py:\n")
        for sym, r in winners[:5]:
            print(f"  {sym}  {describe(to_params(r))}  |  TRAIN {pct(r.train_return)}  "
                  f"TEST {pct(r.test_return)} ({int(r.test_trades)} trades)")
            print(config_snippet(r, sym) + "\n")
        print("Passing once is not proof. Paper trade it for a few weeks before trusting it.")
    print("Full results saved to logs/optimize_results.csv\n")


if __name__ == "__main__":
    main()
