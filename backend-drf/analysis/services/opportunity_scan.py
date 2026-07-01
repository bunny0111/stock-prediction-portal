"""
OpportunityScanService  (EXPERIMENTAL)
======================================
Ranks a fixed liquid watchlist by EXPECTED NEXT-DAY MOVE and how UNUSUAL today's
volatility is vs the stock's own baseline (expansion). Reuses RangeForecastService
in light mode (no direction, no per-ticker calibration loop) so the scan is fast.

This is NOT a directional signal. "Opportunity" = likely next-day move magnitude.
Direction stays the user's call.

Opportunity Score (0-100) = cross-sectional percentile of EXPECTED MOVE across the
watchlist. Historical validation (50,991 stock-days) showed the earlier expansion
blend added NO predictive value and actually DEGRADED realised-move prediction
(Spearman 0.169 -> 0.122), so it was removed — simpler and more predictive.
"""
from .market_data import MarketDataService, MarketDataError
from .range_forecast import RangeForecastService

# Fixed liquid universe (NSE large-caps + a few naturally volatile names).
WATCHLIST = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS",
    "WIPRO.NS", "MARUTI.NS", "LT.NS", "AXISBANK.NS", "KOTAKBANK.NS", "BHARTIARTL.NS",
    "ITC.NS", "HINDUNILVR.NS", "TITAN.NS", "SUNPHARMA.NS", "TATASTEEL.NS",
    "BAJFINANCE.NS", "HCLTECH.NS", "ASIANPAINT.NS", "TATAMOTORS.NS", "VEDL.NS",
    "ADANIENT.NS", "TATAPOWER.NS",
]

# Risk-class thresholds on the 90% range width (% of price), from validation deciles.
RISK_LOW, RISK_HIGH = 4.0, 6.5


class OpportunityScanService:
    def __init__(self, market_data_service=None):
        self.market = market_data_service or MarketDataService()
        self.rf = RangeForecastService(self.market)

    def scan(self, period="2y"):
        rows = []
        for tk in WATCHLIST:
            try:
                d = self.rf.analyze(tk, period=period, light=True)["details"]
            except MarketDataError:
                continue
            if d.get("error") or "90" not in d.get("ranges", {}):
                continue
            r90 = d["ranges"]["90"]
            price = d["current_price"]
            exp_move = round((r90["high"] - r90["low"]) / 2 / price * 100, 2)
            width = r90["width_pct"]
            rows.append({
                "ticker": tk,
                "price": price,
                "expected_move_pct": exp_move,
                "width90": width,
                "risk_class": self._risk(width),
                "confidence": d["confidence_level"]["label"],
                "expansion": d["regime_ratio"],          # raw ewma/window vol ratio
                "limited_history": d.get("limited_history", False),
            })
        if not rows:
            return []

        moves = [x["expected_move_pct"] for x in rows]
        for x in rows:
            x["opportunity_score"] = round(100 * self._pct_rank(moves, x["expected_move_pct"]))
        rows.sort(key=lambda x: -x["opportunity_score"])
        return rows

    @staticmethod
    def _pct_rank(values, v):
        n = len(values)
        if n < 2:
            return 0.5
        return (sum(1 for s in values if s <= v) - 1) / (n - 1)

    @staticmethod
    def _risk(width):
        if width < RISK_LOW:
            return "Low"
        if width <= RISK_HIGH:
            return "Medium"
        return "High"
