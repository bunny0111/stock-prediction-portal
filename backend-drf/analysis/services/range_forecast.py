"""
RangeForecastService
====================
Probabilistic NEXT-DAY range forecast — NOT a price prediction.

We do not forecast direction (validated as unpredictable on public daily data).
We forecast the *dispersion* of the next day, because volatility CLUSTERS and is
forecastable. The output is a set of calibrated intervals plus an uncertainty
estimate — judged by calibration (does a 90% range contain the close ~90% of the
time?), not by directional accuracy.

Engines:
  - Empirical rolling quantiles  -> PRIMARY close-return intervals (50/70/90).
    Best calibrated in research (coverage within ~1pp of nominal, out-of-sample).
  - EWMA volatility              -> SECONDARY regime adjustment (WIDEN-ONLY):
    widens the empirical interval when current volatility exceeds its recent
    average, but never narrows below the calibrated empirical band. Validated
    (A/B over 35k stock-days) to improve calibration at every level and fix the
    confidence-bucket inversion vs the earlier two-sided scaling.
  - ATR                          -> expected HIGH / LOW reach ONLY (never the
    close-return interval — ATR measures the high-low span and over-covers there).

The existing Trend / Volume / Support-Resistance / Confluence engines are reused
(not duplicated) to describe the current 'Trend Posture' — a market-condition
label, NOT a directional forecast.

Strictly point-in-time: every estimate at a given day uses only returns up to
that day; the `as_of` cutoff slices history first, so it is leakage-safe.
"""

from .market_data import MarketDataService
from .confluence import ConfluenceScoringService
from ..indicators.volatility import average_true_range
from ..indicators.distribution import empirical_interval, ewma_volatility, std

LEVELS = [0.50, 0.70, 0.90]
WINDOW = 252          # ~1 trading year of returns for the empirical distribution
MIN_RETURNS = 60      # below this we do not trust the distribution
LIMITED_HISTORY_DAYS = 252   # < ~1 trading year of returns -> calibration less reliable
MIN_CALIB_SAMPLES = 150      # < this many point-in-time eval days -> flag as limited


class RangeForecastService:
    def __init__(self, market_data_service=None):
        self.market = market_data_service or MarketDataService()
        self.confluence = ConfluenceScoringService(self.market)

    def analyze(self, ticker, period="2y", interval="1d", as_of=None, light=False):
        data = self.market.get_ohlcv(ticker, period=period, interval=interval)
        candles = data["candles"]
        if as_of:
            candles = [c for c in candles if c["date"] <= as_of]
        if len(candles) < MIN_RETURNS + 5:
            return self._empty("Not enough history for a range forecast.")

        closes = [c["close"] for c in candles]
        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]
        dates = [c["date"] for c in candles]
        returns = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))]

        price = closes[-1]
        window = returns[-WINDOW:]
        regime_ratio = self._regime_ratio(window)        # raw: drives confidence + display
        regime_scale = max(1.0, regime_ratio)            # widen-only: never narrow below the calibrated band

        # --- PRIMARY: empirical intervals, widened (only) for an expanding regime ---
        ranges = {}
        for level in LEVELS:
            iv = empirical_interval(window, level)
            if iv is None:
                continue
            q_lo, q_hi = iv[0] * regime_scale, iv[1] * regime_scale
            ranges[str(int(level * 100))] = {
                "low": round(price * (1 + q_lo), 2),
                "high": round(price * (1 + q_hi), 2),
                "width_pct": round((q_hi - q_lo) * 100, 2),
            }

        # --- ATR-based expected high / low (typical one-day reach) ---
        atr = average_true_range(highs, lows, closes, 14)
        expected_high = round(price + atr, 2) if atr else None
        expected_low = round(price - atr, 2) if atr else None

        # In light mode (multi-stock scanner) skip the expensive posture
        # (confluence) and per-ticker calibration loop for speed — neither is
        # shown in the scanner.
        posture = None if light else self._posture(ticker, period, interval, as_of)

        # --- confidence from the volatility regime ---
        confidence = self._confidence(regime_ratio, len(window))

        # --- historical calibration of THIS ticker (leakage-safe) ---
        calibration = None if light else self._calibration(returns)

        # --- limited-history flag: thin data -> calibration less reliable ---
        history_days = len(returns)
        calib_samples = (calibration or {}).get("samples", 0)
        # Only apply the calibration-samples test when calibration was actually
        # computed (light mode skips it, so calib_samples would be 0 for all).
        limited_history = history_days < LIMITED_HISTORY_DAYS or (
            calibration is not None and calib_samples < MIN_CALIB_SAMPLES)

        return {
            "signal": (posture["label"].lower() if posture else "neutral"),
            "confidence": confidence["value"],
            "details": {
                "current_price": round(price, 2),
                "as_of_date": dates[-1],
                "ranges": ranges,
                "expected_high": expected_high,
                "expected_low": expected_low,
                "atr": round(atr, 2) if atr else None,
                "trend_posture": posture,
                "confidence_level": confidence,
                "regime_ratio": round(regime_ratio, 2),
                "regime_scale": round(regime_scale, 2),
                "calibration": calibration,
                "window": len(window),
                "history_days": history_days,
                "limited_history": limited_history,
            },
            "viz": {},
        }

    # ---------------------------------------------------------------- helpers

    def _regime_ratio(self, window):
        """current EWMA vol / flat-window vol, clamped. >1 = vol expanding."""
        w_std = std(window)
        ew = ewma_volatility(window)
        if not w_std or not ew:
            return 1.0
        return max(0.5, min(2.0, ew / w_std))

    def _confidence(self, ratio, n):
        if n < MIN_RETURNS:
            label, val = "Low", 0.3
            detail = "limited history — treat the range as indicative only."
        elif ratio > 1.15:
            label, val = "Low", 0.4
            detail = ("current volatility is elevated vs its recent average — "
                      "the next-day range is wider and less stable.")
        elif ratio <= 0.90:
            label, val = "High", 0.85
            detail = ("current volatility is calm and stable vs its recent "
                      "average — the range is tighter and more reliable.")
        else:
            label, val = "Medium", 0.6
            detail = "volatility is near its recent average."
        return {"label": label, "value": val, "detail": detail}

    def _posture(self, ticker, period, interval, as_of):
        """Reuse the existing confluence engine — Trend + Volume + S/R — to label
        the current market condition. This is NOT a price/direction forecast."""
        try:
            conf = self.confluence.analyze(ticker, period=period, interval=interval,
                                           as_of=as_of, light=True)
            d = conf["details"]
            direction = d.get("direction", "neutral")
            label = {"bullish": "Bullish", "bearish": "Bearish"}.get(direction, "Neutral")
            return {
                "label": label,
                "score": d.get("score"),
                "classification": d.get("classification"),
                # surfaced so the UI can show HOW the posture is computed
                "bull_points": d.get("bull_points"),
                "bear_points": d.get("bear_points"),
                "factors": d.get("factors", []),
                "weights": d.get("weights", {}),
                "detail": ("net trend / volume / support-resistance posture — a "
                           "current market condition, not a price forecast."),
            }
        except Exception:
            return {"label": "Neutral", "score": None, "classification": None,
                    "factors": [], "weights": {}, "detail": "posture unavailable."}

    def _calibration(self, returns, window=WINDOW):
        """
        Rolling, leakage-safe coverage of the adjusted-empirical intervals for
        THIS ticker: for each past day, build the interval from PRIOR returns only
        and check whether the realised next-day return fell inside. Reports the
        same method the live forecast uses, so the displayed coverage is honest.
        """
        hits = {str(int(l * 100)): 0 for l in LEVELS}
        total = 0
        n = len(returns)
        for i in range(MIN_RETURNS, n):
            win = returns[max(0, i - window):i]      # only data strictly before day i
            if len(win) < MIN_RETURNS:
                continue
            scale = max(1.0, self._regime_ratio(win))  # widen-only, matches the live forecast
            r_next = returns[i]                       # realised next-day return
            total += 1
            for level in LEVELS:
                iv = empirical_interval(win, level)
                if iv is None:
                    continue
                lo, hi = iv[0] * scale, iv[1] * scale
                if lo <= r_next <= hi:
                    hits[str(int(level * 100))] += 1
        if total == 0:
            return None
        out = {k: round(v / total * 100, 1) for k, v in hits.items()}
        out["samples"] = total
        return out

    def _empty(self, msg):
        return {"signal": "neutral", "confidence": 0.0,
                "details": {"error": msg}, "viz": {}}
