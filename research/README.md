# Research scripts

Every experiment from the main README. Run them **from the repo root** after downloading data (see the main README).

| Script | What it tests |
|---|---|
| `lab.py`, `wf.py` | Shared engine: fast backtests with filters/trailing stops, walk-forward (tune on the past, score on the next unseen period) |
| `run1.py` | 3 intraday strategies, same settings on all 20 stocks, walk-forward |
| `run2.py` | Same, plus market-trend, relative-volume, skip-the-open and trailing-stop filters |
| `run3.py` | Each stock picks its own settings |
| `newsexp.py`, `run4.py` | News features (fresh news, news bursts, earnings headlines) as trade filters |
| `run6.py` | News-burst test rebuilt **without look-ahead** (trailing 30-day baseline) |
| `daily.py`, `test_hold.py` | Daily bars: where returns come from (overnight vs intraday) and swing strategies |
| `test_rsi2.py` | Stress test of the RSI(2) dip-buy: neighbor settings, per-stock, higher costs |
| `test_mom.py` | Dip-buy safety variants and momentum rotation |
| `test_more.py`, `test_rich.py` | Position concentration, idle cash, leverage, shorting |
| `swing.py`, `crash_test.py` | 10-year daily test (2016–2026) with leverage and crash protection |

All tests charge 0.05% slippage per side. Intraday data is Alpaca's free IEX feed, which covers only part of total market volume.
