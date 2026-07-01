"""
NewsAnalysisService
===================
Collects recent company news from yfinance and returns a clean, de-duplicated
list for display. Phase 4, Step 1 per the plan:

    yfinance News  ->  NewsAnalysisService  ->  display

Locked constraints: yfinance ONLY, NO AI/LLM, NO sentiment. This service stays
completely independent of any sentiment logic — news display never depends on
scoring. (A separate, optional, local rule-based scorer can be added later.)
"""

import yfinance as yf
from django.core.cache import cache


class NewsAnalysisService:
    CACHE_TTL = 60 * 15  # 15 minutes

    def get_news(self, ticker, limit=12):
        ticker = ticker.strip().upper()
        cache_key = f"news:{ticker}"

        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            raw = yf.Ticker(ticker).news or []
        except Exception:
            raw = []  # news is optional context — never break on a fetch failure

        items, seen = [], set()
        for entry in raw:
            item = self._normalize(entry)
            if not item or item["title"] in seen:
                continue
            seen.add(item["title"])
            items.append(item)
            if len(items) >= limit:
                break

        result = {"ticker": ticker, "count": len(items), "items": items}
        cache.set(cache_key, result, self.CACHE_TTL)
        return result

    # ----------------------------------------------------------------- helpers

    def _normalize(self, entry):
        """Handle yfinance's newer nested {'id','content':{...}} format and the
        older flat format, returning a uniform dict (or None if unusable)."""
        c = entry.get("content", entry) if isinstance(entry, dict) else {}
        title = c.get("title")
        if not title:
            return None

        provider = c.get("provider")
        publisher = (provider.get("displayName")
                     if isinstance(provider, dict) else entry.get("publisher")) or "Unknown"

        url = ""
        for key in ("clickThroughUrl", "canonicalUrl"):
            v = c.get(key)
            if isinstance(v, dict) and v.get("url"):
                url = v["url"]
                break
        if not url:
            url = entry.get("link", "")

        thumb = ""
        th = c.get("thumbnail")
        if isinstance(th, dict):
            thumb = th.get("originalUrl", "")

        published = c.get("pubDate") or c.get("displayTime") or ""

        return {
            "title": title,
            "summary": (c.get("summary") or c.get("description") or "").strip(),
            "publisher": publisher,
            "published": published[:10] if published else "",
            "url": url,
            "thumbnail": thumb,
        }
