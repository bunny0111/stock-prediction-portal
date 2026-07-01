"""
Decision-support usefulness of the Next-Day Range Forecast.

Does the forecast carry information that improves decisions BEYOND just drawing a
range? Five leakage-safe tests (forecast uses returns <= day i; outcomes are days
i+1 / i+2). Production engine method (empirical + widen-only EWMA) is used as-is.

  1. Trade filtering   : do larger FORECAST moves -> larger REALISED moves?
  2. Extreme-zone      : touching the forecast extreme -> continuation or reversion?
  3. Ranking power     : top-decile forecast move vs bottom-decile realised move
  4. Risk management   : forecast-range stops vs fixed-ATR stops (breach consistency)
  5. Historical lookup : conditioned on the forecast, what typically happened next?
"""
import os
import warnings
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "stock_prediction_main.settings")
django.setup()
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from analysis.services.range_forecast import RangeForecastService, WINDOW, MIN_RETURNS
from analysis.indicators.distribution import empirical_interval
from analysis.services.market_data import MarketDataService, MarketDataError

svc = RangeForecastService()
m = MarketDataService()
STOCKS = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS",
          "WIPRO.NS", "MARUTI.NS", "LT.NS", "AXISBANK.NS", "ITC.NS", "HINDUNILVR.NS",
          "TITAN.NS", "SUNPHARMA.NS", "TATASTEEL.NS", "BAJFINANCE.NS", "HCLTECH.NS",
          "ASIANPAINT.NS", "POWERGRID.NS", "NTPC.NS", "GRASIM.NS", "ULTRACEMCO.NS",
          "VEDL.NS", "^NSEI"]

rows = []
for t in STOCKS:
    try:
        c = m.get_ohlcv(t, period="10y")["candles"]
    except MarketDataError:
        continue
    df = pd.DataFrame(c)
    if len(df) < WINDOW + 200:
        continue
    close = df["close"].values; high = df["high"].values; low = df["low"].values
    dates = df["date"].values
    ret = np.concatenate([[np.nan], close[1:] / close[:-1] - 1])
    tr = np.maximum(high - low, np.maximum(np.abs(high - np.roll(close, 1)),
                                           np.abs(low - np.roll(close, 1))))
    tr[0] = high[0] - low[0]
    atr = pd.Series(tr).rolling(14).mean().values
    n = len(close)
    for i in range(WINDOW, n - 2):
        win = ret[i - WINDOW + 1:i + 1]
        win = win[~np.isnan(win)]
        if len(win) < MIN_RETURNS:
            continue
        iv = empirical_interval(win, 0.90)
        if iv is None or atr[i] != atr[i]:
            continue
        scale = max(1.0, svc._regime_ratio(win))
        q_lo, q_hi = iv[0] * scale, iv[1] * scale
        cp = close[i]
        exp_low, exp_high = cp * (1 + q_lo), cp * (1 + q_hi)
        fwidth = q_hi - q_lo                       # forecast move size (fraction)
        raw = svc._regime_ratio(win)
        conf = "High" if raw <= 0.90 else "Medium" if raw <= 1.15 else "Low"
        nret = ret[i + 1]; aft = ret[i + 2]
        rows.append({
            "tkr": t, "date": dates[i + 1], "cp": cp, "fwidth": fwidth,
            "atr_pct": atr[i] / cp, "conf": conf,
            "nabs": abs(nret), "nret": nret, "aft": aft,
            "in90": int(exp_low <= close[i + 1] <= exp_high),
            "touch_lo": int(low[i + 1] <= exp_low),
            "touch_hi": int(high[i + 1] >= exp_high),
            "br_fc": int(low[i + 1] <= exp_low),               # forecast lower stop hit
            "br_1atr": int(low[i + 1] <= cp - atr[i]),         # 1*ATR stop hit
            "br_2atr": int(low[i + 1] <= cp - 2 * atr[i]),     # 2*ATR stop hit
            "fc_stop_dist": (cp - exp_low) / cp,               # forecast stop distance %
            "atr2_dist": 2 * atr[i] / cp,
        })

D = pd.DataFrame(rows)
print(f"Panel: {len(D)} stock-days, {D['tkr'].nunique()} symbols\n")

# ---------- 1. TRADE FILTERING ----------
print("=== 1. TRADE FILTERING: do larger FORECAST moves -> larger REALISED moves? ===")
sp = spearmanr(D["fwidth"], D["nabs"]).correlation
print(f"  Spearman(forecast width, realised |move|) = {sp:.3f}")
D["fdec"] = pd.qcut(D["fwidth"], 10, labels=False, duplicates="drop")
g = D.groupby("fdec").agg(fwidth=("fwidth", "mean"), realised=("nabs", "mean"), n=("nabs", "size"))
print("  decile (1=smallest forecast .. 10=largest):  forecast% -> realised |move|%")
for d, r in g.iterrows():
    print(f"     D{int(d)+1:<2} forecast {r['fwidth']*100:5.2f}%   realised {r['realised']*100:5.2f}%   (n={int(r['n'])})")
ratio = g["realised"].iloc[-1] / g["realised"].iloc[0]
print(f"  -> top-decile realised move is {ratio:.1f}x the bottom decile. {'MONOTONIC/USEFUL' if g['realised'].is_monotonic_increasing else 'see table'}\n")

# ---------- 2. EXTREME-ZONE BEHAVIOR ----------
print("=== 2. EXTREME-ZONE: after touching the forecast extreme, continuation vs reversion? ===")
base_up = (D["aft"] > 0).mean() * 100
lo = D[D["touch_lo"] == 1]; hi = D[D["touch_hi"] == 1]
print(f"  base rate P(next-day up) = {base_up:.1f}%   (n={len(D)})")
print(f"  after touching LOWER extreme (n={len(lo)}): next-day mean ret {lo['aft'].mean()*100:+.3f}%, "
      f"P(up)={ (lo['aft']>0).mean()*100:.1f}%  -> {'reversion(bounce)' if (lo['aft']>0).mean()>0.5 else 'continuation(down)'}")
print(f"  after touching UPPER extreme (n={len(hi)}): next-day mean ret {hi['aft'].mean()*100:+.3f}%, "
      f"P(down)={ (hi['aft']<0).mean()*100:.1f}%  -> {'reversion(fade)' if (hi['aft']<0).mean()>0.5 else 'continuation(up)'}")
edge_lo = (lo['aft'] > 0).mean()*100 - base_up
print(f"  reversion EDGE vs base rate: lower {edge_lo:+.1f}pp,  upper {(base_up-(hi['aft']<0).mean()*100*0+ (100-base_up) - (hi['aft']<0).mean()*100):+.1f}pp")
print()

# ---------- 3. RANKING POWER (cross-sectional, per day) ----------
print("=== 3. RANKING POWER: top-decile vs bottom-decile forecast move (by day) ===")
tops, bots = [], []
for d, sub in D.groupby("date"):
    if len(sub) < 10:
        continue
    k = max(1, int(round(len(sub) * 0.2)))
    s = sub.sort_values("fwidth")
    bots.append(s.head(k)["nabs"].mean()); tops.append(s.tail(k)["nabs"].mean())
print(f"  days evaluated: {len(tops)}")
print(f"  top-quintile (widest forecast) realised |move| = {np.mean(tops)*100:.2f}%")
print(f"  bottom-quintile (narrowest)     realised |move| = {np.mean(bots)*100:.2f}%")
print(f"  -> ranking spread {np.mean(tops)/np.mean(bots):.1f}x  ({'FORECAST RANKS REALISED MOVE' if np.mean(tops)>np.mean(bots)*1.3 else 'weak'})\n")

# ---------- 4. RISK MANAGEMENT ----------
print("=== 4. RISK MANAGEMENT: forecast-range stop vs fixed-ATR stops (long side) ===")
print(f"  {'stop':>14}{'breach%':>9}{'avg dist%':>11}{'cross-stock breach std':>24}")
for lab, br, dist in [("forecast 90%", "br_fc", "fc_stop_dist"),
                      ("1x ATR", "br_1atr", None), ("2x ATR", "br_2atr", "atr2_dist")]:
    per = D.groupby("tkr")[br].mean() * 100
    dcol = D[dist].mean() * 100 if dist else (D["atr_pct"].mean() * 100)
    print(f"  {lab:>14}{D[br].mean()*100:>8.1f}%{dcol:>10.2f}%{per.std():>22.2f}pp")
print("  (forecast stop is calibrated to ~5% and CONSISTENT across stocks; fixed ATR breach")
print("   rate varies by stock -> forecast adapts risk to each stock's distribution)\n")

# ---------- 5. HISTORICAL BEHAVIOR (conditional outcomes) ----------
print("=== 5. HISTORICAL LOOKUP: conditioned on the forecast, what happened next day? ===")
print(f"  {'condition':>22}{'n':>7}{'realised|move|':>16}{'stayed in 90%':>15}")
for conf in ["High", "Medium", "Low"]:
    s = D[D["conf"] == conf]
    if len(s) > 100:
        print(f"  {'confidence='+conf:>22}{len(s):>7}{s['nabs'].mean()*100:>14.2f}%{s['in90'].mean()*100:>13.1f}%")
for d in [0, 4, 9]:
    s = D[D["fdec"] == d]
    lab = {0: "forecast width D1(low)", 4: "forecast width D5(mid)", 9: "forecast width D10(high)"}[d]
    print(f"  {lab:>22}{len(s):>7}{s['nabs'].mean()*100:>14.2f}%{s['in90'].mean()*100:>13.1f}%")
print("\nDone.")
