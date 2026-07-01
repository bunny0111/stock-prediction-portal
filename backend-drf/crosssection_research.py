"""
Cross-sectional forecasting: is future RELATIVE performance (rank) more
predictable than future absolute return?

For each day we rank the universe by next-day return and test whether a model
(or simple baselines) can predict that ranking. Metrics: daily Spearman rank
correlation, top-group relative return, top-group hit rate. Walk-forward.
"""
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "stock_prediction_main.settings")
django.setup()

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import RandomForestRegressor
from analysis.services.market_data import MarketDataService, MarketDataError

m = MarketDataService()
STOCKS = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS",
          "WIPRO.NS", "MARUTI.NS", "LT.NS", "AXISBANK.NS", "KOTAKBANK.NS", "BHARTIARTL.NS",
          "ITC.NS", "HINDUNILVR.NS", "TITAN.NS", "SUNPHARMA.NS", "TATASTEEL.NS",
          "BAJFINANCE.NS", "HCLTECH.NS", "ASIANPAINT.NS", "POWERGRID.NS", "NTPC.NS",
          "GRASIM.NS", "TATAMOTORS.NS", "ULTRACEMCO.NS"]

FEATURES = ["ret_1d", "ret_5d", "ret_20d", "atr_pct", "rel_vol", "ret_60d"]
frames = []
for t in STOCKS:
    try:
        c = m.get_ohlcv(t, period="10y")["candles"]
    except MarketDataError:
        continue
    df = pd.DataFrame(c)
    if len(df) < 400:
        continue
    df["ret_1d"] = df["close"].pct_change()
    df["ret_5d"] = df["close"] / df["close"].shift(5) - 1
    df["ret_20d"] = df["close"] / df["close"].shift(20) - 1
    df["ret_60d"] = df["close"] / df["close"].shift(60) - 1
    tr = np.maximum(df["high"] - df["low"],
                    np.maximum((df["high"] - df["close"].shift(1)).abs(),
                               (df["low"] - df["close"].shift(1)).abs()))
    df["atr_pct"] = tr.rolling(14).mean() / df["close"] * 100
    df["rel_vol"] = df["volume"] / df["volume"].rolling(20).mean()
    df["next_ret"] = df["close"].shift(-1) / df["close"] - 1
    df["stock"] = t
    frames.append(df[["date", "stock"] + FEATURES + ["next_ret"]].dropna())

panel = pd.concat(frames).reset_index(drop=True)
# keep only days with a full-enough cross-section to rank
counts = panel.groupby("date")["stock"].count()
good_days = counts[counts >= 8].index
panel = panel[panel["date"].isin(good_days)].sort_values("date").reset_index(drop=True)
dates = sorted(panel["date"].unique())
print(f"Panel: {len(panel)} stock-days across {len(dates)} days, ~{len(panel)//len(dates)} stocks/day\n")


def day_metrics(sub, pred_col):
    """Spearman + top-group relative return for one day."""
    if len(sub) < 8:
        return None
    actual = sub["next_ret"].values
    pred = sub[pred_col].values
    rho = spearmanr(pred, actual).correlation
    k = max(1, int(round(len(sub) * 0.2)))           # top quintile
    top = sub.sort_values(pred_col, ascending=False).head(k)
    rel = top["next_ret"].mean() - actual.mean()      # vs universe mean that day
    hit = (top["next_ret"] > actual.mean()).mean()    # frac of leaders that beat the mean
    return rho, rel, hit


# --- walk-forward RF (predicts next_ret; rank by it) ---
nf = 6
b = [int(len(dates) * k / nf) for k in range(nf + 1)]
panel["pred_rf"] = np.nan
for k in range(1, nf):
    tr_dates = set(dates[:b[k]]); te_dates = set(dates[b[k]:b[k + 1]])
    tr = panel[panel["date"].isin(tr_dates)]; te = panel[panel["date"].isin(te_dates)]
    rf = RandomForestRegressor(n_estimators=150, max_depth=7, n_jobs=-1, random_state=0)
    rf.fit(tr[FEATURES].values, tr["next_ret"].values)
    panel.loc[panel["date"].isin(te_dates), "pred_rf"] = rf.predict(te[FEATURES].values)

# baselines (deterministic predictors)
panel["pred_rand"] = np.random.default_rng(0).standard_normal(len(panel))
panel["pred_mom1"] = panel["ret_1d"]          # short-term momentum
panel["pred_rev1"] = -panel["ret_1d"]         # short-term reversal
panel["pred_mom20"] = panel["ret_20d"]        # 20d momentum

test = panel[panel["pred_rf"].notna()]
print(f"Test stock-days (walk-forward): {len(test)}\n")
print(f"  {'predictor':14}{'meanSpearman':>14}{'topRelRet%':>12}{'topHitRate%':>13}")
for name, col in [("Random", "pred_rand"), ("Momentum-1d", "pred_mom1"),
                  ("Reversal-1d", "pred_rev1"), ("Momentum-20d", "pred_mom20"),
                  ("RandomForest", "pred_rf")]:
    rhos, rels, hits = [], [], []
    for d, sub in test.groupby("date"):
        r = day_metrics(sub, col)
        if r and not np.isnan(r[0]):
            rhos.append(r[0]); rels.append(r[1]); hits.append(r[2])
    print(f"  {name:14}{np.mean(rhos):>14.4f}{np.mean(rels)*100:>12.4f}{np.mean(hits)*100:>13.1f}")
print("\n(topRelRet% = avg next-day return of predicted top-quintile MINUS universe mean)")
print("Done.")
