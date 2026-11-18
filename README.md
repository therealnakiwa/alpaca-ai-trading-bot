# Alpaca AI Trading Bot: Building a Day-Trading Bot and Testing It Honestly

A Python trading bot for the [Alpaca](https://alpaca.markets) API, with live paper trading, a tested security layer, risk controls, a backtester, a walk-forward optimizer, a real-time news check, and a research suite that tests the strategies across **20 intraday stocks and 60 stocks/ETFs over 10 years**.

**The headline result:** none of the strategies beat simply holding an index fund over 10 years. The project shows how I found that out, including two of my own testing mistakes that made losing strategies look like winners, and how I caught them.

> Educational project. Not financial advice. Defaults to paper trading (fake money).

---

## TL;DR results

| What I tested | Result |
|---|---|
| 3 intraday strategies (EMA crossover, opening range breakout, mean reversion) on 20 stocks, walk-forward | **All lost money** on unseen data |
| Same, plus filters (market trend, volume, skip the open, trailing stops) | Lost less, **still lost** |
| Same, plus real-time news filters (Benzinga headlines) | Looked profitable, **until I found a look-ahead bug**. After fixing it, no edge |
| Daily "dip-buy" swing strategy, 1 year | **+9.7%** vs buy & hold −0.1%. Looked great |
| Same dip-buy, **10 years (2016–2026)** | **+7.1%/yr vs +14.8%/yr for SPY**. Lost to the index |
| Dip-buy with 2× leverage, 10 years | Worst drawdown **−78%** |

**Lesson:** a strategy that looks great on one year of data can lose badly over ten. Testing on unseen data and long histories is the whole game.

---

## What the bot does

```
 Alpaca market data ─┐
 Alpaca news feed ───┼──> strategy.py ──> risk checks ──> bracket order ──> Alpaca (paper)
                     │    (signals)       (size, limits,    (stop-loss +
                     │                     news check)       take-profit)
                     └──> logs/bot.log  <── every decision, headline and trade
```

- **3 strategies, one shared code path:** the live bot, backtester and optimizer all call the same `compute_signals()`, so a backtest tests exactly what trades live.
  - `ema`: EMA crossover with an RSI filter (trend following)
  - `orb`: opening range breakout
  - `meanrev`: buy when price is K standard deviations below its average
- **Risk management:**
  - every entry is a **bracket order** (stop-loss + take-profit live at the broker, so positions stay protected if the bot crashes)
  - position sizing by risk (about 1% of equity per trade), capped per symbol
  - **max daily loss** limit: flattens everything and stops
  - max trades per day
  - flattens before the close (no overnight risk)
- **Real-time news check:** before every buy, pulls the stock's recent headlines, logs them, and can require or avoid news (`NEWS_MODE`).
- **Backtester** with slippage, and an **optimizer** that tunes on older data (TRAIN) and judges only on newer, unseen data (TEST).

## Security design

Built by a cybersecurity student, so the bot is threat-modeled like any system that holds credentials and can move money. All controls live in [`security.py`](security.py) and are covered by **24 automated tests** ([`tests/`](tests/)).

| Threat | Control |
|---|---|
| API keys stolen from a plaintext file | Keys stored in the **OS credential store** (Windows Credential Manager / macOS Keychain) via `keyring`; `.env` is only a fallback, and the bot logs which source it used |
| Keys leaking into logs or screenshots | A **redacting log filter** masks the actual keys and anything shaped like an Alpaca key in every log line |
| Keys pushed to GitHub | [`scan_secrets.py`](scan_secrets.py) scans everything git would upload (and can install itself as a **pre-commit hook** that blocks the commit); `.env` is git-ignored |
| A bug, bad config or tampered strategy placing huge or runaway orders | **OrderGuard**, enforced before *every* order regardless of strategy code: symbol allowlist, max shares, max $ per order, max $ per day, and a **rate limit** that trips the kill switch if orders fire in a loop |
| Someone else trading with your keys | Every bot order carries a tagged `client_order_id`. Orders or positions the bot didn't create raise a **security alert** and **halt new trading** |
| Code tampered with on disk | A SHA-256 **integrity manifest** of the bot's code, signed with an HMAC key kept in the credential store. The bot **refuses to start** if any file changed, was added or deleted since you approved it |
| Logs edited to hide what happened | A **tamper-evident audit log**: each entry's HMAC covers the previous entry, so edited, reordered or deleted lines are detected (`security.py --verify-audit`) |
| Accidentally trading real money | Paper trading by default; live trading needs both `ALPACA_PAPER=false` **and** `CONFIRM_LIVE=yes` |
| Losses compounding while unattended | Broker-side stop-loss/take-profit (bracket orders), max daily loss, max trades/day, flatten before close, and a `STOP`-file kill switch |

**Design choices worth noting**
- **Defense in depth:** the OrderGuard doesn't trust the strategy. Even if strategy code is wrong or modified, order size and frequency are capped in a separate layer.
- **Fail-safe vs. fail-open:** security failures stop trading (integrity mismatch, rate limit, foreign activity), while non-critical failures (the news API) degrade gracefully.
- **Secrets never in the repo:** the HMAC key, keys and integrity manifest are per-machine and git-ignored.
- **Known limitation:** someone with full control of the machine *and* access to the credential store could defeat these checks. They raise the bar and make tampering detectable; they don't replace OS-level security.

### Security setup
```bash
python security.py --set-keys       # store keys in the OS credential store (input hidden)
python security.py --approve        # trust the current code; re-run after reviewing any change
python scan_secrets.py --install-hook   # after `git init`: block commits containing keys
python -m pytest -q                 # run the security test suite
python security.py --verify-audit   # check the audit log for tampering
```
On Windows: `9_security_setup.bat` and `10_security_check.bat`.

---

## The research, step by step

All tests include **0.05% slippage per side**. Research scripts are in [`research/`](research/).

### 1. Intraday strategies: no edge
Walk-forward test on 20 stocks, 1 year of 5-minute bars. Settings picked on earlier months, then scored on the next 3 unseen months, three times over:

| Strategy | Return on unseen data (avg per stock) |
|---|---|
| EMA crossover | −0.73% |
| Opening range breakout | −1.11% |
| Mean reversion | −0.65% |

Letting each stock choose its own settings didn't help: two stocks (MARA, SMCI) looked good, which is about what luck predicts across 60 stock/strategy combinations.

### 2. Why it loses: costs on a coin flip

| Strategy | With costs | If trading were free | Trades/stock/yr |
|---|---|---|---|
| EMA | −7.60% | −0.79% | 386 |
| ORB | −1.60% | +0.21% | 101 |
| Mean reversion | −1.40% | +0.18% | 84 |

Before costs the strategies are roughly break-even, i.e. no real predictive power. Costs on hundreds of trades turn that into a steady loss. Splitting returns showed **all of the year's gains came overnight**; during market hours the stocks lost 5.4% before costs.

### 3. News filters, and the bug I caught
"Only trade during a news burst (≥2× normal headline volume)" first looked like the breakthrough: 1 in 3 settings profitable in both halves of the period, vs 0 without news.

Then I noticed "normal headline volume" was averaged over the **whole** period, so the backtest knew the future. Rebuilt with a trailing 30-day baseline (what a live bot actually knows), that dropped to **6%**. **The edge was a look-ahead bug.**

### 4. Holding for days instead of minutes
A classic daily dip-buy (buy when 2-day RSI < 10, sell when price closes above its 5-day average) over the last year:
- **+9.7%** vs −0.1% buy & hold
- all 15 nearby parameter settings profitable
- 16 of 20 stocks profitable
- survived 4× the trading costs

Every sign of a real edge, on one year of data.

### 5. The 10-year test that settled it
60 stocks and ETFs, daily bars 2016–2026, including the 2018 selloff, the 2020 crash and the 2022 bear market:

| Strategy | Per year | Worst drawdown |
|---|---|---|
| **Buy & hold SPY** | **+14.8%** | −33.8% |
| Buy & hold all 60 (equal weight) | +18.5% | −32.6% |
| Dip-buy, 1× | +7.1% | −47.7% |
| Dip-buy, 2× leverage | +5.7% | **−78.0%** |
| Dip-buy, 2× + trend filter + volatility control + drawdown breaker | +3.4% | −46.4% |

The great year was a favorable stretch. The strategy lost 23% in 2018 and 15% in 2022, and leverage turned those years into near-wipeouts. (These results also carry **survivorship bias**: the 60 stocks are today's successful companies, which flatters every strategy, buy & hold included.)

### What I learned
1. **Test on data the strategy has never seen.** In-sample results are always flattering.
2. **Check your own tests for look-ahead bias.** My most exciting result came from a backtest that could see the future.
3. **Costs decide everything for high-frequency strategies.** A coin flip with fees is a slow loss.
4. **One good year proves nothing.** Test across crashes and bear markets.
5. **Leverage magnifies whatever you have**, including no edge.
6. **Beating a low-cost index fund is genuinely hard,** which is why most professionals don't.

---

## Project structure

```
bot.py              live trading loop (paper by default)
strategy.py         indicators + the 3 strategies (shared by everything)
config.py           every setting: symbols, strategy, risk limits, news mode
news.py             Alpaca/Benzinga news: live checks + history
security.py         credential store, order guard, integrity check, audit log
scan_secrets.py     blocks API keys from being pushed to GitHub
tests/              security test suite (pytest)
backtest.py         single-symbol backtest with slippage
optimize.py         TRAIN/TEST optimizer across strategies and symbols
download_*.py       pull 5-min bars, daily bars and news into data/
research/           every experiment from the write-up above
*.bat               Windows double-click launchers
```

## Setup

1. Create a free [Alpaca](https://alpaca.markets) account and generate **paper trading** API keys.
2. Install:
   ```bash
   python -m venv venv
   # Windows: venv\Scripts\activate    Mac/Linux: source venv/bin/activate
   pip install -r requirements.txt
   ```
   (On Windows you can instead double-click `1_setup.bat`.)
3. Store your keys: `python security.py --set-keys` (or copy `.env.example` to `.env` as a fallback).
4. Approve the code: `python security.py --approve`. The bot won't start until you do.

## Usage

```bash
python backtest.py --symbol SPY --days 60                 # test the current config
python optimize.py --symbols SPY TSLA NVDA --days 120     # TRAIN/TEST across all strategies
python bot.py                                             # paper trade (Ctrl+C to stop, STOP file to flatten)
```

To reproduce the research, download data, then run any script in `research/` from the repo root:

```bash
python download_data.py --days 365          # 5-min bars  -> data/
python download_news.py --days 365          # headlines   -> data/
python download_daily.py --start 2016-01-01 # daily bars  -> data/daily/
python research/crash_test.py               # the 10-year test
```

## Built with
Python · pandas · NumPy · [alpaca-py](https://github.com/alpacahq/alpaca-py)

## Author
**Julian Barajas**, Cybersecurity, The University of Texas at San Antonio

---

*Disclaimer: for education and research only. Nothing here is financial advice. Trading involves risk of loss, and past or backtested performance does not guarantee future results.*
