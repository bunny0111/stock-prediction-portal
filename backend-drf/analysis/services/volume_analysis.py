"""
VolumeAnalysisService
=====================
Measures the "conviction" behind price using volume.

Outputs the uniform {signal, confidence, details, viz} contract:
  - relative_volume : latest volume vs the recent average (e.g. 1.8x)
  - volume_spike    : is the latest volume unusually large?
  - volume_trend    : is participation rising/falling/flat over recent weeks?
  - obv_trend       : is volume flowing into up-days (accumulation) or down-days?
  - breakout_confirmation : did a big price move come WITH big volume?
  - signal          : bullish / bearish / neutral
"""

from .market_data import MarketDataService
from ..indicators.volume import average, on_balance_volume


class VolumeAnalysisService:
    def __init__(self, market_data_service=None):
        self.market = market_data_service or MarketDataService()

    def analyze(self, ticker, period="1y", interval="1d",
                avg_period=20, spike_mult=2.0, as_of=None):
        data = self.market.get_ohlcv(ticker, period=period, interval=interval)
        candles = data["candles"]
        if as_of:
            candles = [c for c in candles if c["date"] <= as_of]

        if len(candles) < avg_period + 11:
            return self._empty("Not enough history for volume analysis.")

        opens = [c["open"] for c in candles]
        closes = [c["close"] for c in candles]
        volumes = [c["volume"] for c in candles]
        dates = [c["date"] for c in candles]

        latest_vol = volumes[-1]

        # Average of the PRIOR `avg_period` bars (excluding today) — the baseline
        # we compare today's volume against.
        baseline = sum(volumes[-(avg_period + 1):-1]) / avg_period
        rel_vol = round(latest_vol / baseline, 2) if baseline else 0.0
        spike = rel_vol >= spike_mult

        # Volume trend: recent 10-day avg vs the 10 days before that.
        recent_avg = average(volumes, 10)
        older_avg = sum(volumes[-20:-10]) / 10
        if recent_avg > older_avg * 1.1:
            volume_trend = "rising"
        elif recent_avg < older_avg * 0.9:
            volume_trend = "falling"
        else:
            volume_trend = "flat"

        # OBV trend over the last ~20 bars.
        obv = on_balance_volume(closes, volumes)
        obv_past = obv[-21] if len(obv) > 21 else obv[0]
        if obv[-1] > obv_past:
            obv_trend = "rising"      # accumulation
        elif obv[-1] < obv_past:
            obv_trend = "falling"     # distribution
        else:
            obv_trend = "flat"

        # Latest bar context.
        latest_up = closes[-1] >= opens[-1]
        change_pct = round((closes[-1] - closes[-2]) / closes[-2] * 100, 2)
        breakout = spike and abs(change_pct) >= 1.0  # big move backed by big volume

        signal, confidence = self._signal(spike, latest_up, volume_trend, obv_trend, rel_vol)

        # Recent volume spikes (rolling 20-day baseline) so the chart can flag them.
        spike_dates = []
        for i in range(avg_period, len(volumes)):
            win = sum(volumes[i - avg_period:i]) / avg_period
            if win and volumes[i] >= spike_mult * win:
                spike_dates.append(dates[i])

        return {
            "signal": signal,
            "confidence": confidence,
            "details": {
                "latest_volume": latest_vol,
                "avg_volume": round(baseline),
                "relative_volume": rel_vol,
                "volume_spike": spike,
                "spike_threshold": spike_mult,
                "volume_trend": volume_trend,
                "obv_trend": obv_trend,
                "breakout_confirmation": breakout,
                "breakout_direction": ("up" if change_pct > 0 else "down") if breakout else None,
                "latest_change_pct": change_pct,
                "latest_date": dates[-1],
                # Intermediate values so the UI can show HOW each number was computed.
                "calc": {
                    "latest_volume": latest_vol,
                    "baseline_20d": round(baseline),
                    "recent_avg_10d": round(recent_avg),
                    "older_avg_10d": round(older_avg),
                    "obv_now": round(obv[-1]),
                    "obv_past": round(obv_past),
                },
            },
            "viz": {"spike_dates": spike_dates},
        }

    # ----------------------------------------------------------------- helpers

    def _signal(self, spike, latest_up, volume_trend, obv_trend, rel_vol):
        """Translate the raw volume readings into a bull/bear/neutral signal."""
        if spike and latest_up:
            signal = "bullish"      # big up-move on big volume = buyers in control
        elif spike and not latest_up:
            signal = "bearish"      # big down-move on big volume = sellers in control
        elif obv_trend == "rising" and volume_trend == "rising":
            signal = "bullish"      # growing participation flowing into up-days
        elif obv_trend == "falling" and volume_trend == "rising":
            signal = "bearish"      # growing participation flowing into down-days
        else:
            signal = "neutral"
        # Confidence scales with how extreme the latest relative volume is (3x+ = full).
        confidence = round(min(rel_vol / 3.0, 1.0), 2)
        return signal, confidence

    def _empty(self, note):
        return {
            "signal": "neutral",
            "confidence": 0.0,
            "details": {"note": note},
            "viz": {"spike_dates": []},
        }
