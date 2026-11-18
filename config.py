"""All the knobs for the bot in one place. Change values here, not in bot.py."""
import os

from dotenv import load_dotenv

from security import load_credentials

load_dotenv()  # reads your .env file

# --- Credentials (never hard-code these) ---
# Looked up in the OS credential store first (python security.py --set-keys), then .env as a fallback.
API_KEY, SECRET_KEY, CREDENTIAL_SOURCE = load_credentials()
PAPER = os.getenv("ALPACA_PAPER", "true").lower() == "true"

# --- What to trade ---
SYMBOLS = ["MARA"]               # paper-test pick from the intraday research
BAR_MINUTES = 15                # candle size

# --- Which strategy: "ema", "orb" or "meanrev" ---
STRATEGY = "meanrev"

# ema: EMA crossover with an RSI filter
FAST_EMA = 9
SLOW_EMA = 21
RSI_PERIOD = 14
RSI_MAX_ENTRY = 70              # don't buy when already overbought (100 = off)

# orb: opening range breakout
ORB_MINUTES = 30                # opening range = first 30 minutes of the day
ORB_CUTOFF_MINUTES = 120        # only take breakouts within 2 hours of the open

# meanrev: mean reversion
MR_PERIOD = 20                  # bars in the moving average
MR_STD = 1.5                    # buy when price is this many std devs below it
MR_RSI_MAX = 30                 # ...and RSI is below this (100 = off)

# --- Live news check (runs every time a buy signal fires) ---
# "off"     = just log the latest headlines, trade as normal
# "require" = only buy if the stock had news in the lookback window
# "avoid"   = skip the buy if the stock had news in the lookback window
NEWS_MODE = "off"
NEWS_LOOKBACK_HOURS = 24

# --- Risk management ---
RISK_PER_TRADE = 0.01           # risk 1% of equity per trade (distance to stop)
STOP_LOSS_PCT = 0.02            # stop 2% below entry
TAKE_PROFIT_PCT = 0.04          # target 4% above entry
MAX_POSITION_PCT = 0.20         # never put more than 20% of equity in one symbol
MAX_DAILY_LOSS_PCT = 0.03       # down 3% on the day -> flatten everything and stop
MAX_TRADES_PER_DAY = 10
FLATTEN_MINUTES_BEFORE_CLOSE = 10   # day trader: no overnight positions

# --- Security guardrails (checked before EVERY order, independent of the strategy) ---
ALLOWED_SYMBOLS = None              # None = only the symbols in SYMBOLS may ever be traded
MAX_ORDER_QTY = 2000                # shares per order
MAX_ORDER_NOTIONAL = 25_000         # $ per order
MAX_DAILY_NOTIONAL = 250_000        # $ of buys per day
MAX_ORDERS_PER_MINUTE = 5           # more than this = runaway loop -> kill switch
ORDER_ID_PREFIX = "jbot"            # tags every order so outside activity can be detected
HALT_ON_FOREIGN_ACTIVITY = True     # stop opening trades if orders/positions appear that the bot didn't make
REQUIRE_CODE_INTEGRITY = True       # refuse to start if the code changed since `security.py --approve`

# --- Loop / safety ---
LOOP_SECONDS = 60
KILL_SWITCH_FILE = "STOP"       # create a file named STOP to flatten and quit
LOG_DIR = "logs"


def strategy_params() -> dict:
    """Everything above, in the format strategy.compute_signals() expects."""
    return {"strategy": STRATEGY, "fast": FAST_EMA, "slow": SLOW_EMA, "rsi_period": RSI_PERIOD,
            "rsi_max": RSI_MAX_ENTRY, "orb_minutes": ORB_MINUTES, "orb_cutoff": ORB_CUTOFF_MINUTES,
            "mr_period": MR_PERIOD, "mr_std": MR_STD, "mr_rsi_max": MR_RSI_MAX,
            "stop": STOP_LOSS_PCT, "target": TAKE_PROFIT_PCT, "risk": RISK_PER_TRADE,
            "max_pos": MAX_POSITION_PCT}
