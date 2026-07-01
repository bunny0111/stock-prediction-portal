"""
Controlled A/B: CURRENT (two-sided regime scaling) vs WIDEN-ONLY
(regime_ratio = max(1.0, regime_ratio)).  Production code is NOT modified.

Same out-of-sample stock-days for both arms. Reports overall calibration,
interval width, calibration by confidence bucket, and a regime stress test.
Leakage-safe: every interval uses only the trailing window before the target day.
"""
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "stock_prediction_main.settings")
django.setup()

import numpy as np
import pandas as pd
from analysis.services.market_data import MarketDataService, MarketDataError

m = MarketDataService()
STOCKS = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS",
          "WIPRO.NS", "MARUTI.NS", "LT.NS", "AXISBANK.NS", "ITC.NS", "HINDUNILVR.NS",
          "TITAN.NS", "SUNPHARMA.NS", "TATASTEEL.NS", "^NSEI"]
WIN, LAM = 252, 0.94
LEVELS = [50, 70, 90]

rows = []
for t in STOCKS:
    try:
        c = m.get_ohlcv(t, period="10y")["candles"]
    except MarketDataError:
        continue
    df = pd.DataFrame(c)
    if len(df) < WIN + 200:
        continue
    ret = df["close"].pct_change()
    sig = ret.rolling(WIN).std()
    ewm = ret.ewm(alpha=1 - LAM).std()
    raw = (ewm / sig).clip(0.5, 2.0)            # current regime_ratio
    cur = raw                                    # current scaling
    wid = raw.clip(lower=1.0)                     # widen-only: max(1.0, ratio)
    d = pd.DataFrame({"tkr": t, "date": df["date"], "raw": raw,
                      "cur": cur, "wid": wid, "nret": ret.shift(-1)})
    for p in LEVELS:
        a = (1 - p / 100) / 2
        d[f"q_lo{p}"] = ret.rolling(WIN).quantile(a)
        d[f"q_hi{p}"] = ret.rolling(WIN).quantile(1 - a)
    rows.append(d)

D = pd.concat(rows).dropna().reset_index(drop=True)
# confidence label from the RAW ratio (same for both arms — label semantics unchanged)
D["conf"] = np.where(D["raw"] <= 0.90, "High",
            np.where(D["raw"] <= 1.15, "Medium", "Low"))
D["year"] = D["date"].str[:4]
print(f"Out-of-sample stock-days: {len(D)}  across {D['tkr'].nunique()} symbols\n")


def cover_width(mask, arm, p):
    sub = D[mask]
    lo = sub[f"q_lo{p}"] * sub[arm]
    hi = sub[f"q_hi{p}"] * sub[arm]
    cov = ((sub["nret"] >= lo) & (sub["nret"] <= hi)).mean() * 100
    w = (hi - lo).mean() * 100
    return cov, w


ALL = D["nret"].notna()
print("=== 1 & 2: OVERALL CALIBRATION + AVG WIDTH ===")
print(f"  {'level':>6} | {'CURRENT cov':>12}{'width':>8} | {'WIDEN cov':>11}{'width':>8} | {'cov gain':>9}{'width +':>9}")
for p in LEVELS:
    cc, cw = cover_width(ALL, "cur", p)
    wc, ww = cover_width(ALL, "wid", p)
    print(f"  {p:>5}% | {cc:>11.1f}%{cw:>7.2f}% | {wc:>10.1f}%{ww:>7.2f}% | {wc-cc:>+8.1f}{(ww-cw)/cw*100:>+8.1f}%")

print("\n=== 3: 90% CALIBRATION BY CONFIDENCE BUCKET ===")
print(f"  {'bucket':>8}{'n':>8} | {'CURRENT':>9} | {'WIDEN':>9} | {'gain':>7}")
for b in ["High", "Medium", "Low"]:
    msk = ALL & (D["conf"] == b)
    cc, _ = cover_width(msk, "cur", 90)
    wc, _ = cover_width(msk, "wid", 90)
    print(f"  {b:>8}{msk.sum():>8} | {cc:>8.1f}% | {wc:>8.1f}% | {wc-cc:>+6.1f}")
print("  (target 90%. The fix works if High rises to >= Medium >= Low ordering.)")

print("\n=== 4: REGIME STRESS TEST — 90% coverage by year ===")
print(f"  {'year':>6}{'n':>8} | {'CURRENT':>9} | {'WIDEN':>9}")
for y in sorted(D["year"].unique()):
    msk = ALL & (D["year"] == y)
    if msk.sum() < 200:
        continue
    cc, _ = cover_width(msk, "cur", 90)
    wc, _ = cover_width(msk, "wid", 90)
    flag = "  <-- COVID" if y == "2020" else ""
    print(f"  {y:>6}{msk.sum():>8} | {cc:>8.1f}% | {wc:>8.1f}%{flag}")

# specific COVID crash window
covid = ALL & (D["date"] >= "2020-02-20") & (D["date"] <= "2020-04-30")
cc, cw = cover_width(covid, "cur", 90)
wc, ww = cover_width(covid, "wid", 90)
print(f"\n  COVID crash window 2020-02-20..04-30 (n={covid.sum()}): "
      f"CURRENT {cc:.1f}% (w {cw:.2f}%)  WIDEN {wc:.1f}% (w {ww:.2f}%)")

print("\n=== 5: TRADE-OFF SUMMARY ===")
gaps_cur = np.mean([abs(cover_width(ALL, 'cur', p)[0] - p) for p in LEVELS])
gaps_wid = np.mean([abs(cover_width(ALL, 'wid', p)[0] - p) for p in LEVELS])
wid_inc = np.mean([(cover_width(ALL, 'wid', p)[1] - cover_width(ALL, 'cur', p)[1]) /
                   cover_width(ALL, 'cur', p)[1] * 100 for p in LEVELS])
hi_c, _ = cover_width(ALL & (D["conf"] == "High"), "cur", 90)
lo_c, _ = cover_width(ALL & (D["conf"] == "Low"), "cur", 90)
hi_w, _ = cover_width(ALL & (D["conf"] == "High"), "wid", 90)
lo_w, _ = cover_width(ALL & (D["conf"] == "Low"), "wid", 90)
print(f"  mean |coverage - nominal|:  CURRENT {gaps_cur:.2f}pp  ->  WIDEN {gaps_wid:.2f}pp")
print(f"  avg interval width increase (widen vs current): +{wid_inc:.1f}%")
print(f"  confidence ordering (High vs Low @90%):  CURRENT High {hi_c:.1f}% vs Low {lo_c:.1f}% "
      f"({'INVERTED' if hi_c < lo_c else 'ok'})  ->  WIDEN High {hi_w:.1f}% vs Low {lo_w:.1f}% "
      f"({'INVERTED' if hi_w < lo_w else 'ok'})")
print("\nDone.")
