"""
Probabilistic next-day RANGE forecasting — calibration study.

We do NOT predict direction. We predict an interval [low, high] for the next
day and ask: does a nominal P% interval actually contain the outcome P% of the
time (calibration)? Volatility clusters, so range is forecastable even though
direction is not.

Methods compared (all leakage-safe: every estimate at day t uses returns <= t,
targets are strictly day t+1):
  - Normal-sigma : close-to-close rolling std, parametric normal quantiles
  - EWMA-sigma   : RiskMetrics lambda=0.94 conditional vol, normal quantiles
  - Empirical    : rolling empirical quantiles of past returns (fat-tail aware)
  - ATR-band     : high/low band from rolling ATR

Reported per nominal level (50/70/90):
  - empirical coverage of next-day CLOSE
  - average interval width (%)
And a high/low band study (does actual next-day high/low stay within band).
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
          "WIPRO.NS", "MARUTI.NS", "LT.NS", "AXISBANK.NS", "KOTAKBANK.NS", "BHARTIARTL.NS",
          "ITC.NS", "HINDUNILVR.NS", "TITAN.NS", "SUNPHARMA.NS", "TATASTEEL.NS",
          "BAJFINANCE.NS", "HCLTECH.NS", "ASIANPAINT.NS"]

LEVELS = [0.50, 0.70, 0.90]
WIN = 250            # trailing lookback
BURN = 260           # skip until we have a full window
LAM = 0.94           # RiskMetrics EWMA decay

cov = {f"{lbl}|{int(p*100)}": {"hit": [], "w": []}
       for lbl in ["Normal", "EWMA", "Empirical", "ATR"] for p in LEVELS}
# high/low band coverage (using ATR-style + empirical of up/dn extents)
hl = {f"{int(p*100)}": {"hi_ok": [], "lo_ok": [], "both": [], "w": []} for p in LEVELS}


def add(d, k, hit, w):
    d[k]["hit"].append(hit); d[k]["w"].append(w)


for t in STOCKS:
    try:
        c = m.get_ohlcv(t, period="10y")["candles"]
    except MarketDataError:
        continue
    df = pd.DataFrame(c)
    if len(df) < BURN + 200:
        continue
    close, high, low = df["close"], df["high"], df["low"]
    ret = close.pct_change()

    # --- volatility estimates known at day t (use returns up to and incl. t) ---
    sig_roll = ret.rolling(WIN).std()
    sig_ewma = ret.ewm(alpha=1 - LAM).std()
    # true range -> ATR%, known at t
    tr = np.maximum(high - low, np.maximum((high - close.shift(1)).abs(),
                                           (low - close.shift(1)).abs()))
    atr_pct = (tr.rolling(14).mean() / close)
    # empirical quantiles of past returns (rolling)
    q = {p: (ret.rolling(WIN).quantile((1 - p) / 2),
             ret.rolling(WIN).quantile(1 - (1 - p) / 2)) for p in LEVELS}
    # extents for high/low band: today's up/down move vs prior close
    up = (high - close.shift(1)) / close.shift(1)
    dn = (close.shift(1) - low) / close.shift(1)
    qup = {p: up.rolling(WIN).quantile(p) for p in LEVELS}
    qdn = {p: dn.rolling(WIN).quantile(p) for p in LEVELS}

    # --- targets: strictly next day ---
    nret = close.shift(-1) / close - 1
    nhi = high.shift(-1) / close - 1          # next high vs today's close
    nlo = close / low.shift(-1) - 1           # today's close vs next low (>=0 if low<close)

    for i in range(BURN, len(df) - 1):
        r = nret.iloc[i]
        if np.isnan(r):
            continue
        for p in LEVELS:
            z = norm.ppf(1 - (1 - p) / 2)
            tag = int(p * 100)
            # Normal sigma
            s = sig_roll.iloc[i]
            add(cov, f"Normal|{tag}", int(abs(r) <= z * s), 2 * z * s * 100)
            # EWMA sigma
            se = sig_ewma.iloc[i]
            add(cov, f"EWMA|{tag}", int(abs(r) <= z * se), 2 * z * se * 100)
            # Empirical
            lo_q, hi_q = q[p][0].iloc[i], q[p][1].iloc[i]
            add(cov, f"Empirical|{tag}", int(lo_q <= r <= hi_q), (hi_q - lo_q) * 100)
            # ATR band (symmetric k*ATR with normal z on ATR as vol proxy)
            a = atr_pct.iloc[i]
            add(cov, f"ATR|{tag}", int(abs(r) <= z * a), 2 * z * a * 100)
            # high/low band (empirical extents)
            uq, dq = qup[p].iloc[i], qdn[p].iloc[i]
            hi_ok = int(nhi.iloc[i] <= uq)             # actual next high within predicted high
            lo_ok = int(nlo.iloc[i] <= dq)             # actual next low within predicted low
            hl[f"{tag}"]["hi_ok"].append(hi_ok)
            hl[f"{tag}"]["lo_ok"].append(lo_ok)
            hl[f"{tag}"]["both"].append(int(hi_ok and lo_ok))
            hl[f"{tag}"]["w"].append((uq + dq) * 100)

n = len(cov["Normal|90"]["hit"])
print(f"Samples (stock-days, out-of-sample): {n}\n")
print("=== CLOSE-RETURN INTERVAL CALIBRATION ===")
print("  (well-calibrated = empirical coverage ~ nominal; closer is better)")
print(f"  {'method':12}{'nominal':>9}{'coverage':>10}{'gap':>8}{'avgWidth%':>11}")
for lbl in ["Normal", "EWMA", "Empirical", "ATR"]:
    for p in LEVELS:
        k = f"{lbl}|{int(p*100)}"
        c_ = np.mean(cov[k]["hit"]) * 100
        w_ = np.nanmean(cov[k]["w"])
        print(f"  {lbl:12}{int(p*100):>8}%{c_:>9.1f}%{c_-p*100:>+8.1f}{w_:>11.2f}")
    print()

print("=== HIGH / LOW BAND CALIBRATION (empirical extents) ===")
print(f"  {'nominal':>9}{'highOK':>9}{'lowOK':>9}{'bothIn':>9}{'avgBand%':>10}")
for p in LEVELS:
    k = f"{int(p*100)}"
    print(f"  {int(p*100):>8}%{np.mean(hl[k]['hi_ok'])*100:>8.1f}%{np.mean(hl[k]['lo_ok'])*100:>8.1f}%"
          f"{np.mean(hl[k]['both'])*100:>8.1f}%{np.nanmean(hl[k]['w']):>10.2f}")
print("\nDone.")
