"""
TrendAnalysisService
====================
Detects trend direction, strength, structure, a drawable trendline, and
trendline breaks. Returns the uniform {signal, confidence, details, viz}.

How direction is decided:
  - SLOPE  : least-squares slope of recent closes (rising / falling / flat)
  - STRUCTURE : swing pattern (higher-highs+higher-lows = up, lower+lower = down)
  - We combine them: they must agree (or one is neutral) to call a real trend;
    if they conflict, it's "sideways".
"""

from .market_data import MarketDataService
from ..indicators.pivots import find_swing_points
from ..indicators.trend import linear_regression


class TrendAnalysisService:
    def __init__(self, market_data_service=None):
        self.market = market_data_service or MarketDataService()

    def analyze(self, ticker, period="1y", interval="1d",
                lookback=60, window=5, as_of=None, compute_trendlines=True):
        data = self.market.get_ohlcv(ticker, period=period, interval=interval)
        candles = data["candles"]
        if as_of:
            candles = [c for c in candles if c["date"] <= as_of]

        if len(candles) < max(window * 2 + 10, 30):
            return self._empty("Not enough history for trend analysis.")

        closes = [c["close"] for c in candles]
        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]
        dates = [c["date"] for c in candles]
        n = len(candles)

        # 1. Slope over the recent lookback window.
        lb = min(lookback, n)
        ys = closes[-lb:]
        xs = list(range(lb))
        slope, intercept, r2 = linear_regression(xs, ys)
        mean_price = sum(ys) / lb
        slope_pct = round(slope / mean_price * 100, 3)  # % move per bar

        # 2. Swing structure.
        swing_highs, swing_lows = find_swing_points(highs, lows, window=window)
        structure, struct_dir = self._structure(swing_highs, swing_lows)

        # 3. Combine slope + structure into a final direction.
        direction, signal = self._direction(slope_pct, struct_dir)

        # 4. Strength: cleanliness (R²) + steepness, lower when sideways.
        steepness = min(abs(slope_pct) / 0.3, 1.0)   # ~0.3%/bar counts as steep
        if direction == "sideways":
            strength = round(0.3 * r2, 2)
        else:
            strength = round(0.6 * r2 + 0.4 * steepness, 2)
        strength_label = ("strong" if strength >= 0.66
                          else "moderate" if strength >= 0.33 else "weak")

        # 5. Detect REAL trendlines — lines that 3+ aligned swing pivots touch.
        #    Use FINER pivots (smaller window) here so more genuine lines can form;
        #    the candle-breach validation still rejects any that price doesn't respect.
        #    Skipped in the backtest hot loop (compute_trendlines=False) since
        #    trendlines aren't used downstream there.
        if compute_trendlines:
            fine_highs, fine_lows = find_swing_points(highs, lows, window=3)
            resistance_lines = self._detect_trendlines(fine_highs, dates, n, "resistance", highs, lows)
            support_lines = self._detect_trendlines(fine_lows, dates, n, "support", highs, lows)
            trendlines = resistance_lines + support_lines
        else:
            trendlines = []

        return {
            "signal": signal,
            "confidence": strength,
            "details": {
                "direction": direction,
                "strength": strength,
                "strength_label": strength_label,
                "slope_pct_per_bar": slope_pct,
                "r_squared": round(r2, 2),
                "structure": structure,
                "trendlines_found": len(trendlines),
                "lookback_days": lb,
            },
            "viz": {"trendlines": trendlines},
        }

    # ----------------------------------------------------------------- helpers

    def _structure(self, swing_highs, swing_lows):
        """Classify the swing pattern using the last two highs and last two lows."""
        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return "not enough swings", "sideways"

        h_prev, h_last = swing_highs[-2][1], swing_highs[-1][1]
        l_prev, l_last = swing_lows[-2][1], swing_lows[-1][1]

        if h_last > h_prev and l_last > l_prev:
            return "higher highs & higher lows", "uptrend"
        if h_last < h_prev and l_last < l_prev:
            return "lower highs & lower lows", "downtrend"
        return "mixed (no clear structure)", "sideways"

    def _direction(self, slope_pct, struct_dir):
        slope_dir = ("uptrend" if slope_pct > 0.05
                     else "downtrend" if slope_pct < -0.05 else "sideways")

        if slope_dir == struct_dir and slope_dir != "sideways":
            direction = slope_dir                         # both agree
        elif slope_dir != "sideways" and struct_dir == "sideways":
            direction = slope_dir                         # slope leads
        elif struct_dir != "sideways" and slope_dir == "sideways":
            direction = struct_dir                        # structure leads
        else:
            direction = "sideways"                        # conflict or both flat

        signal = ("bullish" if direction == "uptrend"
                  else "bearish" if direction == "downtrend" else "neutral")
        return direction, signal

    def _detect_trendlines(self, pivots, dates, n, kind, highs, lows,
                           tol_pct=1.0, min_touches=3, top=2,
                           recent_bars=180, min_span=8, max_span=90,
                           max_slope_pct=2.0,
                           breach_pct=1.5, allowed_breaches=1):
        """
        Find SHORT, LOCAL trendlines:
          - only consider pivots within the last `recent_bars`,
          - the two anchor pivots must be `min_span..max_span` bars apart
            (so a line can't stretch across 1-2 years),
          - 3+ pivots must touch the line BETWEEN the anchors,
          - price must respect it (resistance not poked above >1×, support below),
          - the per-bar slope is capped so lines aren't near-vertical.
        Each line is drawn from its first touch to its last touch (+ a small
        forward projection), NOT all the way to today.

        pivots : list of (index, price) — swing highs for resistance, lows for support.
        """
        recent = [(i, p) for (i, p) in pivots if i >= n - recent_bars]
        L = len(recent)
        if L < min_touches:
            return []

        candidates = []
        for a in range(L):
            i1, p1 = recent[a]
            for b in range(a + 1, L):
                i2, p2 = recent[b]
                span = i2 - i1
                if span < min_span or span > max_span:
                    continue
                slope = (p2 - p1) / span
                intercept = p1 - slope * i1
                avg_p = (p1 + p2) / 2.0
                if avg_p <= 0 or abs(slope) / avg_p * 100 > max_slope_pct:
                    continue  # too steep / invalid

                # Count touches (swing pivots sitting on the line).
                touches = []
                for (i, p) in recent:
                    if i < i1 or i > i2:        # only between the anchors
                        continue
                    line_val = slope * i + intercept
                    if line_val <= 0:
                        continue
                    if abs((p - line_val) / line_val * 100) <= tol_pct:
                        touches.append(i)
                if len(touches) < min_touches:
                    continue

                # VALIDATE against actual candles: the line must be respected as a
                # boundary. A support line is invalid if too many candle LOWS trade
                # below it; a resistance line if too many candle HIGHS poke above it.
                breaches = 0
                valid = True
                for i in range(i1, i2 + 1):
                    line_val = slope * i + intercept
                    if line_val <= 0:
                        continue
                    if kind == "support" and lows[i] < line_val * (1 - breach_pct / 100):
                        breaches += 1
                    elif kind == "resistance" and highs[i] > line_val * (1 + breach_pct / 100):
                        breaches += 1
                    if breaches > allowed_breaches:
                        valid = False
                        break
                if not valid:
                    continue

                candidates.append({
                    "slope": slope, "intercept": intercept,
                    "touches": len(touches),
                    "first_i": i1, "last_i": i2, "span": span,
                })

        # Prefer more touches, then more recent; drop overlapping near-duplicates.
        candidates.sort(key=lambda c: (c["touches"], c["last_i"]), reverse=True)
        selected = []
        for c in candidates:
            dup = False
            for s in selected:
                same_sign = (c["slope"] >= 0) == (s["slope"] >= 0)
                overlap = not (c["last_i"] < s["first_i"] or c["first_i"] > s["last_i"])
                if same_sign and overlap and abs(c["slope"] - s["slope"]) <= abs(s["slope"]) * 0.3 + 1e-9:
                    dup = True
                    break
            if not dup:
                selected.append(c)
            if len(selected) >= top:
                break

        result = []
        for c in selected:
            slope, intercept = c["slope"], c["intercept"]
            start_i = c["first_i"]
            # Extend forward past the last touch ONLY while price keeps respecting
            # the line; stop at the first real breach (so we never draw the line
            # through candles that have broken it).
            end_i = c["last_i"]
            for i in range(c["last_i"] + 1, n):
                lv = slope * i + intercept
                if lv <= 0:
                    break
                if kind == "support" and lows[i] < lv * (1 - breach_pct / 100):
                    break
                if kind == "resistance" and highs[i] > lv * (1 + breach_pct / 100):
                    break
                end_i = i
            result.append({
                "type": kind,
                "touches": c["touches"],
                "last_touch_date": dates[c["last_i"]],
                "points": [
                    {"date": dates[start_i], "price": round(slope * start_i + intercept, 2)},
                    {"date": dates[end_i], "price": round(slope * end_i + intercept, 2)},
                ],
            })
        return result

    def _empty(self, note):
        return {
            "signal": "neutral",
            "confidence": 0.0,
            "details": {"direction": "unknown", "note": note},
            "viz": {"trendline": None},
        }
