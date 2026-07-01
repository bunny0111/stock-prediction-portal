"""
BacktestService
===============
Replays history to measure whether the system's trade signals actually worked.

For each test date (point-in-time, NO look-ahead):
  1. Compute the opportunity using ONLY data up to that date (as_of).
  2. If it flags a trade, simulate it forward bar-by-bar: did price hit the
     TARGET or the STOP first (within a max holding period)?
  3. Record the outcome as an R-multiple (win = +R:R, loss = -1R).

Then aggregate: win rate, profit factor, average R, max drawdown — and crucially
break it down by CONFLUENCE SCORE BAND, to test the core claim that higher-
confluence setups perform better.

Avoiding look-ahead bias: the signal at date D uses candles <= D (the services
filter on as_of); the outcome uses candles strictly AFTER D from the same fetch.
"""

from .market_data import MarketDataService
from .opportunity import OpportunityService
from .support_resistance import SupportResistanceService
from .volume_analysis import VolumeAnalysisService
from .trend_analysis import TrendAnalysisService


class BacktestService:
    def __init__(self, market_data_service=None):
        self.market = market_data_service or MarketDataService()
        self.opportunity = OpportunityService(self.market)
        # Shared cached market data, so these add little cost per trade.
        self.sr = SupportResistanceService(self.market)
        self.volume = VolumeAnalysisService(self.market)
        self.trend = TrendAnalysisService(self.market)

    def run(self, ticker, period="2y", interval="1d",
            step=5, max_holding=20, min_history=150, min_rr=0, min_score=0,
            target_method="A"):
        data = self.market.get_ohlcv(ticker, period=period, interval=interval)
        candles = data["candles"]
        n = len(candles)
        if n < min_history + max_holding + 10:
            return {"trades": 0, "note": "Not enough history to backtest this ticker."}

        trades = []
        trade_id = 1
        for i in range(min_history, n - max_holding, step):
            as_of = candles[i]["date"]
            opp = self.opportunity.analyze(ticker, period=period, interval=interval,
                                           as_of=as_of, light=True, min_rr=min_rr,
                                           target_method=target_method)["details"]
            if opp.get("no_trade", True):
                continue
            # Skip setups below the minimum confluence score (e.g. drop Weak ones).
            if opp.get("confluence_score", 0) < min_score:
                continue
            target = opp["targets"][0]["price"] if opp.get("targets") else None
            if target is None or opp["risk"] <= 0:
                continue

            sim = self._simulate(
                candles, i, opp["direction"], opp["entry"], opp["stop_loss"],
                target, opp["risk"], max_holding
            )

            # Capture the FULL market-condition snapshot at the trade date so every
            # trade can be audited later (why it was generated, what was present).
            sr_snap = self.sr.analyze(ticker, period=period, interval=interval,
                                      as_of=as_of)["details"]
            vol_res = self.volume.analyze(ticker, period=period, interval=interval,
                                          as_of=as_of)
            trend_snap = self.trend.analyze(ticker, period=period, interval=interval,
                                            as_of=as_of, compute_trendlines=False)["details"]

            trades.append(self._build_trade(
                trade_id, ticker, candles, i, opp, sim, sr_snap, vol_res, trend_snap
            ))
            trade_id += 1

        return self._aggregate(trades, ticker, period)

    # ----------------------------------------------------------------- helpers

    def _simulate(self, candles, i, side, entry, stop, target, risk, max_holding):
        """Walk forward from the bar AFTER the signal; stop or target, first hit wins.
        Returns the outcome plus the exit bar index and exit price."""
        end = min(i + 1 + max_holding, len(candles))
        for j in range(i + 1, end):
            hi, lo = candles[j]["high"], candles[j]["low"]
            hit_stop = (lo <= stop) if side == "long" else (hi >= stop)
            hit_target = (hi >= target) if side == "long" else (lo <= target)
            if hit_stop:                       # conservative: stop wins ties
                return {"result": "loss", "r_multiple": -1.0,
                        "exit_index": j, "exit_price": stop}
            if hit_target:
                reward = (target - entry) if side == "long" else (entry - target)
                return {"result": "win", "r_multiple": round(reward / risk, 2),
                        "exit_index": j, "exit_price": target}

        # Neither hit within the holding window — settle at the last close.
        last_idx = end - 1
        last_close = candles[last_idx]["close"]
        move = (last_close - entry) if side == "long" else (entry - last_close)
        return {"result": "open", "r_multiple": round(move / risk, 2),
                "exit_index": last_idx, "exit_price": round(last_close, 2)}

    def _build_trade(self, tid, ticker, candles, i, opp, sim, sr_snap, vol_res, trend_snap=None):
        """Assemble the full trade record + the market-condition snapshot at entry."""
        side = opp["direction"]
        entry = opp["entry"]
        exit_idx = sim["exit_index"]
        exit_price = sim["exit_price"]
        entry_date = candles[i]["date"]
        exit_date = candles[exit_idx]["date"]

        ret = ((exit_price - entry) if side == "long" else (entry - exit_price)) / entry * 100

        # Target/stop geometry — to diagnose whether targets are unrealistic.
        stop = opp["stop_loss"]
        target = opp["targets"][0]["price"]
        atr = opp.get("atr") or 0
        t_dist = abs(target - entry)
        s_dist = abs(entry - stop)
        target_distance_pct = round(t_dist / entry * 100, 2) if entry else None
        stop_distance_pct = round(s_dist / entry * 100, 2) if entry else None
        target_atr = round(t_dist / atr, 2) if atr else None
        stop_atr = round(s_dist / atr, 2) if atr else None
        risk_reward = opp["targets"][0].get("risk_reward")

        def sr_level(z):
            return {"level": z["level"], "touches": z["touches"],
                    "strength": int(z["strength"] * 100),
                    "distance_pct": round((z["level"] - entry) / entry * 100, 2)}

        def zone(z):
            return {"center": z["center"], "low": z["low"], "high": z["high"],
                    "touches": z["touches"], "highs": z["highs"], "lows": z["lows"],
                    "role_reversals": z["role_reversals"],
                    "strength": int(z["strength"] * 100),
                    "distance_pct": round((z["center"] - entry) / entry * 100, 2)}

        support = [sr_level(z) for z in sr_snap.get("support", [])]
        resistance = [sr_level(z) for z in sr_snap.get("resistance", [])]
        key_zones = [zone(z) for z in sr_snap.get("key_zones", [])]

        return {
            "id": tid,
            "ticker": ticker,
            "entry_date": entry_date,
            "exit_date": exit_date,
            "trade_type": "CNC",                 # delivery / multi-day positional
            "side": side,
            "entry_price": entry,
            "exit_price": exit_price,
            "stop_loss": opp["stop_loss"],
            "target": opp["targets"][0]["price"],
            "holding_period": exit_idx - i,      # bars (trading days)
            "outcome": sim["result"],
            "return_pct": round(ret, 2),
            "r_multiple": sim["r_multiple"],
            "atr": round(atr, 2),
            "target_distance_pct": target_distance_pct,
            "stop_distance_pct": stop_distance_pct,
            "target_atr": target_atr,
            "stop_atr": stop_atr,
            "risk_reward": risk_reward,
            "score": opp["confluence_score"],    # kept for aggregation/bands
            "confluence_score": opp["confluence_score"],
            "trend_signal": opp.get("trend_direction"),
            "trend_strength": opp.get("trend_strength"),
            # Raw measurements (for measurement-vs-outcome analysis, no scoring).
            "trend_slope": (trend_snap or {}).get("slope_pct_per_bar"),
            "trend_r2": (trend_snap or {}).get("r_squared"),
            "atr_pct": round(atr / entry * 100, 2) if entry else None,
            "obv_trend": vol_res.get("details", {}).get("obv_trend"),
            "volume_signal": vol_res.get("signal"),
            "relative_volume": vol_res.get("details", {}).get("relative_volume"),
            "support": support,
            "resistance": resistance,
            "key_zones": key_zones,
            "trigger": self._trigger(side, opp, sr_snap),
        }

    def _trigger(self, side, opp, sr_snap):
        """Human-readable reason the trade was generated."""
        near = ""
        if side == "long" and sr_snap.get("support"):
            z = sr_snap["support"][0]
            near = f"; price near support {z['level']} ({z['touches']} touches)"
        elif side == "short" and sr_snap.get("resistance"):
            z = sr_snap["resistance"][0]
            near = f"; price near resistance {z['level']} ({z['touches']} touches)"
        trend = f"{opp.get('trend_direction')} ({opp.get('trend_strength')})"
        return (f"{side.upper()} - confluence {opp['confluence_score']} "
                f"({opp['setup_quality']}); trend {trend}{near}")

    def _aggregate(self, trades, ticker, period):
        if not trades:
            return {"trades": 0, "note": "No trade setups were triggered in this period."}

        r = [t["r_multiple"] for t in trades]
        wins = [x for x in r if x > 0]
        gross_win = sum(x for x in r if x > 0)
        gross_loss = -sum(x for x in r if x < 0)

        result = {
            "ticker": ticker,
            "period": period,
            "trades": len(trades),
            "win_rate": round(len(wins) / len(trades) * 100, 1),
            "open_pct": round(len([t for t in trades if t["outcome"] == "open"]) / len(trades) * 100, 1),
            "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else None,
            "avg_r": round(sum(r) / len(r), 2),
            "total_r": round(sum(r), 2),
            "max_drawdown_r": self._max_drawdown(r),
            "by_score_band": self._by_band(trades),
            "target_stop_diagnostics": self._diagnostics(trades),
            "condition_analysis": self._condition_analysis(trades),
            "all_trades": trades,            # full audit trail (every trade)
        }
        result["verdict"] = self._verdict(result)
        return result

    def _verdict(self, res):
        """Plain-English summary of whether these signals had a usable edge."""
        pf = res["profit_factor"] or 0
        avg_r = res["avg_r"]
        total_r = res["total_r"]
        dd = res["max_drawdown_r"]

        if pf >= 1.5 and avg_r >= 0.15:
            rating, line = "Decent edge", "the setups were net profitable with a reasonable payoff."
        elif pf >= 1.2 and avg_r > 0:
            rating, line = "Marginal edge", "slightly profitable, but not strong — trade with caution."
        elif pf >= 1.0 and avg_r >= 0:
            rating, line = "Breakeven", "essentially no edge — the signals barely covered their losses."
        else:
            rating, line = "No edge", "these signals lost money over the test — not tradeable as-is."

        # Flag a drawdown that dwarfs the gains.
        warn = ""
        if total_r > 0 and dd < 0 and abs(dd) > 2 * total_r:
            warn = (f" Warning: the worst drawdown ({dd}R) is far larger than the total gain "
                    f"({total_r}R) — a poor risk profile.")

        # Does higher confluence actually help? Only judge if BOTH bands have a
        # meaningful sample (>=5 trades) — otherwise the comparison is just noise.
        bands = res["by_score_band"]
        edge_note = ""
        MIN_SAMPLE = 5
        if "Weak" in bands and "Moderate" in bands:
            weak_n = bands["Weak"]["trades"]
            mod_n = bands["Moderate"]["trades"]
            if weak_n >= MIN_SAMPLE and mod_n >= MIN_SAMPLE:
                if bands["Moderate"]["avg_r"] > bands["Weak"]["avg_r"]:
                    edge_note = " Higher-confluence setups did better than weak ones — the score is adding value."
                else:
                    edge_note = " Higher-confluence setups did NOT beat weak ones here — the score isn't helping on this stock."
            else:
                edge_note = " (Too few trades in one score band to judge whether the score helps — widen the test or lower the filters.)"

        return {"rating": rating, "text": f"{rating}: {line}{warn}{edge_note}"}

    def _diagnostics(self, trades):
        """Target/stop geometry overall and split by outcome — evidence for whether
        targets are unrealistic (far in ATR terms) vs entries simply being weak."""
        def avg(items, key):
            vals = [t[key] for t in items if t.get(key) is not None]
            return round(sum(vals) / len(vals), 2) if vals else None

        groups = {
            "all": trades,
            "win": [t for t in trades if t["outcome"] == "win"],
            "loss": [t for t in trades if t["outcome"] == "loss"],
            "open": [t for t in trades if t["outcome"] == "open"],
        }
        return {
            name: {
                "trades": len(items),
                "avg_target_distance_pct": avg(items, "target_distance_pct"),
                "avg_stop_distance_pct": avg(items, "stop_distance_pct"),
                "avg_target_atr": avg(items, "target_atr"),
                "avg_stop_atr": avg(items, "stop_atr"),
                "avg_rr": avg(items, "risk_reward"),
            }
            for name, items in groups.items()
        }

    def _group_stats(self, trades, bucket_fn):
        """Group trades by bucket_fn(trade)->label and compute stats per bucket."""
        buckets = {}
        for t in trades:
            label = bucket_fn(t)
            if label is None:
                continue
            buckets.setdefault(label, []).append(t)

        out = {}
        for label, items in buckets.items():
            r = [x["r_multiple"] for x in items]
            gw = sum(x for x in r if x > 0)
            gl = -sum(x for x in r if x < 0)
            out[label] = {
                "trades": len(items),
                "win_rate": round(len([x for x in r if x > 0]) / len(items) * 100, 1),
                "avg_return_pct": round(sum(x["return_pct"] for x in items) / len(items), 2),
                "avg_r": round(sum(r) / len(r), 2),
                "profit_factor": round(gw / gl, 2) if gl > 0 else None,
                "total_r": round(sum(r), 2),
            }
        return out

    def _condition_analysis(self, trades):
        """Winners-vs-losers stats grouped by market condition — using ONLY the
        snapshot already captured per trade. No new indicators."""
        def score_band(t):
            s = t["confluence_score"]
            for lo, hi in [(0, 20), (21, 40), (41, 60), (61, 80), (81, 100)]:
                if lo <= s <= hi:
                    return f"{lo}-{hi}"

        def relvol_band(t):
            v = t.get("relative_volume")
            if v is None:
                return None
            return ("<0.7" if v < 0.7 else "0.7-1.0" if v < 1.0 else
                    "1.0-1.5" if v < 1.5 else "1.5-2.0" if v < 2.0 else "2.0+")

        def entry_level_strength(t):
            levels = t["support"] if t["side"] == "long" else t["resistance"]
            if not levels:
                return None
            s = levels[0]["strength"]
            return ("0-50" if s < 50 else "51-70" if s < 70 else
                    "71-85" if s < 85 else "86-100")

        def dist_band(levels):
            if not levels:
                return None
            d = abs(levels[0]["distance_pct"])
            return ("0-1%" if d < 1 else "1-3%" if d < 3 else "3-5%" if d < 5 else "5%+")

        def role_flips(t):
            rf = max((z["role_reversals"] for z in t.get("key_zones", [])), default=0)
            return "3+" if rf >= 3 else str(rf)

        def holding(t):
            h = t["holding_period"]
            return ("1-3d" if h <= 3 else "4-7d" if h <= 7 else
                    "8-14d" if h <= 14 else "15+d")

        return {
            "by_confluence_band": self._group_stats(trades, score_band),
            "by_trend_strength": self._group_stats(trades, lambda t: t.get("trend_strength") or "unknown"),
            "by_relative_volume": self._group_stats(trades, relvol_band),
            "by_sr_strength": self._group_stats(trades, entry_level_strength),
            "by_distance_to_support": self._group_stats(trades, lambda t: dist_band(t["support"])),
            "by_distance_to_resistance": self._group_stats(trades, lambda t: dist_band(t["resistance"])),
            "by_role_flips": self._group_stats(trades, role_flips),
            "by_holding_period": self._group_stats(trades, holding),
        }

    def _max_drawdown(self, r_multiples):
        """Largest peak-to-trough drop of the cumulative R equity curve."""
        equity = peak = 0.0
        max_dd = 0.0
        for x in r_multiples:
            equity += x
            peak = max(peak, equity)
            max_dd = min(max_dd, equity - peak)
        return round(max_dd, 2)

    def _by_band(self, trades):
        bands = {"Weak": (0, 30), "Moderate": (31, 60),
                 "Strong": (61, 80), "Very Strong": (81, 100)}
        out = {}
        for name, (lo, hi) in bands.items():
            bt = [t for t in trades if lo <= t["score"] <= hi]
            if bt:
                rr = [t["r_multiple"] for t in bt]
                out[name] = {
                    "trades": len(bt),
                    "win_rate": round(len([x for x in rr if x > 0]) / len(bt) * 100, 1),
                    "avg_r": round(sum(rr) / len(rr), 2),
                }
        return out
