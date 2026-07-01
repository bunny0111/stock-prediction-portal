"""
Opportunity Scanner historical validation.

Simulates THREE rankers point-in-time across history over the watchlist and asks:
does the Opportunity Score (blend) add information beyond Expected Move and
Static Volatility — or is the expansion component just churn?

  A) Static Volatility   : trailing 252-day std (slow baseline)
  B) Expected Move        : forecast 90% half-width (validated magnitude)
  C) Opportunity Score    : 50/50 cross-sectional blend of Expected Move + Expansion

Metrics: ranking stability, top-5 turnover, expansion's incremental value,
realised-move prediction (cross-sectional), differentiation. Leakage-safe:
forecast at day i uses returns <= i; realised = day i+1.
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
from analysis.services.opportunity_scan import WATCHLIST
from analysis.services.market_data import MarketDataService, MarketDataError

svc = RangeForecastService()
m = MarketDataService()

recs = []
for tk in WATCHLIST:
    try:
        c = m.get_ohlcv(tk, period="10y")["candles"]
    except MarketDataError:
        continue
    df = pd.DataFrame(c)
    if len(df) < WINDOW + 300:
        continue
    close = df["close"].values; dates = df["date"].values
    ret = np.concatenate([[np.nan], close[1:] / close[:-1] - 1])
    svol = pd.Series(ret).rolling(252).std().values
    n = len(close)
    for i in range(WINDOW + 1, n - 1):
        win = ret[i - WINDOW + 1:i + 1]; win = win[~np.isnan(win)]
        if len(win) < MIN_RETURNS:
            continue
        iv = empirical_interval(win, 0.90)
        if iv is None or svol[i] != svol[i]:
            continue
        raw = svc._regime_ratio(win); scale = max(1.0, raw)
        emove = (iv[1] - iv[0]) / 2 * scale          # forecast 90% half-width
        recs.append((dates[i], tk, emove, raw, svol[i], abs(ret[i + 1])))
    print(f"  loaded {tk}")

P = pd.DataFrame(recs, columns=["date", "tkr", "emove", "expand", "svol", "rmove"])
# cross-sectional percentile ranks -> opportunity score (production 50/50 blend)
P["pr_emove"] = P.groupby("date")["emove"].rank(pct=True)
P["pr_expand"] = P.groupby("date")["expand"].rank(pct=True)
P["opp"] = 0.5 * P["pr_emove"] + 0.5 * P["pr_expand"]
print(f"\nPanel: {len(P)} stock-days, {P['tkr'].nunique()} stocks, "
      f"{P['date'].nunique()} days\n")

MINS = 15


def daily_spear(col):
    v = []
    for d, g in P.groupby("date"):
        if len(g) >= MINS:
            r = spearmanr(g[col], g["rmove"]).correlation
            if r == r:
                v.append(r)
    return np.mean(v)


def stability(col):
    piv = P.pivot(index="date", columns="tkr", values=col)
    idx = piv.index; v = []
    for a, b in zip(idx[:-1], idx[1:]):
        x, y = piv.loc[a], piv.loc[b]; mk = x.notna() & y.notna()
        if mk.sum() >= MINS:
            r = spearmanr(x[mk], y[mk]).correlation
            if r == r:
                v.append(r)
    return np.mean(v)


def turnover(col, k=5):
    piv = P.pivot(index="date", columns="tkr", values=col)
    prev = None; ch = []; names = set()
    for d in piv.index:
        row = piv.loc[d].dropna()
        if len(row) < k:
            continue
        top = set(row.sort_values(ascending=False).head(k).index); names |= top
        if prev is not None:
            ch.append(k - len(top & prev))
        prev = top
    return np.mean(ch), len(names)


def quartile_spread(col):
    tops, bots = [], []
    for d, g in P.groupby("date"):
        if len(g) < 12:
            continue
        g = g.sort_values(col); k = max(1, len(g) // 4)
        bots.append(g.head(k)["rmove"].mean()); tops.append(g.tail(k)["rmove"].mean())
    return np.mean(tops), np.mean(bots)


print("=== RANKER COMPARISON ===")
print(f"  {'ranker':>16}{'stability':>11}{'turnover/day':>14}{'unique top5':>13}{'pred(Spearman)':>16}{'topQ/botQ move':>16}")
for lab, col in [("Static Vol", "svol"), ("Expected Move", "emove"), ("Opportunity", "opp")]:
    st = stability(col); tch, uniq = turnover(col); pr = daily_spear(col)
    tq, bq = quartile_spread(col)
    print(f"  {lab:>16}{st:>11.3f}{tch:>13.2f}{uniq:>13}{pr:>16.3f}{tq/bq:>14.2f}x")

print("\n=== EXPANSION: does it add information beyond Expected Move? ===")
sp_exp = daily_spear("expand")
sp_em = daily_spear("emove")
sp_opp = daily_spear("opp")
print(f"  Spearman(expansion alone, realised move)   = {sp_exp:+.3f}")
print(f"  Spearman(expected move,   realised move)   = {sp_em:+.3f}")
print(f"  Spearman(opportunity,     realised move)   = {sp_opp:+.3f}")
print(f"  INCREMENTAL (opportunity - expected move)  = {sp_opp - sp_em:+.3f}")
# correlation of the ranking with static vol (criterion 2: not just vol)
co = P.groupby("date").apply(lambda g: spearmanr(g["opp"], g["svol"]).correlation if len(g) >= MINS else np.nan).mean()
ce = P.groupby("date").apply(lambda g: spearmanr(g["emove"], g["svol"]).correlation if len(g) >= MINS else np.nan).mean()
print(f"\n  corr(Expected Move rank, Static Vol rank)  = {ce:+.3f}")
print(f"  corr(Opportunity  rank, Static Vol rank)   = {co:+.3f}   (lower = rotates away from raw vol)")
print("\nVERDICT:")
if sp_opp <= sp_em + 0.005 and sp_exp < 0.03:
    print("  Expansion adds NO meaningful predictive value -> SIMPLIFY to Expected Move only.")
elif sp_opp > sp_em + 0.005:
    print("  Expansion ADDS predictive value -> keep the Opportunity Score blend.")
else:
    print("  Expansion adds rotation but little/no prediction -> judgement call (lean simplify).")
print("\nDone.")
