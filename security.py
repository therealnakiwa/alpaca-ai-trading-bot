"""Security layer for the trading bot.

Threats this guards against, and how:
  1. Stolen API keys from plaintext files   -> keys in the OS credential store (Windows Credential Manager,
                                               macOS Keychain) via `keyring`; .env only as a fallback
  2. Keys leaking into logs or screenshots  -> RedactingFilter masks secrets in every log line
  3. A bug or tampered config placing huge  -> OrderGuard: symbol allowlist, max qty, max $ per order,
     or runaway orders                         max $ per day, max orders per minute (kill-switch on breach)
  4. Someone else trading with your keys    -> every bot order is tagged; orders/positions the bot didn't
                                               create are flagged and new trading halts
  5. Code tampered with on disk              -> SHA-256 manifest of the bot's code, signed with an HMAC key;
                                               the bot refuses to start if anything changed unapproved
  6. Logs edited to hide what happened       -> tamper-evident audit log: each entry is chained to the
                                               previous one with an HMAC, so edits/deletions are detectable

Commands:
  python security.py --set-keys      store Alpaca keys in the OS credential store
  python security.py --approve       record the current code as trusted (after you review changes)
  python security.py --verify-audit  check the audit log for tampering
"""
import argparse
import getpass
import glob
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
import uuid
from collections import deque
from datetime import datetime, timezone

SERVICE = "alpaca-ai-bot"
HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(HERE, "integrity.json")
AUDIT_LOG = os.path.join(HERE, "logs", "audit.jsonl")


class SecurityBlock(Exception):
    """Raised when a security control refuses an action."""


# ------------------------------------------------------------------ 1. credentials
def _keyring():
    try:
        import keyring
        from keyring.backends import fail
        if isinstance(keyring.get_keyring(), fail.Keyring):
            return None            # no OS credential store on this machine
        return keyring
    except Exception:
        return None


def load_credentials():
    """Return (api_key, secret_key, source). OS credential store first, then environment/.env."""
    kr = _keyring()
    if kr:
        try:
            k, s = kr.get_password(SERVICE, "api_key"), kr.get_password(SERVICE, "secret_key")
            if k and s:
                return k, s, "OS credential store"
        except Exception:
            pass
    return os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY"), ".env file (less secure)"


def set_keys():
    kr = _keyring()
    if not kr:
        raise SystemExit("The `keyring` package isn't available. Run: pip install keyring")
    k = getpass.getpass("Alpaca API Key ID (input hidden): ").strip()
    s = getpass.getpass("Alpaca Secret Key (input hidden): ").strip()
    if not (k and s):
        raise SystemExit("Nothing entered; no changes made.")
    kr.set_password(SERVICE, "api_key", k)
    kr.set_password(SERVICE, "secret_key", s)
    print("Saved to the OS credential store. You can now delete the two key lines from .env.")


def _hmac_key() -> bytes:
    """Per-machine secret used to sign the code manifest and audit log. Never stored in the repo."""
    kr = _keyring()
    if kr:
        try:
            v = kr.get_password(SERVICE, "hmac_key")
            if not v:
                v = secrets.token_hex(32)
                kr.set_password(SERVICE, "hmac_key", v)
            return bytes.fromhex(v)
        except Exception:
            pass
    v = os.getenv("BOT_HMAC_KEY")
    if v:
        return v.encode()
    # last resort: a local key file outside the code (ignored by git)
    path = os.path.join(HERE, ".hmac_key")
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(secrets.token_hex(32))
    with open(path) as f:
        return bytes.fromhex(f.read().strip())


# ------------------------------------------------------------------ 2. log redaction
class RedactingFilter(logging.Filter):
    """Masks API keys (and anything that looks like an Alpaca key) in every log record."""
    PATTERN = re.compile(r"\b(PK|AK|CK)[A-Z0-9]{14,}\b")

    def __init__(self, secrets_to_hide=()):
        super().__init__()
        self.secrets = [s for s in secrets_to_hide if s and len(s) >= 8]

    def redact(self, text: str) -> str:
        for s in self.secrets:
            text = text.replace(s, s[:2] + "***REDACTED***")
        return self.PATTERN.sub(lambda m: m.group(1) + "***REDACTED***", text)

    def filter(self, record):
        record.msg = self.redact(record.getMessage())
        record.args = ()
        return True


# ------------------------------------------------------------------ 3. order guard
class OrderGuard:
    """Hard limits checked before ANY order is sent, independent of strategy code."""

    def __init__(self, allowed_symbols, max_qty, max_order_notional, max_daily_notional,
                 max_orders_per_minute, clock=time.time):
        self.allowed = {s.upper() for s in allowed_symbols}
        self.max_qty = max_qty
        self.max_order_notional = max_order_notional
        self.max_daily_notional = max_daily_notional
        self.max_per_min = max_orders_per_minute
        self.clock = clock
        self.recent = deque()
        self.day = None
        self.day_notional = 0.0

    def check(self, symbol: str, qty: float, price: float):
        now = self.clock()
        today = datetime.fromtimestamp(now, timezone.utc).date()
        if today != self.day:
            self.day, self.day_notional = today, 0.0
        symbol = symbol.upper()
        notional = qty * price
        if symbol not in self.allowed:
            raise SecurityBlock(f"{symbol} is not on the symbol allowlist")
        if qty <= 0 or qty > self.max_qty:
            raise SecurityBlock(f"quantity {qty} outside 1..{self.max_qty}")
        if not (price > 0):
            raise SecurityBlock(f"invalid price {price}")
        if notional > self.max_order_notional:
            raise SecurityBlock(f"order ${notional:,.0f} exceeds per-order cap ${self.max_order_notional:,.0f}")
        if self.day_notional + notional > self.max_daily_notional:
            raise SecurityBlock(f"would exceed daily cap ${self.max_daily_notional:,.0f}")
        while self.recent and now - self.recent[0] > 60:
            self.recent.popleft()
        if len(self.recent) >= self.max_per_min:
            raise SecurityBlock(f"rate limit: more than {self.max_per_min} orders/minute (runaway loop?)")
        # passed: record it
        self.recent.append(now)
        self.day_notional += notional


def new_order_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:20]}"


# ------------------------------------------------------------------ 4. foreign activity
def find_foreign_activity(orders, positions, prefix: str, allowed_symbols, known_symbols):
    """Return a list of human-readable problems: open orders not created by this bot, or positions
    in symbols the bot isn't allowed to trade / never bought. `orders` should be top-level orders
    (bracket legs nested), each with .client_order_id and .symbol; positions with .symbol."""
    problems = []
    allowed = {s.upper() for s in allowed_symbols}
    for o in orders:
        cid = getattr(o, "client_order_id", "") or ""
        if not cid.startswith(prefix + "-"):
            problems.append(f"open order {getattr(o, 'id', '?')} on {o.symbol} was not placed by this bot")
    for p in positions:
        sym = p.symbol.upper()
        if sym not in allowed:
            problems.append(f"position in {sym}, which is not on the allowlist")
        elif sym not in known_symbols:
            problems.append(f"position in {sym} that this bot did not open")
    return problems


# ------------------------------------------------------------------ 5. code integrity
def code_files():
    files = sorted(glob.glob(os.path.join(HERE, "*.py")))
    return [f for f in files if not os.path.basename(f).startswith("test_")]


def _digest(files):
    out = {}
    for f in files:
        with open(f, "rb") as fh:
            out[os.path.basename(f)] = hashlib.sha256(fh.read()).hexdigest()
    return out


def approve_code():
    hashes = _digest(code_files())
    body = json.dumps(hashes, sort_keys=True)
    sig = hmac.new(_hmac_key(), body.encode(), hashlib.sha256).hexdigest()
    with open(MANIFEST, "w") as f:
        json.dump({"files": hashes, "signature": sig,
                   "approved_at": datetime.now(timezone.utc).isoformat()}, f, indent=2)
    print(f"Approved {len(hashes)} code files. The bot will refuse to run if any of them change.")


def verify_code():
    """Returns a list of problems (empty = OK)."""
    if not os.path.exists(MANIFEST):
        return ["no integrity.json yet; run `python security.py --approve` after reviewing the code"]
    with open(MANIFEST) as f:
        m = json.load(f)
    body = json.dumps(m["files"], sort_keys=True)
    expected = hmac.new(_hmac_key(), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, m.get("signature", "")):
        return ["integrity.json signature is invalid (manifest edited or made on another machine)"]
    now = _digest(code_files())
    problems = [f"{f} changed since approval" for f in now if f in m["files"] and now[f] != m["files"][f]]
    problems += [f"{f} is new and not approved" for f in now if f not in m["files"]]
    problems += [f"{f} was deleted" for f in m["files"] if f not in now]
    return problems


# ------------------------------------------------------------------ 6. tamper-evident audit log
class AuditLog:
    """Append-only JSON-lines log where each entry's MAC covers the previous entry's MAC.
    Editing, reordering or deleting any line breaks the chain from that point on."""

    def __init__(self, path=AUDIT_LOG, key: bytes = None):
        self.path = path
        self.key = key or _hmac_key()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.prev = self._last_mac()

    def _last_mac(self):
        if not os.path.exists(self.path):
            return "GENESIS"
        last = "GENESIS"
        with open(self.path) as f:
            for line in f:
                if line.strip():
                    last = json.loads(line)["mac"]
        return last

    def _mac(self, prev, ts, event, data):
        body = json.dumps({"prev": prev, "ts": ts, "event": event, "data": data}, sort_keys=True)
        return hmac.new(self.key, body.encode(), hashlib.sha256).hexdigest()

    def write(self, event: str, **data):
        ts = datetime.now(timezone.utc).isoformat()
        mac = self._mac(self.prev, ts, event, data)
        with open(self.path, "a") as f:
            f.write(json.dumps({"ts": ts, "event": event, "data": data, "prev": self.prev, "mac": mac}) + "\n")
        self.prev = mac

    def verify(self):
        """Returns (ok, message)."""
        if not os.path.exists(self.path):
            return True, "no audit log yet"
        prev, n = "GENESIS", 0
        with open(self.path) as f:
            for i, line in enumerate(f, 1):
                if not line.strip():
                    continue
                e = json.loads(line)
                if e["prev"] != prev:
                    return False, f"line {i}: chain broken (a line was deleted or reordered before it)"
                if not hmac.compare_digest(self._mac(prev, e["ts"], e["event"], e["data"]), e["mac"]):
                    return False, f"line {i}: contents were modified"
                prev, n = e["mac"], n + 1
        return True, f"{n} entries verified, no tampering detected"


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set-keys", action="store_true")
    ap.add_argument("--approve", action="store_true")
    ap.add_argument("--verify-audit", action="store_true")
    a = ap.parse_args()
    if a.set_keys:
        set_keys()
    elif a.approve:
        approve_code()
    elif a.verify_audit:
        ok, msg = AuditLog().verify()
        print(("OK: " if ok else "TAMPERING DETECTED: ") + msg)
    else:
        ap.print_help()
