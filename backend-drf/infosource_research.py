"""
Information-source audit: do EXTERNAL sources (market context, relative strength,
regime) add predictive value beyond the stock's own OHLCV?

Method: build OHLCV-only feature set and an OHLCV+market feature set, evaluate
both with expanding-window walk-forward, and quantify the INCREMENTAL change
(directional accuracy + RMSE) over OHLCV-only and over naive. Leakage-safe.
"""
import os
import time
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "stock_prediction_main.settings")
django.setup()

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.feature_selection import mutual_info_classif
from analysis.services.market_data import MarketDataService, MarketDataError

m = MarketDataService()
STOCKS = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS",
          "WIPRO.NS", "MARUTI.NS", "LT.NS", "AXISBANK.NS", "KOTAKBANK.NS", "BHARTIARTL.NS",
          "ITC.NS", "HINDUNILVR.NS", "TITAN.NS", "SUNPHARMA.NS", "TATASTEEL.NS",
          "BAJFINANCE.NS", "HCLTECH.NS", "ASIANPAINT.NS"]


def close_map(ticker):
    c = m.get_ohlcv(ticker, period="10y")["candles"]
    return {x["date"]: x["close"] for x in c}


nifty = close_map("^NSEI")
try:
    vix = close_map("^INDIAVIX")
    HAVE_VIX = True
except MarketDataError:
    vix, HAVE_VIX = {}, False
print(f"NIFTY days: {len(nifty)} | India VIX: {'loaded '+str(len(vix)) if HAVE_VIX else 'UNAVAILABLE'}")

OHLCV = ["sret", "sret5", "sret20", "atr_pct", "rel_vol"]
MARKET = ["nret1", "nret5", "nret20", "ntrend", "rel1", "relmom20", "corr60"] + (["vix", "vix_chg"] if HAVE_VIX else [])

frames = []
for t in STOCKS:
    try:
        c = m.get_ohlcv(t, period="10y")["candles"]
    except MarketDataError:
        continue
    sc = {x["date"]: x for x in c}
    common = sorted(d for d in sc if d in nifty and (not HAVE_VIX or d in vix))
    if len(common) < 400:
        continue
    df = pd.DataFrame(index=common)
    df["close"] = [sc[d]["close"] for d in common]
    df["high"] = [sc[d]["high"] for d in common]
    df["low"] = [sc[d]["low"] for d in common]
    df["vol"] = [sc[d]["volume"] for d in common]
    df["nclose"] = [nifty[d] for d in common]
    if HAVE_VIX:
        df["vix"] = [vix[d] for d in common]
        df["vix_chg"] = df["vix"].pct_change()
    df["sret"] = df["close"].pct_change()
    df["nret1"] = df["nclose"].pct_change()
    df["sret5"] = df["close"] / df["close"].shift(5) - 1
    df["sret20"] = df["close"] / df["close"].shift(20) - 1
    df["nret5"] = df["nclose"] / df["nclose"].shift(5) - 1
    df["nret20"] = df["nclose"] / df["nclose"].shift(20) - 1
    tr = np.maximum(df["high"] - df["low"],
                    np.maximum((df["high"] - df["close"].shift(1)).abs(),
                               (df["low"] - df["close"].shift(1)).abs()))
    df["atr_pct"] = tr.rolling(14).mean() / df["close"] * 100
    df["rel_vol"] = df["vol"] / df["vol"].rolling(20).mean()
    df["ntrend"] = (df["nclose"] > df["nclose"].rolling(50).mean()).astype(int)
    df["rel1"] = df["sret"] - df["nret1"]
    df["relmom20"] = df["sret20"] - df["nret20"]
    df["corr60"] = df["sret"].rolling(60).corr(df["nret1"])
    df["y"] = df["close"].shift(-1) / df["close"] - 1
    df["ydir"] = (df["y"] > 0).astype(int)
    df["date"] = df.index
    frames.append(df[["date"] + OHLCV + MARKET + ["y", "ydir"]].dropna())

data = pd.concat(frames).sort_values("date").reset_index(drop=True)
print(f"Dataset: {len(data)} rows | OHLCV feats {len(OHLCV)} | +market feats {len(MARKET)}\n")

# --- predictive information of the NEW (market) features vs direction ---
mi = mutual_info_classif(data[MARKET].values, data["ydir"].values, random_state=0)
print("=== Mutual information of EXTERNAL features with next-day direction ===")
for f, v in sorted(zip(MARKET, mi), key=lambda z: -z[1]):
    print(f"  {f:10} {v:.4f}")

# --- walk-forward: OHLCV-only vs OHLCV+market ---
def walk(features):
    n = len(data); nf = 6; b = [int(n * k / nf) for k in range(nf + 1)]
    pc, pr, yt, ydir = [], [], [], []
    for k in range(1, nf):
        tr_, te_ = slice(0, b[k]), slice(b[k], b[k + 1])
        Xtr, Xte = data[features].values[tr_], data[features].values[te_]
        cm = RandomForestClassifier(n_estimators=120, max_depth=6, n_jobs=-1, random_state=0).fit(Xtr, data["ydir"].values[tr_])
        rm = RandomForestRegressor(n_estimators=120, max_depth=6, n_jobs=-1, random_state=0).fit(Xtr, data["y"].values[tr_])
        pc.append(cm.predict(Xte)); pr.append(rm.predict(Xte))
        yt.append(data["y"].values[te_]); ydir.append(data["ydir"].values[te_])
    pc, pr, yt, ydir = map(np.concatenate, (pc, pr, yt, ydir))
    acc = (pc == ydir).mean() * 100
    rmse = np.sqrt(np.mean((pr - yt) ** 2))
    return acc, rmse, ydir, yt

print("\n=== WALK-FORWARD: OHLCV-only vs OHLCV+Market/Relative/Regime ===")
acc_o, rmse_o, ydir, yt = walk(OHLCV)
acc_m, rmse_m, _, _ = walk(OHLCV + MARKET)
base_dir = max(ydir.mean(), 1 - ydir.mean()) * 100
naive_rmse = np.sqrt(np.mean(yt ** 2))
print(f"  baseline majority dir = {base_dir:.1f}% | naive RMSE = {naive_rmse:.5f}")
print(f"  OHLCV-only      : DirAcc {acc_o:.1f}%   RMSE {rmse_o:.5f}")
print(f"  OHLCV + Market  : DirAcc {acc_m:.1f}%   RMSE {rmse_m:.5f}")
print(f"  INCREMENTAL     : DirAcc {acc_m-acc_o:+.2f}pp   RMSE {(rmse_o-rmse_m)/rmse_o*100:+.2f}% (vs OHLCV)")
print(f"  vs NAIVE        : OHLCV {(naive_rmse-rmse_o)/naive_rmse*100:+.2f}%   +Market {(naive_rmse-rmse_m)/naive_rmse*100:+.2f}%")
print("\nNote: Event features (earnings/news sentiment) NOT tested — no rigorous historical free data.")
print("Done.")
