"""Live (paper) day-trading bot for Alpaca.

Run:   python bot.py
Stop:  Ctrl+C (open positions keep their stop-loss/take-profit orders)
Kill:  create a file named STOP in this folder -> flattens everything and exits
"""
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone

from alpaca.common.exceptions import APIError
from alpaca.data.enums import DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderClass, OrderSide, QueryOrderStatus, TimeInForce
from alpaca.trading.requests import (GetOrdersRequest, MarketOrderRequest,
                                     StopLossRequest, TakeProfitRequest)

import config
import security
from news import recent_headlines
from strategy import compute_signals, describe, position_size, regular_hours


def setup_logging() -> logging.Logger:
    os.makedirs(config.LOG_DIR, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s")
    log = logging.getLogger("bot")
    log.setLevel(logging.INFO)
    redact = security.RedactingFilter([config.API_KEY, config.SECRET_KEY])
    for handler in (logging.StreamHandler(sys.stdout),
                    logging.FileHandler(os.path.join(config.LOG_DIR, "bot.log"))):
        handler.setFormatter(fmt)
        handler.addFilter(redact)          # keys can never reach the screen or log file
        log.addHandler(handler)
    return log


log = setup_logging()


class Bot:
    def __init__(self):
        if not config.API_KEY or not config.SECRET_KEY:
            sys.exit("Missing Alpaca keys. Run `python security.py --set-keys` (or fill in .env).")
        if not config.PAPER and os.getenv("CONFIRM_LIVE") != "yes":
            sys.exit("ALPACA_PAPER=false but CONFIRM_LIVE=yes is not set. Refusing to trade real money.")
        if config.REQUIRE_CODE_INTEGRITY:
            problems = security.verify_code()
            if problems:
                for p in problems:
                    log.error(f"INTEGRITY: {p}")
                sys.exit("Refusing to start: code changed since it was approved. Review the changes, "
                         "then run `python security.py --approve`.")
        log.info(f"Credentials loaded from: {config.CREDENTIAL_SOURCE}")
        self.audit = security.AuditLog()
        self.allowed = config.ALLOWED_SYMBOLS or config.SYMBOLS
        self.guard = security.OrderGuard(self.allowed, config.MAX_ORDER_QTY, config.MAX_ORDER_NOTIONAL,
                                         config.MAX_DAILY_NOTIONAL, config.MAX_ORDERS_PER_MINUTE)
        self.known_symbols = set()      # positions this bot opened
        self.halted = False

        self.trading = TradingClient(config.API_KEY, config.SECRET_KEY, paper=config.PAPER)
        self.data = StockHistoricalDataClient(config.API_KEY, config.SECRET_KEY)
        self.timeframe = TimeFrame(config.BAR_MINUTES, TimeFrameUnit.Minute)
        self.trades_today = 0
        self.trade_day = None
        self.params = config.strategy_params()

    # ---------- data ----------
    def get_bars(self, symbol: str):
        now = datetime.now(timezone.utc)
        req = StockBarsRequest(symbol_or_symbols=symbol, timeframe=self.timeframe,
                               start=now - timedelta(days=5), feed=DataFeed.IEX)
        df = self.data.get_stock_bars(req).df
        if df.empty:
            return df
        df = df.xs(symbol, level="symbol")
        # drop the bar that's still forming so we only act on completed candles
        df = df[df.index <= now - timedelta(minutes=config.BAR_MINUTES)]
        return regular_hours(df)

    # ---------- orders ----------
    def open_orders(self):
        # nested=True: bracket legs sit under their parent, so only top-level orders are checked
        return self.trading.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN, nested=True))

    def cancel_orders_for(self, symbol: str):
        req = GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[symbol])
        for order in self.trading.get_orders(req):
            self.trading.cancel_order_by_id(order.id)

    def buy(self, symbol: str, price: float, equity: float, buying_power: float):
        qty = position_size(equity, price, buying_power, config.RISK_PER_TRADE,
                            config.STOP_LOSS_PCT, config.MAX_POSITION_PCT)
        if qty < 1:
            log.info(f"{symbol}: buy signal but position size is 0, skipping")
            return
        try:
            self.guard.check(symbol, qty, price)
        except security.SecurityBlock as e:
            log.error(f"SECURITY BLOCK {symbol}: {e}")
            self.audit.write("order_blocked", symbol=symbol, qty=qty, price=price, reason=str(e))
            if "rate limit" in str(e):
                self.flatten("order rate limit tripped")
                sys.exit("Stopped: order rate limit tripped (possible runaway loop).")
            return
        order_id = security.new_order_id(config.ORDER_ID_PREFIX)
        order = MarketOrderRequest(
            symbol=symbol, qty=qty, side=OrderSide.BUY, time_in_force=TimeInForce.DAY,
            client_order_id=order_id, order_class=OrderClass.BRACKET,
            take_profit=TakeProfitRequest(limit_price=round(price * (1 + config.TAKE_PROFIT_PCT), 2)),
            stop_loss=StopLossRequest(stop_price=round(price * (1 - config.STOP_LOSS_PCT), 2)),
        )
        self.trading.submit_order(order)
        self.known_symbols.add(symbol)
        self.audit.write("buy", symbol=symbol, qty=qty, price=price, order_id=order_id)
        self.trades_today += 1
        log.info(f"{symbol}: BUY {qty} @ ~{price:.2f} (stop -{config.STOP_LOSS_PCT:.1%}, "
                 f"target +{config.TAKE_PROFIT_PCT:.1%}) | trades today {self.trades_today}")

    def sell(self, symbol: str):
        self.cancel_orders_for(symbol)          # release shares held by the bracket legs
        time.sleep(1)
        self.trading.close_position(symbol)
        self.known_symbols.discard(symbol)
        self.audit.write("sell", symbol=symbol, reason="exit signal")
        log.info(f"{symbol}: SELL (exit signal), position closed")

    def news_ok(self, symbol: str) -> bool:
        """Real-time news check before a buy. Always logs headlines; blocks per NEWS_MODE."""
        try:
            heads = recent_headlines(symbol, config.NEWS_LOOKBACK_HOURS)
        except Exception as e:
            log.warning(f"{symbol}: news check failed ({e}); trading without it")
            return True
        log.info(f"{symbol}: {len(heads)} headline(s) in last {config.NEWS_LOOKBACK_HOURS}h")
        for h in heads[:3]:
            log.info(f"    {h['time']:%m/%d %H:%M} {h['headline'][:110]}")
        if config.NEWS_MODE == "require" and not heads:
            log.info(f"{symbol}: no recent news -> skipping buy (NEWS_MODE=require)")
            return False
        if config.NEWS_MODE == "avoid" and heads:
            log.info(f"{symbol}: recent news -> skipping buy (NEWS_MODE=avoid)")
            return False
        return True

    def flatten(self, reason: str):
        log.warning(f"FLATTENING ALL POSITIONS: {reason}")
        self.trading.close_all_positions(cancel_orders=True)
        self.known_symbols.clear()
        self.audit.write("flatten", reason=reason)

    def check_foreign_activity(self, orders, positions) -> bool:
        """True if something is happening on the account that this bot didn't do."""
        problems = security.find_foreign_activity(orders, positions, config.ORDER_ID_PREFIX,
                                                  self.allowed, self.known_symbols)
        for p in problems:
            log.critical(f"SECURITY ALERT: {p}")
        if problems:
            self.audit.write("foreign_activity", problems=problems)
        return bool(problems)

    # ---------- safety checks ----------
    def daily_loss_breached(self, account) -> bool:
        equity, last_equity = float(account.equity), float(account.last_equity)
        pnl_pct = (equity - last_equity) / last_equity if last_equity else 0.0
        log.info(f"Equity ${equity:,.2f} | day P&L {pnl_pct:+.2%}")
        return pnl_pct <= -config.MAX_DAILY_LOSS_PCT

    # ---------- main loop ----------
    def tick(self):
        if os.path.exists(config.KILL_SWITCH_FILE):
            self.flatten("kill switch file found")
            sys.exit("Stopped by kill switch.")

        clock = self.trading.get_clock()
        if not clock.is_open:
            wait = (clock.next_open - clock.timestamp).total_seconds()
            log.info(f"Market closed. Next open {clock.next_open}. Sleeping.")
            time.sleep(min(max(wait, 60), 15 * 60))   # wake every 15 min max to check kill switch
            return

        today = clock.timestamp.date()
        if today != self.trade_day:
            self.trade_day, self.trades_today = today, 0

        account = self.trading.get_account()
        if self.daily_loss_breached(account):
            self.flatten(f"daily loss limit of {config.MAX_DAILY_LOSS_PCT:.0%} hit")
            sys.exit("Stopped for the day: max daily loss.")

        mins_to_close = (clock.next_close - clock.timestamp).total_seconds() / 60
        if mins_to_close <= config.FLATTEN_MINUTES_BEFORE_CLOSE:
            if self.trading.get_all_positions():
                self.flatten("near market close")
            return

        pos_list = self.trading.get_all_positions()
        orders = self.open_orders()
        positions = {p.symbol: p for p in pos_list}
        pending = {o.symbol for o in orders}
        if self.check_foreign_activity(orders, pos_list) and config.HALT_ON_FOREIGN_ACTIVITY:
            if not self.halted:
                log.critical("New trading HALTED. Check your Alpaca account; if you didn't do this, "
                             "regenerate your API keys now.")
            self.halted = True
        if self.halted:
            return
        equity, buying_power = float(account.equity), float(account.buying_power)

        for symbol in config.SYMBOLS:
            df = self.get_bars(symbol)
            if len(df) < 30:
                log.info(f"{symbol}: not enough bars yet")
                continue
            df, buy_sig, sell_sig = compute_signals(df, self.params)
            sig = "buy" if buy_sig[-1] else "sell" if sell_sig[-1] else "hold"
            last = df.iloc[-1]
            log.info(f"{symbol}: close {last.close:.2f} -> {sig}")

            if sig == "buy" and symbol not in positions and symbol not in pending:
                if self.trades_today >= config.MAX_TRADES_PER_DAY:
                    log.info("Max trades for today reached, not opening new positions")
                    continue
                if not self.news_ok(symbol):
                    continue
                self.buy(symbol, float(last.close), equity, buying_power)
            elif sig == "sell" and symbol in positions:
                self.sell(symbol)

    def run(self):
        mode = "PAPER" if config.PAPER else "LIVE"
        log.info(f"Starting bot in {mode} mode on {config.SYMBOLS} | {describe(self.params)} | "
                 f"stop {config.STOP_LOSS_PCT:.2%} target {config.TAKE_PROFIT_PCT:.2%}")
        # adopt positions that already exist at startup (e.g. after a restart) only if allowlisted
        for p in self.trading.get_all_positions():
            if p.symbol in self.allowed:
                self.known_symbols.add(p.symbol)
        self.audit.write("start", mode=mode, symbols=list(config.SYMBOLS), strategy=describe(self.params))
        while True:
            try:
                self.tick()
            except APIError as e:
                log.error(f"Alpaca API error: {e}")
            except Exception as e:   # keep running through network blips
                log.exception(f"Unexpected error: {e}")
            time.sleep(config.LOOP_SECONDS)


if __name__ == "__main__":
    try:
        Bot().run()
    except KeyboardInterrupt:
        log.info("Stopped by user (positions left open with their bracket orders).")
