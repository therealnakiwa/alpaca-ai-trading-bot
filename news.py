"""Stock news from Alpaca (Benzinga headlines), for live checks and for backtesting.

Live:      recent_headlines("MARA", hours=24)  -> newest headlines about MARA
History:   fetch_news("MARA", start, end)      -> every headline in that window
"""
from datetime import datetime, timedelta, timezone

import config

_client = None


def _news_client():
    global _client
    if _client is None:
        from alpaca.data.historical.news import NewsClient
        _client = NewsClient(config.API_KEY, config.SECRET_KEY)
    return _client


def fetch_news(symbol: str, start: datetime, end: datetime) -> list:
    """All headlines tagged with `symbol` between start and end, oldest first."""
    from alpaca.data.requests import NewsRequest
    res = _news_client().get_news(NewsRequest(symbols=symbol, start=start, end=end))
    items = res.data.get("news", []) if hasattr(res, "data") else res.get("news", [])
    rows = []
    for n in items:
        get = (lambda k: getattr(n, k, None)) if not isinstance(n, dict) else n.get
        rows.append({
            "time": get("created_at"),
            "headline": (get("headline") or "").strip(),
            "source": get("source"),
            "symbols": ",".join(get("symbols") or []),
            "summary": (get("summary") or "").strip()[:300],
        })
    rows.sort(key=lambda r: r["time"])
    return rows


def recent_headlines(symbol: str, hours: float = 24) -> list:
    """Headlines about `symbol` in the last `hours` hours, newest first."""
    end = datetime.now(timezone.utc)
    return list(reversed(fetch_news(symbol, end - timedelta(hours=hours), end)))
