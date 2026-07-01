"""
Forecasting research: do the platform's measurements contain predictive
information when used as MODEL FEATURES (not hand-crafted rules)?

Leakage-safe: every feature at date t uses only data <= t (services via as_of,
rolling windows via [:i+1]); targets use closes strictly AFTER t (t+1..t+5).
Models are evaluated with a TIME-BASED split (train older, test newer) — no
shuffling — so the test set is genuinely out-of-sample in time.
"""
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "stock_prediction_main.settings")
django.setup()

import numpy as np
import pandas as pd
from analysis.services.market_data import MarketDataService
from analysis.services.support_resistance import SupportResistanceService
from analysis.services.confluence import ConfluenceScoringService
from analysis.indicators.trend import linear_regression
from analysis.indicators.volatility import average_true_range
from analysis.indicators.volume import on_balance_volume

PERIOD = "5y"
SAMPLE_STEP = 5
START = 220          # need ~60 (regression) + 20 (vol) + buffer
TICKERS = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
           "SBIN.NS", "WIPRO.NS", "MARUTI.NS", "LT.NS", "AXISBANK.NS"]

market, sr, conf = MarketDataService(), SupportResistanceService(), ConfluenceScoringService()


def build_for(ticker):
    candles = market.get_ohlcv(ticker, period=PERIOD)["candles"]
    n = len(candles)
    closes = np.array([c["close"] for c in candles], float)
    highs = np.array([c["high"] for c in candles], float)
    lows = np.array([c["low"] for c in candles], float)
    vols = np.array([c["volume"] for c in candles], float)
    dates = [c["date"] for c in candles]
    obv = on_balance_volume(list(closes), list(vols))
    rows = []
    for i in range(START, n - 6, SAMPLE_STEP):
        # --- cheap features from data up to i ---
        sl, _, r2 = linear_regression(list(range(60)), list(closes[i - 59:i + 1]))
        slope_pct = sl / closes[i - 59:i + 1].mean() * 100
        atr = average_true_range(list(highs[:i + 1]), list(lows[:i + 1]), list(closes[:i + 1]), 14) or 0
        f = {
            "ticker": ticker, "date": dates[i],
            "ret_1d": closes[i] / closes[i - 1] - 1,
            "ret_5d": closes[i] / closes[i - 5] - 1,
            "atr_pct": atr / closes[i] * 100 if closes[i] else np.nan,
            "rel_vol": vols[i] / vols[i - 20:i].mean() if vols[i - 20:i].mean() else np.nan,
            "trend_slope": slope_pct,
            "trend_r2": r2,
            "obv_up": 1 if obv[i] > obv[i - 20] else 0,
        }
        # --- service features (as_of = point-in-time) ---
        srd = sr.analyze(ticker, period=PERIOD, as_of=dates[i])["details"]
        sup, res, kz = srd.get("support", []), srd.get("resistance", []), srd.get("key_zones", [])
        f["dist_support"] = abs(sup[0]["distance_pct"]) if sup else np.nan
        f["dist_resistance"] = abs(res[0]["distance_pct"]) if res else np.nan
        f["sup_touches"] = sup[0]["touches"] if sup else np.nan
        f["res_touches"] = res[0]["touches"] if res else np.nan
        f["role_flips"] = max((z["role_reversals"] for z in kz), default=0)
        cd = conf.analyze(ticker, period=PERIOD, as_of=dates[i], light=True)["details"]
        f["conf_score"] = cd.get("score")
        # --- targets (strictly future) ---
        f["tgt_ret1"] = closes[i + 1] / closes[i] - 1
        f["tgt_dir"] = int(closes[i + 1] > closes[i])
        f["tgt_ret3"] = closes[i + 3] / closes[i] - 1
        f["tgt_ret5"] = closes[i + 5] / closes[i] - 1
        rows.append(f)
    return rows


print("Building dataset (leakage-safe, point-in-time)...")
allrows = []
for t in TICKERS:
    r = build_for(t)
    allrows += r
    print(f"  {t:13} {len(r)} rows")
df = pd.DataFrame(allrows).dropna().reset_index(drop=True)
df = df.sort_values("date").reset_index(drop=True)
FEATURES = ["ret_1d", "ret_5d", "atr_pct", "rel_vol", "trend_slope", "trend_r2",
            "obv_up", "dist_support", "dist_resistance", "sup_touches",
            "res_touches", "role_flips", "conf_score"]
print(f"\nDataset: {len(df)} rows, {len(FEATURES)} features\n")

# ---------- 1. LEAKAGE CHECK ----------
print("=== LEAKAGE CHECK (feature vs next-day return correlation) ===")
print("  (|corr| > ~0.3 would be suspicious for this domain)")
for f in FEATURES:
    c = df[f].corr(df["tgt_ret1"])
    flag = "  <-- HIGH (check!)" if abs(c) > 0.3 else ""
    print(f"  {f:15} corr(tgt_ret1) = {c:+.3f}{flag}")

# ---------- 2. CORRELATION with targets ----------
print("\n=== CORRELATION of features with each target ===")
print(f"  {'feature':15}{'ret1':>8}{'dir':>8}{'ret3':>8}{'ret5':>8}")
for f in FEATURES:
    print(f"  {f:15}{df[f].corr(df['tgt_ret1']):>8.3f}{df[f].corr(df['tgt_dir']):>8.3f}"
          f"{df[f].corr(df['tgt_ret3']):>8.3f}{df[f].corr(df['tgt_ret5']):>8.3f}")

# ---------- 3. INFORMATION (mutual info) + 4. IMPORTANCE ----------
from sklearn.feature_selection import mutual_info_classif
from sklearn.ensemble import RandomForestClassifier
X = df[FEATURES].values
ydir = df["tgt_dir"].values
mi = mutual_info_classif(X, ydir, random_state=0)
rf_imp = RandomForestClassifier(n_estimators=200, max_depth=6, random_state=0).fit(X, ydir).feature_importances_
print("\n=== INFORMATION VALUE (mutual info) & RF IMPORTANCE for direction ===")
print(f"  {'feature':15}{'mutual_info':>12}{'rf_importance':>14}")
for f, m, imp in sorted(zip(FEATURES, mi, rf_imp), key=lambda z: -z[2]):
    print(f"  {f:15}{m:>12.4f}{imp:>14.4f}")

# ---------- 5. MODEL COMPARISON (time split) ----------
from sklearn.linear_model import LogisticRegression, LinearRegression
from sklearn.ensemble import RandomForestRegressor, HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.preprocessing import StandardScaler

cut = int(len(df) * 0.7)
tr, te = df.iloc[:cut], df.iloc[cut:]
Xtr, Xte = tr[FEATURES].values, te[FEATURES].values
scaler = StandardScaler().fit(Xtr)
Xtr_s, Xte_s = scaler.transform(Xtr), scaler.transform(Xte)
print(f"\n=== MODELS (time split: train {len(tr)} older / test {len(te)} newer) ===")

# Direction (classification)
ytr_d, yte_d = tr["tgt_dir"].values, te["tgt_dir"].values
base_dir = max(yte_d.mean(), 1 - yte_d.mean())  # majority-class baseline
print(f"\n  NEXT-DAY DIRECTION accuracy  (baseline majority = {base_dir*100:.1f}%):")
for name, m, xs in [("LogisticReg", LogisticRegression(max_iter=1000), (Xtr_s, Xte_s)),
                    ("RandomForest", RandomForestClassifier(n_estimators=300, max_depth=6, random_state=0), (Xtr, Xte)),
                    ("HistGradBoost", HistGradientBoostingClassifier(random_state=0), (Xtr, Xte))]:
    m.fit(xs[0], ytr_d)
    acc = (m.predict(xs[1]) == yte_d).mean()
    print(f"     {name:14} {acc*100:5.1f}%   ({'beats' if acc>base_dir+0.005 else 'NO better than'} baseline)")

# Return (regression) — does it beat naive 'tomorrow=today' (predict 0)?
ytr_r, yte_r = tr["tgt_ret1"].values, te["tgt_ret1"].values
rmse = lambda p: np.sqrt(np.mean((p - yte_r) ** 2))
naive_rmse = rmse(np.zeros_like(yte_r))
print(f"\n  NEXT-DAY RETURN RMSE  (naive tomorrow=today = {naive_rmse:.5f}):")
for name, m, xs in [("LinearReg", LinearRegression(), (Xtr_s, Xte_s)),
                    ("RandomForest", RandomForestRegressor(n_estimators=300, max_depth=6, random_state=0), (Xtr, Xte)),
                    ("HistGradBoost", HistGradientBoostingRegressor(random_state=0), (Xtr, Xte))]:
    m.fit(xs[0], ytr_r)
    p = m.predict(xs[1])
    dir_acc = (np.sign(p) == np.sign(yte_r)).mean()
    print(f"     {name:14} RMSE {rmse(p):.5f}  dir_acc {dir_acc*100:.1f}%  ({'beats' if rmse(p)<naive_rmse else 'WORSE than'} naive)")

# 5-day direction (longer horizon may carry more signal)
ytr_5, yte_5 = (tr["tgt_ret5"] > 0).astype(int).values, (te["tgt_ret5"] > 0).astype(int).values
base5 = max(yte_5.mean(), 1 - yte_5.mean())
m5 = HistGradientBoostingClassifier(random_state=0).fit(Xtr, ytr_5)
acc5 = (m5.predict(Xte) == yte_5).mean()
print(f"\n  5-DAY DIRECTION  baseline {base5*100:.1f}%  HistGradBoost {acc5*100:.1f}%  "
      f"({'beats' if acc5>base5+0.005 else 'NO better than'} baseline)")
print("\nDone.")
