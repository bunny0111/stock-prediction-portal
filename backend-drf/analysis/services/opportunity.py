"""
OpportunityService
==================
Turns the confluence DIRECTION into a concrete (educational) trade plan:
entry zone, stop-loss, targets, and risk/reward.

Logic:
  - Direction comes from ConfluenceScoringService (bullish=long, bearish=short).
  - Stop-loss sits just beyond the nearest support (long) / resistance (short),
    with an ATR buffer; if none, it's a pure ATR-based stop.
  - Targets are the next resistance levels (long) / support levels (short);
    if none, ATR-projected targets.
  - Risk/reward = potential reward to each target ÷ risk to the stop.

For analysis & education only — NOT financial advice, NEVER auto-trades.
"""

from .market_data import MarketDataService
from .confluence import ConfluenceScoringService
from .support_resistance import SupportResistanceService
from ..indicators.volatility import average_true_range


class OpportunityService:
    def __init__(self, market_data_service=None):
        self.market = market_data_service or MarketDataService()
        self.confluence = ConfluenceScoringService(self.market)
        self.sr = SupportResistanceService(self.market)

    def analyze(self, ticker, period="1y", interval="1d", as_of=None, light=False,
                min_rr=0, target_method="A"):
        conf = self.confluence.analyze(ticker, period=period, interval=interval,
                                       as_of=as_of, light=light)
        cd = conf["details"]
        direction = cd["direction"]
        score = cd["score"]
        quality = cd["classification"]
        trend_direction = cd.get("trend_direction")
        trend_strength = cd.get("trend_strength")

        sr = self.sr.analyze(ticker, period=period, interval=interval, as_of=as_of)["details"]
        current = sr["current_price"]
        supports = [z["level"] for z in sr.get("support", [])]
        resistances = [z["level"] for z in sr.get("resistance", [])]

        # ATR for stop/target buffers (fall back to ~2% of price).
        data = self.market.get_ohlcv(ticker, period=period, interval=interval)
        candles = data["candles"]
        if as_of:
            candles = [c for c in candles if c["date"] <= as_of]
        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]
        closes = [c["close"] for c in candles]
        atr = round(average_true_range(highs, lows, closes) or current * 0.02, 2)

        if direction == "bullish":
            plan = self._long_plan(current, atr, supports, resistances, target_method)
        elif direction == "bearish":
            plan = self._short_plan(current, atr, supports, resistances, target_method)
        else:
            return self._no_trade(current, atr, score, quality,
                                  "No directional bias — confluence is neutral.",
                                  trend_direction, trend_strength)

        if plan["risk"] <= 0:
            return self._no_trade(current, atr, score, quality,
                                  "Risk could not be defined cleanly for this setup.",
                                  trend_direction, trend_strength)

        # Minimum risk/reward filter: only keep targets whose R:R meets the bar.
        # If none qualify, it's not a trade worth taking.
        if min_rr and min_rr > 0:
            qualifying = [t for t in plan["targets"]
                          if t["risk_reward"] is not None and t["risk_reward"] >= min_rr]
            if not qualifying:
                best = max((t["risk_reward"] or 0 for t in plan["targets"]), default=0)
                return self._no_trade(
                    current, atr, score, quality,
                    f"Best risk/reward ({best}) is below the minimum of {min_rr}.",
                    trend_direction, trend_strength)
            plan["targets"] = qualifying

        rr0 = plan["targets"][0]["risk_reward"] if plan["targets"] else None
        rr_quality = ("good" if rr0 and rr0 >= 2
                      else "fair" if rr0 and rr0 >= 1 else "poor")

        return {
            "signal": direction,
            "confidence": round(score / 100, 2),
            "details": {
                "no_trade": False,
                "direction": plan["side"],          # "long" / "short"
                "trend_direction": trend_direction,  # uptrend / downtrend / sideways
                "trend_strength": trend_strength,
                "setup_quality": quality,
                "confluence_score": score,
                "current_price": round(current, 2),
                "atr": atr,
                "entry_zone": plan["entry_zone"],
                "entry": plan["entry"],
                "stop_loss": plan["stop_loss"],
                "risk": plan["risk"],
                "targets": plan["targets"],
                "rr_quality": rr_quality,
            },
            "viz": {
                "entry": plan["entry"],
                "stop_loss": plan["stop_loss"],
                "targets": [t["price"] for t in plan["targets"]],
            },
        }

    # ----------------------------------------------------------------- helpers

    def _long_plan(self, current, atr, supports, resistances, target_method="A"):
        entry = current
        entry_zone = [round(current - 0.25 * atr, 2), round(current + 0.25 * atr, 2)]

        nearest_support = max(supports) if supports else None
        if nearest_support is not None and nearest_support < entry:
            stop = round(nearest_support - 0.25 * atr, 2)
        else:
            stop = round(current - 1.5 * atr, 2)

        res_above = sorted([r for r in resistances if r > entry])
        if target_method == "B":
            # ATR-capped: target = min(nearest resistance, entry + 2.5x / 4x ATR)
            cap1, cap2 = entry + 2.5 * atr, entry + 4.0 * atr
            t1 = min(res_above[0], cap1) if res_above else cap1
            t2 = min(res_above[1], cap2) if len(res_above) > 1 else cap2
            if t2 <= t1:
                t2 = t1 + atr
            levels = [round(t1, 2), round(t2, 2)]
        else:
            levels = res_above[:2] or [round(current + 2 * atr, 2), round(current + 3 * atr, 2)]

        risk = round(entry - stop, 2)
        targets = [self._target(t, round(t - entry, 2), risk) for t in levels]
        return {"side": "long", "entry": round(entry, 2), "entry_zone": entry_zone,
                "stop_loss": stop, "risk": risk, "targets": targets}

    def _short_plan(self, current, atr, supports, resistances, target_method="A"):
        entry = current
        entry_zone = [round(current - 0.25 * atr, 2), round(current + 0.25 * atr, 2)]

        nearest_resistance = min(resistances) if resistances else None
        if nearest_resistance is not None and nearest_resistance > entry:
            stop = round(nearest_resistance + 0.25 * atr, 2)
        else:
            stop = round(current + 1.5 * atr, 2)

        sup_below = sorted([s for s in supports if s < entry], reverse=True)
        if target_method == "B":
            cap1, cap2 = entry - 2.5 * atr, entry - 4.0 * atr
            t1 = max(sup_below[0], cap1) if sup_below else cap1
            t2 = max(sup_below[1], cap2) if len(sup_below) > 1 else cap2
            if t2 >= t1:
                t2 = t1 - atr
            levels = [round(t1, 2), round(t2, 2)]
        else:
            levels = sup_below[:2] or [round(current - 2 * atr, 2), round(current - 3 * atr, 2)]

        risk = round(stop - entry, 2)
        targets = [self._target(t, round(entry - t, 2), risk) for t in levels]
        return {"side": "short", "entry": round(entry, 2), "entry_zone": entry_zone,
                "stop_loss": stop, "risk": risk, "targets": targets}

    def _target(self, price, reward, risk):
        return {
            "price": round(price, 2),
            "reward": reward,
            "risk_reward": round(reward / risk, 2) if risk > 0 else None,
        }

    def _no_trade(self, current, atr, score, quality, reason,
                  trend_direction=None, trend_strength=None):
        return {
            "signal": "neutral",
            "confidence": round(score / 100, 2),
            "details": {
                "no_trade": True,
                "reason": reason,
                "current_price": round(current, 2),
                "atr": atr,
                "confluence_score": score,
                "setup_quality": quality,
                "trend_direction": trend_direction,
                "trend_strength": trend_strength,
            },
            "viz": {},
        }
