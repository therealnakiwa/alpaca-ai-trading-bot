"""Tests for the security layer. Run:  python -m pytest -q"""
import json, logging, os, sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("ALPACA_API_KEY", "PKTESTTESTTESTTEST1234")  # scan: allow (fake test key)
os.environ.setdefault("ALPACA_SECRET_KEY", "s3cr3t-s3cr3t-s3cr3t-s3cr3t-s3cr3t-0000")
import security
from security import AuditLog, OrderGuard, RedactingFilter, SecurityBlock, find_foreign_activity


# ---------------- order guard ----------------
class FakeClock:
    def __init__(self): self.t = datetime(2026, 11, 18, 15, tzinfo=timezone.utc).timestamp()
    def __call__(self): return self.t

def guard(clock=None):
    return OrderGuard(["SPY", "MARA"], max_qty=100, max_order_notional=5_000,
                      max_daily_notional=12_000, max_orders_per_minute=3, clock=clock or FakeClock())

def test_allows_normal_order():
    guard().check("SPY", 5, 500)

@pytest.mark.parametrize("sym,qty,price,why", [
    ("TSLA", 1, 100, "allowlist"),
    ("SPY", 0, 100, "quantity"),
    ("SPY", 101, 1, "quantity"),
    ("SPY", 10, 600, "per-order cap"),
    ("SPY", 1, float("nan"), "invalid price"),
])
def test_blocks_bad_orders(sym, qty, price, why):
    with pytest.raises(SecurityBlock, match=why):
        guard().check(sym, qty, price)

def test_daily_cap_and_reset_next_day():
    c = FakeClock(); g = guard(c)
    g.check("SPY", 9, 500); c.t += 120; g.check("SPY", 9, 500)          # $9,000 so far
    c.t += 120
    with pytest.raises(SecurityBlock, match="daily cap"):
        g.check("SPY", 9, 500)                                           # would be $13,500
    c.t += 86_400
    g.check("SPY", 9, 500)                                               # new day, cap resets

def test_rate_limit_catches_runaway_loop():
    c = FakeClock(); g = guard(c)
    for _ in range(3):
        g.check("MARA", 1, 10)
    with pytest.raises(SecurityBlock, match="rate limit"):
        g.check("MARA", 1, 10)
    c.t += 61
    g.check("MARA", 1, 10)                                               # window passed

def test_order_ids_are_tagged_and_unique():
    a, b = security.new_order_id("jbot"), security.new_order_id("jbot")
    assert a.startswith("jbot-") and a != b


# ---------------- log redaction ----------------
def test_redaction_hides_keys(caplog):
    secret = "s3cr3t-s3cr3t-s3cr3t-s3cr3t-s3cr3t-9999"  # scan: allow (fake test key)
    f = RedactingFilter([secret])
    rec = logging.LogRecord("t", logging.INFO, "", 0, "key=%s id=PKABCDEFGHIJKLMNOP12", (secret,), None)  # scan: allow (fake test key)
    f.filter(rec)
    msg = rec.getMessage()
    assert secret not in msg and "PKABCDEFGHIJKLMNOP12" not in msg and "REDACTED" in msg  # scan: allow (fake test key)


# ---------------- foreign activity ----------------
def test_detects_orders_and_positions_the_bot_did_not_make():
    orders = [NS(id=1, symbol="SPY", client_order_id="jbot-abc"), NS(id=2, symbol="SPY", client_order_id="web-123")]
    positions = [NS(symbol="SPY"), NS(symbol="GME"), NS(symbol="MARA")]
    probs = find_foreign_activity(orders, positions, "jbot", ["SPY", "MARA"], known_symbols={"SPY"})
    text = " | ".join(probs)
    assert "order 2" in text and "GME" in text and "MARA that this bot did not open" in text
    assert "order 1" not in text

def test_clean_account_has_no_alerts():
    assert find_foreign_activity([NS(id=1, symbol="SPY", client_order_id="jbot-x")],
                                 [NS(symbol="SPY")], "jbot", ["SPY"], {"SPY"}) == []


# ---------------- audit log ----------------
def make_log(tmp_path):
    a = AuditLog(path=str(tmp_path / "audit.jsonl"), key=b"k" * 32)
    for i in range(4):
        a.write("buy", symbol="SPY", qty=i)
    return a

def test_audit_log_verifies(tmp_path):
    ok, msg = make_log(tmp_path).verify()
    assert ok, msg

def test_audit_log_detects_edit(tmp_path):
    a = make_log(tmp_path)
    lines = open(a.path).read().splitlines()
    e = json.loads(lines[1]); e["data"]["qty"] = 999; lines[1] = json.dumps(e)
    open(a.path, "w").write("\n".join(lines) + "\n")
    ok, msg = a.verify()
    assert not ok and "line 2" in msg

def test_audit_log_detects_deletion(tmp_path):
    a = make_log(tmp_path)
    lines = open(a.path).read().splitlines()
    del lines[1]
    open(a.path, "w").write("\n".join(lines) + "\n")
    ok, msg = a.verify()
    assert not ok and "chain broken" in msg

def test_audit_log_rejects_wrong_key(tmp_path):
    a = make_log(tmp_path)
    ok, _ = AuditLog(path=a.path, key=b"x" * 32).verify()
    assert not ok


# ---------------- code integrity ----------------
@pytest.fixture
def code_dir(tmp_path, monkeypatch):
    (tmp_path / "bot.py").write_text("print('hi')\n")
    (tmp_path / "config.py").write_text("MAX = 1\n")
    monkeypatch.setattr(security, "HERE", str(tmp_path))
    monkeypatch.setattr(security, "MANIFEST", str(tmp_path / "integrity.json"))
    monkeypatch.setattr(security, "_hmac_key", lambda: b"k" * 32)
    return tmp_path

def test_integrity_passes_after_approval(code_dir):
    security.approve_code()
    assert security.verify_code() == []

def test_integrity_catches_changed_new_and_deleted_files(code_dir):
    security.approve_code()
    (code_dir / "config.py").write_text("MAX = 999999\n")
    (code_dir / "evil.py").write_text("send_keys()\n")
    (code_dir / "bot.py").unlink()
    probs = " | ".join(security.verify_code())
    assert "config.py changed" in probs and "evil.py is new" in probs and "bot.py was deleted" in probs

def test_integrity_catches_forged_manifest(code_dir):
    security.approve_code()
    m = json.loads((code_dir / "integrity.json").read_text())
    m["files"]["config.py"] = "0" * 64
    (code_dir / "integrity.json").write_text(json.dumps(m))
    assert "signature is invalid" in security.verify_code()[0]


# ---------------- secret scanner ----------------
def test_scanner_finds_real_looking_keys_and_ignores_placeholders(tmp_path):
    import scan_secrets
    bad = tmp_path / "leak.py"; bad.write_text('API_KEY = "PKZZ8Q2W4E6R8T0Y2U4I"\n')  # scan: allow (fake test key)
    ok = tmp_path / ".env.example"; ok.write_text("ALPACA_API_KEY=your_paper_key_here\n")
    env = tmp_path / ".env"; env.write_text("x=1\n")
    hits = scan_secrets.scan([str(bad), str(ok), str(env)])
    flagged = {os.path.basename(h[0]) for h in hits}
    assert flagged == {"leak.py", ".env"}

def test_project_itself_contains_no_secrets():
    import scan_secrets
    root = os.path.join(os.path.dirname(__file__), "..")
    files = [os.path.join(r, f) for r, d, fs in os.walk(root) for f in fs
             if not any(x in r for x in (".git", "venv", "__pycache__", "data", "logs")) and f != ".env"
             and not f.startswith("test_")]
    assert scan_secrets.scan(files) == []


# ---------------- bot integration (no network) ----------------
@pytest.fixture
def bot(tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "REQUIRE_CODE_INTEGRITY", False)
    monkeypatch.setattr(config, "SYMBOLS", ["SPY"])
    monkeypatch.setattr(config, "MAX_ORDER_NOTIONAL", 5_000)
    monkeypatch.setattr(security, "AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    monkeypatch.setattr(security, "_hmac_key", lambda: b"k" * 32)
    import bot as botmod
    monkeypatch.setattr(botmod.security, "AuditLog", lambda: AuditLog(path=str(tmp_path / "audit.jsonl"), key=b"k" * 32))
    b = botmod.Bot()
    b.trading = MagicMock()
    return b

def test_bot_tags_orders_and_audits(bot):
    bot.buy("SPY", 100.0, equity=10_000, buying_power=20_000)
    order = bot.trading.submit_order.call_args[0][0]
    assert order.client_order_id.startswith("jbot-")
    ok, msg = bot.audit.verify()
    assert ok and "1 entries" in msg

def test_bot_blocks_oversized_order(bot):
    bot.buy("SPY", 1000.0, equity=1_000_000, buying_power=2_000_000)    # way above $5k cap
    bot.trading.submit_order.assert_not_called()

def test_bot_halts_on_foreign_activity(bot):
    assert bot.check_foreign_activity([NS(id=9, symbol="SPY", client_order_id="someone-else")], [])
