"""
MarketDataService
=================
The single source of market data for the whole analysis platform.

Every future engine (support/resistance, volume, trend, confluence, ...) asks
THIS service for price data instead of fetching it itself. Doing it in one
place means:
  - we fetch from Yahoo only once and reuse the result (caching),
  - retries and error handling live in one place,
  - every engine receives data in exactly the same shape.

How it fetches
--------------
It uses the SAME approach your existing prediction view already uses and that
already works reliably in this project: a direct request to Yahoo's chart
endpoint with a browser User-Agent. (yfinance's default download path is the
one Yahoo frequently rate-limits with "Too Many Requests", which is why we
avoid it here.) News, later in Phase 4, will still use the yfinance library.
"""

import json
import os
import time

import requests
import pandas as pd
from django.core.cache import cache

# Bundled list of NSE equities (symbol + company name) for offline autocomplete.
_NSE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "nse_equities.json")
_NSE_CACHE = None


def _nse_equities():
    global _NSE_CACHE
    if _NSE_CACHE is None:
        try:
            with open(_NSE_PATH, encoding="utf-8") as f:
                _NSE_CACHE = json.load(f)
        except Exception:
            _NSE_CACHE = []
    return _NSE_CACHE


class MarketDataError(Exception):
    """Raised when we cannot get usable data for a ticker (bad symbol, no data,
    or Yahoo failed after retries). The view turns this into a clean HTTP error."""
    pass


class MarketDataService:
    CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    SEARCH_URL = "https://query1.finance.yahoo.com/v1/finance/search"
    HEADERS = {"User-Agent": "Mozilla/5.0"}

    CACHE_TTL = 60 * 15      # keep a fetched result for 15 minutes
    MAX_RETRIES = 3          # retry transient failures (e.g. rate limits)
    RETRY_DELAY = 1          # seconds between retries

    def get_ohlcv(self, ticker, period="2y", interval="1d"):
        """
        Return cleaned OHLCV (Open/High/Low/Close/Volume) data for a ticker.

        period:   how far back to look ('6mo', '1y', '2y', '5y', '10y', 'max')
        interval: candle size ('1d', '1wk', '1mo')

        Returns a plain dict that is safe to send straight to the frontend.
        Raises MarketDataError if the ticker is invalid or data is unavailable.
        """
        ticker = ticker.strip().upper()
        cache_key = f"ohlcv:{ticker}:{period}:{interval}"

        # 1. Serve from cache if we already fetched this recently.
        cached = cache.get(cache_key)
        if cached is not None:
            cached["meta"]["cache_hit"] = True
            return cached

        # 2. Otherwise fetch the raw Yahoo "result" block, with retries.
        result = self._fetch_with_retries(ticker, period, interval)

        # 3. Turn it into our standard candle list.
        candles = self._parse_candles(result)
        if not candles:
            raise MarketDataError(f"No usable price data for ticker '{ticker}'.")

        # 4. Wrap with metadata.
        payload = self._build_payload(ticker, period, interval, candles)

        # 5. Cache so the next request (and every other engine) is instant.
        cache.set(cache_key, payload, self.CACHE_TTL)
        return payload

    def search(self, query, limit=10):
        """Autocomplete over the bundled NSE equity list (Indian stocks only).
        Ranks: symbol-prefix > name-prefix > any substring. Returns
        [{symbol, name, exchange}]. Never raises — returns []."""
        q = (query or "").strip().lower()
        # Strip a trailing exchange suffix the user may have typed (e.g. "tat.ns",
        # "tata.bo", or a partial ".n"/".") so it still matches the base symbol.
        for suf in (".ns", ".bo", ".n", ".b", "."):
            if q.endswith(suf):
                q = q[: -len(suf)]
                break
        if not q:
            return []

        sym_prefix, name_prefix, contains = [], [], []
        for s in _nse_equities():
            base = s["symbol"].split(".")[0].lower()   # symbol without ".NS"
            name = s["name"].lower()
            if base.startswith(q):
                sym_prefix.append(s)
            elif name.startswith(q):
                name_prefix.append(s)
            elif q in base or q in name:
                contains.append(s)

        ranked = sym_prefix + name_prefix + contains
        return [{"symbol": s["symbol"], "name": s["name"], "exchange": "NSE"}
                for s in ranked[:limit]]

    def get_dataframe(self, ticker, period="2y", interval="1d"):
        """Convenience for future engines that prefer a pandas DataFrame
        (indexed by date) instead of the JSON dict."""
        candles = self.get_ohlcv(ticker, period=period, interval=interval)["candles"]
        df = pd.DataFrame(candles)
        df["date"] = pd.to_datetime(df["date"])
        return df.set_index("date")

    # ----------------------------------------------------------------- helpers

    def _fetch_with_retries(self, ticker, period, interval):
        """Call Yahoo's chart endpoint up to MAX_RETRIES times."""
        url = self.CHART_URL.format(ticker=ticker)
        params = {"range": period, "interval": interval}
        last_error = None

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                resp = requests.get(url, params=params, headers=self.HEADERS, timeout=10)
                data = resp.json()

                # Yahoo signals a bad ticker via an error block or empty result.
                chart = data.get("chart", {})
                if chart.get("error") or not chart.get("result"):
                    raise MarketDataError(f"Invalid or unknown ticker: '{ticker}'.")

                return chart["result"][0]

            except MarketDataError:
                raise  # a real "bad ticker" — no point retrying
            except Exception as exc:  # network blip, rate limit, bad JSON, etc.
                last_error = exc
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_DELAY)

        raise MarketDataError(f"Failed to fetch '{ticker}' from Yahoo: {last_error}")

    def _parse_candles(self, result):
        """Convert Yahoo's parallel arrays into a clean list of candle dicts."""
        timestamps = result.get("timestamp") or []
        quote = result.get("indicators", {}).get("quote", [{}])[0]
        opens = quote.get("open", [])
        highs = quote.get("high", [])
        lows = quote.get("low", [])
        closes = quote.get("close", [])
        volumes = quote.get("volume", [])

        candles = []
        for i, ts in enumerate(timestamps):
            o, h, l, c = opens[i], highs[i], lows[i], closes[i]
            # Yahoo uses null for market holidays / missing bars — skip them.
            if None in (o, h, l, c):
                continue
            candles.append({
                "date": pd.to_datetime(ts, unit="s").strftime("%Y-%m-%d"),
                "open": round(float(o), 2),
                "high": round(float(h), 2),
                "low": round(float(l), 2),
                "close": round(float(c), 2),
                "volume": int(volumes[i]) if i < len(volumes) and volumes[i] is not None else 0,
            })
        return candles

    def _build_payload(self, ticker, period, interval, candles):
        last = candles[-1]
        return {
            "candles": candles,
            "meta": {
                "ticker": ticker,
                "period": period,
                "interval": interval,
                "count": len(candles),
                "last_close": last["close"],
                "last_date": last["date"],
                "cache_hit": False,
            },
        }
