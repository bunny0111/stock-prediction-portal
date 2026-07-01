"""
SupportResistanceService
========================
Turns raw price history into ranked support & resistance ZONES.

Pipeline (matches what we discussed):
  1. get candles from MarketDataService (single cached source)
  2. find swing highs/lows (pivots) -> where price actually reversed
  3. cluster nearby pivots into zones (S/R are areas, not exact lines)
  4. score each zone by touches + recency
  5. classify vs current price: below = support, above = resistance
  6. return a uniform {signal, confidence, details, viz} contract
"""

from .market_data import MarketDataService
from ..indicators.pivots import find_swing_points


class SupportResistanceService:
    def __init__(self, market_data_service=None):
        # Depend on the shared data source. Because it caches, the candle fetch
        # here is usually free (already fetched for the chart).
        self.market = market_data_service or MarketDataService()

    def analyze(self, ticker, period="2y", interval="1d",
                window=5, tolerance_pct=1.5, min_touches=2, max_levels=5, as_of=None):
        data = self.market.get_ohlcv(ticker, period=period, interval=interval)
        candles = data["candles"]

        # Point-in-time review: keep only candles up to the chosen cutoff date,
        # so the levels reflect ONLY what was known by then (no look-ahead).
        if as_of:
            candles = [c for c in candles if c["date"] <= as_of]

        # "Current price" for classification is the close as of the cutoff
        # (or today's close when no cutoff is given).
        current_price = candles[-1]["close"] if candles else data["meta"]["last_close"]

        # Need a reasonable amount of history to find meaningful pivots.
        if len(candles) < (window * 2 + 10):
            return self._empty(current_price, "Not enough history up to that date to detect levels.")

        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]
        dates = [c["date"] for c in candles]
        n = len(candles)

        # 2. pivots — kept SEPARATE on purpose:
        #    swing LOWS = places price bounced UP  -> support candidates
        #    swing HIGHS = places price turned DOWN -> resistance candidates
        swing_highs, swing_lows = find_swing_points(highs, lows, window=window)

        # 3. cluster each type independently into zones
        support_zones = self._zones_from(
            self._cluster(swing_lows, tolerance_pct), current_price, dates, n, min_touches
        )
        resistance_zones = self._zones_from(
            self._cluster(swing_highs, tolerance_pct), current_price, dates, n, min_touches
        )

        # 4. a support must be BELOW current price (a floor); resistance ABOVE (a ceiling)
        support = [z for z in support_zones if z["level"] < current_price]
        resistance = [z for z in resistance_zones if z["level"] > current_price]

        # Keep the STRONGEST levels, but enforce a minimum gap between them so
        # near-duplicate lines don't overlap/clutter the chart.
        support = self._pick_spaced(support, max_levels)
        resistance = self._pick_spaced(resistance, max_levels)
        support.sort(key=lambda z: z["level"], reverse=True)   # nearest below first
        resistance.sort(key=lambda z: z["level"])              # nearest above first

        signal, confidence = self._signal(support, resistance)

        # KEY REACTION ZONES: levels where price reacted in BOTH directions
        # (acted as support sometimes AND resistance other times). These are the
        # "magnet" levels and are often the most significant on the chart.
        key_zones = self._key_zones(swing_highs, swing_lows, current_price,
                                    dates, n, tolerance_pct=2.0, top=2)

        return {
            "signal": signal,
            "confidence": confidence,
            "details": {
                "current_price": current_price,
                "support": support,
                "resistance": resistance,
                "key_zones": key_zones,
            },
            "viz": {
                "levels": (
                    [{"price": z["level"], "type": "support", **z} for z in support] +
                    [{"price": z["level"], "type": "resistance", **z} for z in resistance]
                )
            },
        }

    # ----------------------------------------------------------------- helpers

    def _key_zones(self, swing_highs, swing_lows, current_price, dates, n,
                   tolerance_pct=2.0, min_touches=3, top=2):
        """
        Find the price zones the market has reacted to the MOST in BOTH
        directions — levels that acted as resistance at times and support at
        others. Pipeline:
          swing highs/lows -> cluster by price -> count reactions ->
          ROLE-REVERSAL detection -> strength ranking.

        Role reversal = the level flipping between acting as resistance (a swing
        high sits on it) and support (a swing low sits on it), read in time
        order. A zone that flips roles many times is the strongest "battle
        zone" / price magnet — exactly the most significant level on the chart.
        """
        # Tag every pivot with its type, then cluster ALL of them together.
        pivots = ([(i, p, "high") for (i, p) in swing_highs] +
                  [(i, p, "low") for (i, p) in swing_lows])
        if not pivots:
            return []

        ordered = sorted(pivots, key=lambda x: x[1])  # by price
        clusters = [[ordered[0]]]
        for piv in ordered[1:]:
            cur = clusters[-1]
            avg = sum(p for (_, p, _) in cur) / len(cur)
            if abs(piv[1] - avg) / avg * 100 <= tolerance_pct:
                cur.append(piv)
            else:
                clusters.append([piv])

        zones = []
        for cl in clusters:
            highs = sum(1 for (_, _, t) in cl if t == "high")
            lows = sum(1 for (_, _, t) in cl if t == "low")
            total = len(cl)
            # Must have reacted BOTH ways, and enough times to matter.
            if highs < 1 or lows < 1 or total < min_touches:
                continue

            # ROLE-REVERSAL DETECTION: walk the touches in time order and count
            # how many times the type flips (resistance<->support).
            chrono = sorted(cl, key=lambda x: x[0])              # by index = time
            types = [t for (_, _, t) in chrono]
            role_reversals = sum(1 for a, b in zip(types, types[1:]) if a != b)

            prices = [p for (_, p, _) in cl]
            idxs = [i for (i, _, _) in cl]
            last_index = max(idxs)
            center = round(sum(prices) / len(prices), 2)
            z_low = round(min(prices), 2)
            z_high = round(max(prices), 2)
            strongest = self._strongest_level(prices)  # densest reaction price in zone

            touch_score = min(total / 6.0, 1.0)              # 6+ reactions = fully proven
            reversal_score = min(role_reversals / 4.0, 1.0)  # 4+ flips = fully proven magnet
            recency = last_index / (n - 1)
            # Role reversals are the defining feature, so weight them heavily.
            strength = round(0.35 * touch_score + 0.40 * reversal_score + 0.25 * recency, 2)

            touch_points = sorted(
                ({"date": dates[i], "price": round(p, 2), "type": t} for (i, p, t) in cl),
                key=lambda x: x["date"],
            )

            zones.append({
                "center": center,
                "low": z_low,
                "high": z_high,
                "width": round(z_high - z_low, 2),
                "strongest_level": strongest,
                "touches": total,
                "highs": highs,             # resistance reactions
                "lows": lows,               # support reactions
                "role_reversals": role_reversals,
                "strength": strength,
                "distance_pct": round((center - current_price) / current_price * 100, 2),
                "touch_points": touch_points,
            })

        # Rank by role reversals first (most-flipped = most significant), then
        # by total reactions, then strength.
        zones.sort(key=lambda z: (z["role_reversals"], z["touches"], z["strength"]),
                   reverse=True)
        return zones[:top]

    def _strongest_level(self, prices, tight_tol_pct=0.6):
        """Within a zone, the single price with the highest CONCENTRATION of
        reactions — the densest sub-cluster of touch prices. This is where inside
        the zone the market reacted most strongly."""
        best_avg, best_count = prices[0], 0
        for p in prices:
            members = [q for q in prices if abs(q - p) / p * 100 <= tight_tol_pct]
            if len(members) > best_count:
                best_count = len(members)
                best_avg = sum(members) / len(members)
        return round(best_avg, 2)

    def _pick_spaced(self, zones, max_levels, min_gap_pct=1.5):
        """Pick the strongest levels while keeping each at least min_gap_pct from
        every already-picked level — so the chart has no overlapping S/R lines."""
        picked = []
        for z in sorted(zones, key=lambda x: x["strength"], reverse=True):
            if len(picked) >= max_levels:
                break
            if all(abs(z["level"] - k["level"]) / k["level"] * 100 >= min_gap_pct
                   for k in picked):
                picked.append(z)
        return picked

    def _zones_from(self, clusters, current_price, dates, n, min_touches):
        """Turn pivot clusters into scored zone dicts (touches + recency strength)."""
        zones = []
        for cluster in clusters:
            touches = len(cluster)
            if touches < min_touches:
                continue  # a single touch is noise, not a level
            prices = [p for (_, p) in cluster]
            indices = [i for (i, _) in cluster]
            last_index = max(indices)
            level = round(sum(prices) / len(prices), 2)

            touch_score = min(touches / 4.0, 1.0)   # 4+ touches = fully proven
            recency = last_index / (n - 1)           # most-recent touch closeness (0..1)
            strength = round(0.6 * touch_score + 0.4 * recency, 2)

            # Every individual touch (date + the price at that touch), oldest first,
            # so the frontend can mark each one on the chart.
            touch_points = sorted(
                ({"date": dates[i], "price": round(p, 2)} for (i, p) in cluster),
                key=lambda t: t["date"],
            )

            zones.append({
                "level": level,
                "touches": touches,
                "strength": strength,
                "last_touch_date": dates[last_index],
                "touch_points": touch_points,
                "distance_pct": round((level - current_price) / current_price * 100, 2),
            })
        return zones

    def _cluster(self, pivots, tolerance_pct):
        """Greedily group pivots whose price is within tolerance_pct of the
        running cluster average."""
        if not pivots:
            return []
        ordered = sorted(pivots, key=lambda x: x[1])  # by price
        clusters = [[ordered[0]]]
        for piv in ordered[1:]:
            current = clusters[-1]
            avg = sum(p for (_, p) in current) / len(current)
            if abs(piv[1] - avg) / avg * 100 <= tolerance_pct:
                current.append(piv)
            else:
                clusters.append([piv])
        return clusters

    def _signal(self, support, resistance):
        """A light proximity signal for the confluence engine to use later.
        Near strong support -> mildly bullish; near strong resistance -> bearish."""
        near_support = support[0] if support else None
        near_resistance = resistance[0] if resistance else None
        if near_support and abs(near_support["distance_pct"]) <= 2:
            return "bullish", near_support["strength"]
        if near_resistance and abs(near_resistance["distance_pct"]) <= 2:
            return "bearish", near_resistance["strength"]
        return "neutral", 0.0

    def _empty(self, current_price, note):
        return {
            "signal": "neutral",
            "confidence": 0.0,
            "details": {"current_price": current_price,
                        "support": [], "resistance": [], "note": note},
            "viz": {"levels": []},
        }
