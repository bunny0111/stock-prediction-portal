"""
Sequence forecasting research — does the raw price SEQUENCE contain predictive
information beyond a naive forecast?

Gate logic (per spec): establish strong baselines first; only escalate to
deep learning IF a simple sequence model beats naive in walk-forward.

Leakage-safe: features at day i use returns up to day i; target is return i+1.
Validation: EXPANDING-WINDOW walk-forward (train older, test newer), no shuffle.
"""
import os
import time
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "stock_prediction_main.settings")
django.setup()

import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from analysis.services.market_data import MarketDataService, MarketDataError

TICKERS = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
           "SBIN.NS", "WIPRO.NS", "MARUTI.NS", "LT.NS", "AXISBANK.NS", "KOTAKBANK.NS",
           "BHARTIARTL.NS", "ITC.NS", "HINDUNILVR.NS", "TITAN.NS", "SUNPHARMA.NS",
           "TATASTEEL.NS", "TATAMOTORS.NS", "BAJFINANCE.NS", "HCLTECH.NS",
           "ASIANPAINT.NS", "POWERGRID.NS", "NTPC.NS", "ULTRACEMCO.NS", "GRASIM.NS"]

m = MarketDataService()
series = {}
for t in TICKERS:
    try:
        c = m.get_ohlcv(t, period="10y")["candles"]
    except MarketDataError:
        continue
    closes = np.array([x["close"] for x in c], float)
    dates = [x["date"] for x in c]
    if len(closes) < 400:
        continue
    rets = closes[1:] / closes[:-1] - 1
    series[t] = (dates[1:], closes[1:], rets)
    time.sleep(0.15)
print(f"Loaded {len(series)} stocks (10y daily).")


def build(W):
    rows = []
    for t, (dts, cl, rt) in series.items():
        L = len(rt)
        for i in range(W - 1, L - 1):
            rows.append((dts[i], rt[i - W + 1:i + 1], rt[i + 1], cl[i], cl[i + 1]))
    rows.sort(key=lambda r: r[0])
    X = np.array([r[1] for r in rows]); yret = np.array([r[2] for r in rows])
    pt = np.array([r[3] for r in rows]); pt1 = np.array([r[4] for r in rows])
    fold_year = [r[0][:4] for r in rows]
    return X, yret, pt, pt1, fold_year


def metrics(pred_ret, yret, pt, pt1):
    pred_price = pt * (1 + pred_ret)
    mae = np.mean(np.abs(pred_ret - yret))
    rmse = np.sqrt(np.mean((pred_ret - yret) ** 2))
    mape = np.mean(np.abs(pt1 - pred_price) / pt1) * 100
    diracc = np.mean(np.sign(pred_ret) == np.sign(yret)) * 100
    return mae, rmse, mape, diracc


def walk_forward(W, n_folds=6):
    X, yret, pt, pt1, yr = build(W)
    n = len(X)
    bounds = [int(n * k / n_folds) for k in range(n_folds + 1)]
    # accumulate test predictions across folds 1..n_folds-1 (expanding train)
    preds = {"naive": [], "mean": [], "AR_linear": [], "RF": []}
    truth = {"yret": [], "pt": [], "pt1": [], "yr": []}
    for k in range(1, n_folds):
        tr = slice(0, bounds[k]); teidx = slice(bounds[k], bounds[k + 1])
        Xtr, ytr = X[tr], yret[tr]
        Xte, yte = X[teidx], yret[teidx]
        preds["naive"].append(np.zeros(len(yte)))
        preds["mean"].append(np.full(len(yte), ytr.mean()))
        preds["AR_linear"].append(LinearRegression().fit(Xtr, ytr).predict(Xte))
        rf = RandomForestRegressor(n_estimators=120, max_depth=6, n_jobs=-1, random_state=0)
        preds["RF"].append(rf.fit(Xtr, ytr).predict(Xte))
        truth["yret"].append(yte); truth["pt"].append(pt[teidx])
        truth["pt1"].append(pt1[teidx]); truth["yr"].append(np.array(yr[bounds[k]:bounds[k + 1]]))
    for d in (preds, truth):
        for kk in d: d[kk] = np.concatenate(d[kk])
    print(f"\n===== WINDOW = {W} days  (test samples: {len(truth['yret'])}) =====")
    print(f"  {'model':10}{'MAE':>9}{'RMSE':>9}{'MAPE%':>8}{'DirAcc%':>9}{'vs naive RMSE':>15}")
    nb = metrics(preds["naive"], truth["yret"], truth["pt"], truth["pt1"])
    for name in ["naive", "mean", "AR_linear", "RF"]:
        mae, rmse, mape, da = metrics(preds[name], truth["yret"], truth["pt"], truth["pt1"])
        imp = (nb[1] - rmse) / nb[1] * 100
        print(f"  {name:10}{mae:>9.5f}{rmse:>9.5f}{mape:>8.2f}{da:>9.1f}{imp:>+14.2f}%")
    # robustness: AR_linear directional accuracy by year
    print("  AR_linear directional accuracy by test-year:")
    line = "    "
    for y in sorted(set(truth["yr"])):
        msk = truth["yr"] == y
        if msk.sum() > 30:
            da = np.mean(np.sign(preds["AR_linear"][msk]) == np.sign(truth["yret"][msk])) * 100
            line += f"{y}:{da:.0f}%  "
    print(line)


for W in [20, 50, 100]:
    walk_forward(W)
print("\nDone.")
