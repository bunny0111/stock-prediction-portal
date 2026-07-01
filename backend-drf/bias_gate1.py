"""
GATE 1 — Trend-bias accuracy gate.

Can ANY trend-bias engine predict next-day (and 3d/5d) DIRECTION better than
baselines, by a margin that would survive costs? Two engines:
  - RULE-BASED : Bull/Bear/Neutral from slope + structure (MA) + momentum vote
  - ML         : RandomForest over all portal features, walk-forward

Baselines: majority class, random (50%), trend-following (continuation).
Leakage-safe: features at day i use data <= i; target is direction at i+h.
PASS bar: directional accuracy consistently >= ~52-53% AND beats baselines.
If it fails, STOP — do not build a plan on a non-edge.
"""
import os
import warnings
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "stock_prediction_main.settings")
django.setup()
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from analysis.services.opportunity_scan import WATCHLIST
from analysis.services.market_data import MarketDataService, MarketDataError

m = MarketDataService()
START = 210
HORIZONS = [1, 3, 5]
FEATS = ["slope60", "r2", "ret1", "ret5", "ret20", "ret60",
         "ma_gap50", "ma_gap200", "ma_cross", "atr_pct", "rel_vol", "regime"]


def lr(y):
    x = np.arange(len(y))
    s, b = np.polyfit(x, y, 1)
    yh = s * x + b
    ss = ((y - yh) ** 2).sum(); st = ((y - y.mean()) ** 2).sum()
    return s, (1 - ss / st if st > 0 else 0.0)


rows = []
for tk in WATCHLIST:
    try:
        c = m.get_ohlcv(tk, period="10y")["candles"]
    except MarketDataError:
        continue
    df = pd.DataFrame(c)
    if len(df) < START + 300:
        continue
    close = df["close"].values; high = df["high"].values; low = df["low"].values
    vol = df["volume"].values; dates = df["date"].values
    ret = np.concatenate([[np.nan], close[1:] / close[:-1] - 1])
    ma50 = pd.Series(close).rolling(50).mean().values
    ma200 = pd.Series(close).rolling(200).mean().values
    tr = np.maximum(high - low, np.maximum(np.abs(high - np.roll(close, 1)), np.abs(low - np.roll(close, 1))))
    atr = pd.Series(tr).rolling(14).mean().values
    sig = pd.Series(ret).rolling(252).std().values
    ewm = pd.Series(ret).ewm(alpha=0.06).std().values
    n = len(close)
    for i in range(START, n - max(HORIZONS) - 1):
        y = close[i - 59:i + 1]
        slope, r2 = lr(y)
        slope_pct = slope / y.mean() * 100
        ret20 = close[i] / close[i - 20] - 1
        ret5 = close[i] / close[i - 5] - 1
        feat = {
            "tkr": tk, "date": dates[i],
            "slope60": slope_pct, "r2": r2,
            "ret1": ret[i], "ret5": ret5, "ret20": ret20, "ret60": close[i] / close[i - 60] - 1,
            "ma_gap50": close[i] / ma50[i] - 1, "ma_gap200": close[i] / ma200[i] - 1,
            "ma_cross": 1 if ma50[i] > ma200[i] else 0,
            "atr_pct": atr[i] / close[i], "rel_vol": vol[i] / vol[i - 20:i].mean(),
            "regime": ewm[i] / sig[i] if sig[i] else 1.0,
        }
        # rule-based vote
        net = (np.sign(slope_pct) + np.sign(ret20) + np.sign(ret5)
               + (1 if close[i] > ma50[i] else -1) + (1 if ma50[i] > ma200[i] else -1))
        feat["rule"] = "bull" if net >= 2 else "bear" if net <= -2 else "neutral"
        for h in HORIZONS:
            feat[f"y{h}"] = int(close[i + h] > close[i])
        rows.append(feat)
    print(f"  loaded {tk}")

P = pd.DataFrame(rows).dropna().sort_values("date").reset_index(drop=True)
print(f"\nPanel: {len(P)} stock-days, {P['tkr'].nunique()} stocks\n")


def walk_ml(y_col, n_folds=6):
    n = len(P); b = [int(n * k / n_folds) for k in range(n_folds + 1)]
    pred, proba, truth = [], [], []
    for k in range(1, n_folds):
        tr, te = slice(0, b[k]), slice(b[k], b[k + 1])
        clf = RandomForestClassifier(n_estimators=150, max_depth=6, n_jobs=-1, random_state=0)
        clf.fit(P[FEATS].values[tr], P[y_col].values[tr])
        pr = clf.predict_proba(P[FEATS].values[te])
        pred.append(clf.predict(P[FEATS].values[te]))
        proba.append(pr.max(axis=1))
        truth.append(P[y_col].values[te])
    return map(np.concatenate, (pred, proba, truth))


print(f"  {'horizon':>8}{'majority':>10}{'trendFollow':>13}{'rule(cov)':>16}{'ML-all':>9}{'ML-conf(cov)':>16}")
verdict_acc = []
for h in HORIZONS:
    yc = f"y{h}"
    maj = max(P[yc].mean(), 1 - P[yc].mean()) * 100
    tf = (P[(P["ret20"] > 0).values][yc].mean() * 100)        # continuation of 20d trend (approx)
    tf_acc = ((P["ret20"] > 0).astype(int) == P[yc]).mean() * 100
    # rule on non-neutral rows
    nz = P[P["rule"] != "neutral"]
    rpred = (nz["rule"] == "bull").astype(int)
    racc = (rpred == nz[yc]).mean() * 100
    rcov = len(nz) / len(P) * 100
    pred, proba, truth = walk_ml(yc)
    ml_all = (pred == truth).mean() * 100
    conf = proba > 0.55
    ml_conf = (pred[conf] == truth[conf]).mean() * 100 if conf.sum() else float("nan")
    ml_cov = conf.mean() * 100
    verdict_acc += [ml_all, racc]
    print(f"  {str(h)+'d':>8}{maj:>9.1f}%{tf_acc:>12.1f}%{racc:>10.1f}%({rcov:>3.0f}%){ml_all:>8.1f}%{ml_conf:>11.1f}%({ml_cov:>3.0f}%)")

# per-stock robustness for 1d ML
print("\n  Per-stock 1d ML directional accuracy (walk-forward within stock pooled test):")
pred, proba, truth = walk_ml("y1")
te_start = int(len(P) * 1 / 6)
test_tkr = P["tkr"].values[te_start:te_start + len(truth)]
beats = []
for tk in P["tkr"].unique():
    mk = test_tkr == tk
    if mk.sum() > 50:
        a = (pred[mk] == truth[mk]).mean() * 100
        beats.append(a)
beats = np.array(beats)
print(f"     stocks tested: {len(beats)}  | mean {beats.mean():.1f}%  | "
      f"share beating 52%: {(beats >= 52).mean()*100:.0f}%  | best {beats.max():.1f}%  worst {beats.min():.1f}%")

best = max(verdict_acc)
print("\n=== GATE 1 VERDICT ===")
print(f"  best directional accuracy across engines/horizons = {best:.1f}%")
if best < 52:
    print("  FAIL — no engine clears ~52%. Trend bias has no exploitable directional edge. STOP.")
elif best < 53:
    print("  MARGINAL — within noise of 52%; unlikely to survive costs. Lean STOP.")
else:
    print("  PASS (provisional) — an engine clears the bar; proceed to Gate 2 with cost-aware backtest.")
print("\nDone.")
