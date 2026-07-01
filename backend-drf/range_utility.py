"""
Utility analysis: does the empirical-quantile Range Forecast add information
BEYOND a naive ATR band or a Gaussian-volatility band — or is it just
repackaging volatility?

For every out-of-sample stock-day (leakage-safe, trailing window only) we build
three next-day intervals and compare width, asymmetry, calibration, and the
regime/confidence signal.
  A) ATR band        : price * (1 ± z * ATR%)          [symmetric]
  B) Volatility band : price * (1 ± z * rolling_std)   [symmetric, Gaussian]
  C) Empirical (prod): EWMA-adjusted empirical return quantiles [asymmetric]
"""
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "stock_prediction_main.settings")
django.setup()

import numpy as np
import pandas as pd
from scipy.stats import norm
from analysis.services.market_data import MarketDataService, MarketDataError

m = MarketDataService()
STOCKS = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS",
          "WIPRO.NS", "MARUTI.NS", "LT.NS", "AXISBANK.NS", "ITC.NS", "HINDUNILVR.NS",
          "TITAN.NS", "SUNPHARMA.NS", "TATASTEEL.NS", "^NSEI"]
WIN, LAM = 252, 0.94
Z = {90: norm.ppf(0.95), 70: norm.ppf(0.85)}   # 1.645, 1.036

rows = []
for t in STOCKS:
    try:
        c = m.get_ohlcv(t, period="10y")["candles"]
    except MarketDataError:
        continue
    df = pd.DataFrame(c)
    if len(df) < WIN + 200:
        continue
    close, high, low = df["close"], df["high"], df["low"]
    ret = close.pct_change()
    sig = ret.rolling(WIN).std()
    ewm = ret.ewm(alpha=1 - LAM).std()
    regime = (ewm / sig).clip(0.5, 2.0)
    tr = np.maximum(high - low, np.maximum((high - close.shift(1)).abs(), (low - close.shift(1)).abs()))
    atr_pct = (tr.rolling(14).mean() / close)           # ATR as a return fraction
    q = {p: (ret.rolling(WIN).quantile((1 - p / 100) / 2),
             ret.rolling(WIN).quantile(1 - (1 - p / 100) / 2)) for p in (90, 70)}
    nret = ret.shift(-1)
    d = pd.DataFrame({"tkr": t, "date": df["date"], "close": close,
                      "sig": sig, "atr": atr_pct, "regime": regime, "nret": nret})
    for p in (90, 70):
        d[f"emp_lo{p}"] = q[p][0] * regime
        d[f"emp_hi{p}"] = q[p][1] * regime
    rows.append(d)

D = pd.concat(rows).dropna().reset_index(drop=True)
print(f"Out-of-sample stock-days: {len(D)}  across {D['tkr'].nunique()} symbols\n")


def cover(lo, hi):
    return ((D["nret"] >= lo) & (D["nret"] <= hi)).mean() * 100


print("=== Q5: METHOD COMPARISON (coverage vs nominal, avg width) ===")
print(f"  {'level':>6}{'method':>14}{'coverage%':>11}{'avgWidth%':>11}")
for p in (90, 70):
    z = Z[p]
    methods = {
        "ATR-band": (-z * D["atr"], z * D["atr"]),
        "Vol-band": (-z * D["sig"], z * D["sig"]),
        "Empirical": (D[f"emp_lo{p}"], D[f"emp_hi{p}"]),
    }
    for name, (lo, hi) in methods.items():
        print(f"  {p:>5}%{name:>14}{cover(lo, hi):>10.1f}%{(hi - lo).mean() * 100:>10.2f}%")
    print()

# widths for the 90% level
emp_w = (D["emp_hi90"] - D["emp_lo90"])
atr_w = 2 * Z[90] * D["atr"]
vol_w = 2 * Z[90] * D["sig"]

print("=== Q1: EMPIRICAL vs ATR band — how different is the WIDTH? ===")
rel = (emp_w - atr_w).abs() / atr_w
print(f"  corr(empirical width, ATR width)      = {np.corrcoef(emp_w, atr_w)[0,1]:.3f}")
print(f"  corr(empirical width, Vol width)      = {np.corrcoef(emp_w, vol_w)[0,1]:.3f}")
print(f"  median |relative width difference|    = {rel.median()*100:.1f}%")
print(f"  share of days differing > 10%         = {(rel > 0.10).mean()*100:.1f}%")
print(f"  share of days differing > 20%         = {(rel > 0.20).mean()*100:.1f}%")
print(f"  (ATR band is on avg {(atr_w/emp_w).mean():.2f}x the empirical width)\n")

print("=== Q2: ASYMMETRY — empirical vs (always-symmetric) ATR/Vol band ===")
up = D["emp_hi90"]; dn = -D["emp_lo90"]
asym = (up - dn) / (up + dn)            # >0 upside wider, <0 downside wider
print(f"  mean signed asymmetry                 = {asym.mean()*100:+.1f}%  (sign: + = upside wider)")
print(f"  mean |asymmetry|                      = {asym.abs().mean()*100:.1f}%")
print(f"  share of days |asymmetry| > 10%       = {(asym.abs() > 0.10).mean()*100:.1f}%")
print(f"  share of days |asymmetry| > 20%       = {(asym.abs() > 0.20).mean()*100:.1f}%")
print(f"  share of days downside wider than up  = {(dn > up).mean()*100:.1f}%   (ATR/Vol band: 0% — always symmetric)\n")

print("=== Q3: EXAMPLES where ATR and empirical disagree most ===")
D2 = D.assign(rel=rel, asym=asym, emp_w=emp_w, atr_w=atr_w)
ex = D2.reindex((D2["rel"] + D2["asym"].abs()).sort_values(ascending=False).index).head(5)
for _, r in ex.iterrows():
    pr = r["close"]
    a_lo, a_hi = pr * (1 - Z[90]*r["atr"]), pr * (1 + Z[90]*r["atr"])
    e_lo, e_hi = pr * (1 + r["emp_lo90"]), pr * (1 + r["emp_hi90"])
    print(f"  {r['tkr']:11} {r['date']}  px={pr:.1f}")
    print(f"     ATR 90%  : {a_lo:8.1f} to {a_hi:8.1f}  (width {(a_hi-a_lo):.1f}, symmetric)")
    print(f"     Empirical: {e_lo:8.1f} to {e_hi:8.1f}  (width {(e_hi-e_lo):.1f}, asym {r['asym']*100:+.0f}%)")

print("\n=== Q4: does CONFIDENCE (regime ratio) add info beyond ATR? ===")
print(f"  corr(regime_ratio, ATR%)              = {np.corrcoef(D['regime'], D['atr'])[0,1]:.3f}  (low = orthogonal to ATR level)")
print(f"  corr(ATR%,        |next-day return|)  = {np.corrcoef(D['atr'], D['nret'].abs())[0,1]:.3f}")
print(f"  corr(regime_ratio,|next-day return|)  = {np.corrcoef(D['regime'], D['nret'].abs())[0,1]:.3f}")
# conditional 90% coverage by regime bucket (does Low-confidence flag real breach risk?)
D3 = D.assign(emp_lo=D["emp_lo90"], emp_hi=D["emp_hi90"])
D3["inside"] = (D3["nret"] >= D3["emp_lo"]) & (D3["nret"] <= D3["emp_hi"])
print("  90% coverage by regime bucket (forecast confidence):")
for lab, lo, hi in [("calm  (<0.90)", 0, 0.90), ("normal(0.90-1.15)", 0.90, 1.15), ("expanding(>1.15)", 1.15, 9)]:
    msk = (D3["regime"] >= lo) & (D3["regime"] < hi)
    if msk.sum() > 100:
        print(f"     {lab:20} n={msk.sum():6d}  coverage={D3.loc[msk,'inside'].mean()*100:.1f}%")
print("\nDone.")
