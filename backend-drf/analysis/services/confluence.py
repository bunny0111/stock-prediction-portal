"""
ConfluenceScoringService
========================
The decision core. It does NOT analyse price itself — it ORCHESTRATES the
objective engines (Trend, Support/Resistance, Volume) and combines their
signals into a single 0-100 setup score with a direction and classification.

Principle: never trade on one factor. A strong setup is one where multiple
independent factors AGREE. If they conflict, the score stays low.

All engines share one cached MarketDataService, so the price data is fetched
once and reused.
"""

from .market_data import MarketDataService
from .trend_analysis import TrendAnalysisService
from .support_resistance import SupportResistanceService
from .volume_analysis import VolumeAnalysisService


# Configurable weights (points out of 100). Trend leads, volume confirms,
# support/resistance gives location.
DEFAULT_WEIGHTS = {"trend": 40, "support_resistance": 30, "volume": 30}


class ConfluenceScoringService:
    def __init__(self, market_data_service=None, weights=None):
        self.market = market_data_service or MarketDataService()
        self.trend = TrendAnalysisService(self.market)
        self.sr = SupportResistanceService(self.market)
        self.volume = VolumeAnalysisService(self.market)
        self.weights = weights or dict(DEFAULT_WEIGHTS)

    def analyze(self, ticker, period="1y", interval="1d", as_of=None, light=False):
        # light=True skips trendline detection inside trend analysis (backtest speed).
        trend = self.trend.analyze(ticker, period=period, interval=interval, as_of=as_of,
                                   compute_trendlines=not light)
        sr = self.sr.analyze(ticker, period=period, interval=interval, as_of=as_of)
        vol = self.volume.analyze(ticker, period=period, interval=interval, as_of=as_of)

        factors = [
            self._factor("trend", trend, self._trend_reason(trend)),
            self._factor("support_resistance", sr, self._sr_reason(sr)),
            self._factor("volume", vol, self._volume_reason(vol)),
        ]

        bull = sum(f["contribution"] for f in factors if f["contribution"] > 0)
        bear = -sum(f["contribution"] for f in factors if f["contribution"] < 0)
        net = round(bull - bear, 1)

        score = min(round(abs(net)), 100)
        direction = "bullish" if net > 5 else "bearish" if net < -5 else "neutral"
        classification = self._classify(score)

        return {
            "signal": direction,
            "confidence": round(score / 100, 2),
            "details": {
                "score": score,
                "direction": direction,
                "classification": classification,
                "bull_points": round(bull, 1),
                "bear_points": round(bear, 1),
                "factors": factors,
                "weights": self.weights,
                # surfaced for the Opportunity panel (no extra computation)
                "trend_direction": trend["details"].get("direction", "unknown"),
                "trend_strength": trend["details"].get("strength_label", ""),
            },
            "viz": {},
        }

    # ----------------------------------------------------------------- helpers

    def _factor(self, name, engine_out, reason):
        weight = self.weights.get(name, 0)
        signal = engine_out.get("signal", "neutral")
        confidence = engine_out.get("confidence", 0.0) or 0.0
        sign = 1 if signal == "bullish" else -1 if signal == "bearish" else 0
        return {
            "name": name,
            "signal": signal,
            "confidence": round(confidence, 2),
            "weight": weight,
            "contribution": round(sign * confidence * weight, 1),  # signed points
            "reason": reason,
        }

    def _classify(self, score):
        if score >= 81:
            return "Very Strong"
        if score >= 61:
            return "Strong"
        if score >= 31:
            return "Moderate"
        return "Weak"

    def _trend_reason(self, trend):
        d = trend.get("details", {})
        return f"{d.get('direction', 'unknown')} ({d.get('strength_label', '')})".strip()

    def _sr_reason(self, sr):
        sig = sr.get("signal", "neutral")
        if sig == "bullish":
            return "price sitting near support"
        if sig == "bearish":
            return "price sitting near resistance"
        return "price between support & resistance"

    def _volume_reason(self, vol):
        d = vol.get("details", {})
        rv = d.get("relative_volume")
        if rv is None:
            return "no volume data"
        return f"{rv}x avg volume, OBV {d.get('obv_trend', 'flat')}"
