"""
A/B: CURRENT (widen-only empirical) vs GARCH-FHS for the next-day range.

GARCH-FHS (Filtered Historical Simulation) = the proper statistical upgrade:
  - GARCH(1,1)-t models the conditional volatility (clusters + fat tails)
  - empirical quantiles of the STANDARDISED residuals give the (fat-tailed) shape
  - next-day interval = sigma_{t+1} * residual_quantile

Leakage-safe: GARCH params refit on an expanding past window only, variance
filtered forward day-by-day, residual quantiles from past residuals only.
Production code is NOT modified.
"""
import os
import warnings
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "stock_prediction_main.settings")
django.setup()
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from arch import arch_model
from analysis.services.range_forecast import RangeForecastService, LEVELS, WINDOW, MIN_RETURNS
from analysis.indicators.distribution import empirical_interval
from analysis.services.market_data import MarketDataService, MarketDataError

svc = RangeForecastService()
m = MarketDataService()
STOCKS = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS",
          "WIPRO.NS", "MARUTI.NS", "LT.NS", "AXISBANK.NS", "ITC.NS", "HINDUNILVR.NS",
          "TITAN.NS", "SUNPHARMA.NS", "TATASTEEL.NS", "^NSEI"]
REFIT = 63          # refit GARCH every ~quarter; filter variance forward between fits
START = 504         # need ~2y to fit the first GARCH

cur = {p: [0, 0] for p in LEVELS}; cur_w = {p: [] for p in LEVELS}
gar = {p: [0, 0] for p in LEVELS}; gar_w = {p: [] for p in LEVELS}
yr_cur = {}; yr_gar = {}            # 90% coverage by year
covid_cur = [0, 0]; covid_gar = [0, 0]


def acc(store, w, p, lo, hi, r):
    store[p][0] += int(lo <= r <= hi); store[p][1] += 1
    w[p].append((hi - lo) * 100)


for t in STOCKS:
    try:
        c = m.get_ohlcv(t, period="10y")["candles"]
    except MarketDataError:
        continue
    df = pd.DataFrame(c)
    if len(df) < START + 200:
        continue
    close = df["close"].values
    dates = df["date"].values
    ret = np.diff(close) / close[:-1]          # ret[k] = return on day k+1
    rdate = dates[1:]
    rp = ret * 100                              # percent, for GARCH stability
    n = len(ret)

    omega = alpha = beta = None
    zq = {}
    sig2 = None                                 # conditional variance (percent^2) for "today"
    for i in range(START, n):
        # refit GARCH on returns strictly before day i; rebuild residual quantiles
        if (i - START) % REFIT == 0 or omega is None:
            try:
                res = arch_model(rp[:i], mean="Zero", vol="GARCH", p=1, q=1, dist="t").fit(disp="off")
                omega = res.params["omega"]; alpha = res.params["alpha[1]"]; beta = res.params["beta[1]"]
                cv = res.conditional_volatility
                z = rp[:i] / cv
                zq = {p: (np.quantile(z, (1 - p) / 2), np.quantile(z, 1 - (1 - p) / 2)) for p in LEVELS}
                sig2 = cv[-1] ** 2
            except Exception:
                pass
        if omega is None or sig2 is None:
            continue
        # 1-step variance forecast for day i (info through i-1): sigma2_i = w + a*r_{i-1}^2 + b*sigma2_{i-1}
        sig2 = omega + alpha * rp[i - 1] ** 2 + beta * sig2
        sig = np.sqrt(sig2)
        r = ret[i]; yr = rdate[i][:4]
        is_covid = "2020-02-20" <= rdate[i] <= "2020-04-30"

        # CURRENT: widen-only empirical on trailing window
        win = ret[max(0, i - WINDOW):i]
        if len(win) >= MIN_RETURNS:
            scale = max(1.0, svc._regime_ratio(win))
            for p in LEVELS:
                iv = empirical_interval(win, p)
                if iv:
                    lo, hi = iv[0] * scale, iv[1] * scale
                    acc(cur, cur_w, p, lo, hi, r)
                    if p == 0.90:
                        yr_cur.setdefault(yr, [0, 0]); yr_cur[yr][0] += int(lo <= r <= hi); yr_cur[yr][1] += 1
                        if is_covid: covid_cur[0] += int(lo <= r <= hi); covid_cur[1] += 1

        # GARCH-FHS: residual quantile * sigma_forecast (convert percent -> fraction)
        for p in LEVELS:
            lo, hi = zq[p][0] * sig / 100, zq[p][1] * sig / 100
            acc(gar, gar_w, p, lo, hi, r)
            if p == 0.90:
                yr_gar.setdefault(yr, [0, 0]); yr_gar[yr][0] += int(lo <= r <= hi); yr_gar[yr][1] += 1
                if is_covid: covid_gar[0] += int(lo <= r <= hi); covid_gar[1] += 1
    print(f"  fitted {t}")

cov = lambda s, p: s[p][0] / s[p][1] * 100 if s[p][1] else float("nan")
wid = lambda w, p: float(np.mean(w[p])) if w[p] else float("nan")
print(f"\nTest stock-days (90% bucket): current {cur[0.90][1]}, garch {gar[0.90][1]}\n")
print("=== OVERALL CALIBRATION + WIDTH ===")
print(f"  {'level':>6} | {'CURRENT cov':>12}{'width':>8} | {'GARCH cov':>11}{'width':>8}")
for p in LEVELS:
    print(f"  {int(p*100):>5}% | {cov(cur,p):>11.1f}%{wid(cur_w,p):>7.2f}% | {cov(gar,p):>10.1f}%{wid(gar_w,p):>7.2f}%")

g = lambda s: np.mean([abs(cov(s, p) - p * 100) for p in LEVELS])
print(f"\n  mean |coverage - nominal|:  CURRENT {g(cur):.2f}pp   GARCH {g(gar):.2f}pp")
aw = np.mean([(wid(gar_w, p) - wid(cur_w, p)) / wid(cur_w, p) * 100 for p in LEVELS])
print(f"  avg width change (GARCH vs current): {aw:+.1f}%")

print("\n=== 90% COVERAGE BY YEAR ===")
print(f"  {'year':>6}{'n':>7} | {'CURRENT':>9} | {'GARCH':>9}")
for y in sorted(yr_cur):
    if yr_cur[y][1] < 150:
        continue
    cc = yr_cur[y][0] / yr_cur[y][1] * 100
    gg = yr_gar[y][0] / yr_gar[y][1] * 100 if yr_gar.get(y, [0, 0])[1] else float("nan")
    print(f"  {y:>6}{yr_cur[y][1]:>7} | {cc:>8.1f}% | {gg:>8.1f}%{'  <-- COVID' if y=='2020' else ''}")
cc = covid_cur[0] / covid_cur[1] * 100 if covid_cur[1] else float("nan")
gg = covid_gar[0] / covid_gar[1] * 100 if covid_gar[1] else float("nan")
print(f"\n  COVID crash window (n={covid_cur[1]}): CURRENT {cc:.1f}%   GARCH {gg:.1f}%")
print("\nDone.")
