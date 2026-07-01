"""
GARCH-FHS SHADOW robustness review (production stays = widen-only empirical).

Reports, for CURRENT vs GARCH-FHS:
  1. Year-by-year calibration: 50/70/90 coverage, width, sample counts
  2. Confidence-bucket calibration: High/Medium/Low coverage, width, counts
  3. Operational metrics: avg + p95 fit runtime, convergence-failure rate, fallback freq
  4. Stability summary: years/buckets where GARCH is WORSE, quantified

Leakage-safe: GARCH refit on expanding past window only, variance filtered forward,
residual quantiles from past residuals only. Production code NOT modified.
"""
import os
import time
import warnings
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "stock_prediction_main.settings")
django.setup()
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from arch import arch_model
from analysis.services.range_forecast import RangeForecastService, MIN_RETURNS, WINDOW
from analysis.indicators.distribution import empirical_interval
from analysis.services.market_data import MarketDataService, MarketDataError

svc = RangeForecastService()
m = MarketDataService()
STOCKS = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS",
          "WIPRO.NS", "MARUTI.NS", "LT.NS", "AXISBANK.NS", "ITC.NS", "HINDUNILVR.NS",
          "TITAN.NS", "SUNPHARMA.NS", "TATASTEEL.NS", "^NSEI"]
LV = [0.50, 0.70, 0.90]
REFIT = 63
START = 504

# stats[method][key][level] = [hits, n, width_sum]; key = year / bucket / "ALL"
def newrec():
    return {lv: [0, 0, 0.0] for lv in LV}
stats = {"cur": {}, "gar": {}}
def rec(method, key, lv, hit, width):
    d = stats[method].setdefault(key, newrec())
    d[lv][0] += hit; d[lv][1] += 1; d[lv][2] += width

fit_times, fit_attempts, fit_failures, fallback_days, total_days = [], 0, 0, 0, 0


def bucket_of(raw):
    return "High" if raw <= 0.90 else "Medium" if raw <= 1.15 else "Low"


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
    ret = np.diff(close) / close[:-1]
    rdate = dates[1:]
    rp = ret * 100
    n = len(ret)

    omega = alpha = beta = None
    zq, sig2 = {}, None
    for i in range(START, n):
        if (i - START) % REFIT == 0 or omega is None:
            fit_attempts += 1
            try:
                t0 = time.perf_counter()
                res = arch_model(rp[:i], mean="Zero", vol="GARCH", p=1, q=1, dist="t").fit(disp="off")
                dt = time.perf_counter() - t0
                o, a, b = res.params["omega"], res.params["alpha[1]"], res.params["beta[1]"]
                if not all(np.isfinite([o, a, b])) or (a + b) >= 1.0:
                    raise ValueError("non-stationary / non-finite params")
                omega, alpha, beta = o, a, b
                cv = res.conditional_volatility
                z = rp[:i] / cv
                zq = {lv: (np.quantile(z, (1 - lv) / 2), np.quantile(z, 1 - (1 - lv) / 2)) for lv in LV}
                sig2 = cv[-1] ** 2
                fit_times.append(dt)
            except Exception:
                fit_failures += 1   # keep prior params if we have them; else this block falls back

        r = ret[i]; yr = rdate[i][:4]
        win = ret[max(0, i - WINDOW):i]
        if len(win) < MIN_RETURNS:
            continue
        total_days += 1
        raw = svc._regime_ratio(win); scale = max(1.0, raw); buck = bucket_of(raw)

        # CURRENT (production) — always available
        for lv in LV:
            iv = empirical_interval(win, lv)
            if iv:
                lo, hi = iv[0] * scale, iv[1] * scale
                w = (hi - lo) * 100
                rec("cur", yr, lv, int(lo <= r <= hi), w)
                rec("cur", buck, lv, int(lo <= r <= hi), w)
                rec("cur", "ALL", lv, int(lo <= r <= hi), w)

        # GARCH-FHS (shadow) — needs valid params; else this day is a FALLBACK
        if omega is None or sig2 is None:
            fallback_days += 1
            continue
        sig2 = omega + alpha * rp[i - 1] ** 2 + beta * sig2
        sig = np.sqrt(sig2)
        for lv in LV:
            lo, hi = zq[lv][0] * sig / 100, zq[lv][1] * sig / 100
            w = (hi - lo) * 100
            rec("gar", yr, lv, int(lo <= r <= hi), w)
            rec("gar", buck, lv, int(lo <= r <= hi), w)
            rec("gar", "ALL", lv, int(lo <= r <= hi), w)
    print(f"  done {t}")

cov = lambda d, lv: d[lv][0] / d[lv][1] * 100 if d[lv][1] else float("nan")
wid = lambda d, lv: d[lv][2] / d[lv][1] if d[lv][1] else float("nan")
gap = lambda d: np.mean([abs(cov(d, lv) - lv * 100) for lv in LV])


def table(keys, title):
    print(f"\n=== {title} ===")
    print(f"  {'key':>8} | {'n':>6} | "
          f"{'C50':>6}{'C70':>6}{'C90':>6}{'Cw90':>7} | {'G50':>6}{'G70':>6}{'G90':>6}{'Gw90':>7} | {'win':>5}")
    for k in keys:
        cd = stats["cur"].get(k); gd = stats["gar"].get(k)
        if not cd or cd[0.90][1] < 80:
            continue
        n = cd[0.90][1]
        cline = f"{cov(cd,.5):>6.1f}{cov(cd,.7):>6.1f}{cov(cd,.9):>6.1f}{wid(cd,.9):>6.2f}%"
        if gd and gd[0.90][1] > 50:
            gline = f"{cov(gd,.5):>6.1f}{cov(gd,.7):>6.1f}{cov(gd,.9):>6.1f}{wid(gd,.9):>6.2f}%"
            win = "GARCH" if gap(gd) < gap(cd) else "cur"
        else:
            gline, win = f"{'--':>6}{'--':>6}{'--':>6}{'--':>7}", "n/a"
        print(f"  {k:>8} | {n:>6} | {cline} | {gline} | {win:>5}")


years = sorted(y for y in stats["cur"] if y.isdigit())
table(years, "1. YEAR-BY-YEAR CALIBRATION (C=current, G=GARCH; Cxx/Gxx=coverage%, w90=90% width)")
table(["High", "Medium", "Low"], "2. CONFIDENCE-BUCKET CALIBRATION")

print("\n=== 3. OPERATIONAL METRICS (GARCH fit) ===")
print(f"  fit attempts                 : {fit_attempts}")
print(f"  convergence/fit failures     : {fit_failures}  ({fit_failures/max(fit_attempts,1)*100:.2f}%)")
print(f"  fallback days (GARCH unavail): {fallback_days}  ({fallback_days/max(total_days,1)*100:.2f}% of {total_days} days)")
if fit_times:
    print(f"  avg fit runtime              : {np.mean(fit_times)*1000:.0f} ms")
    print(f"  p95 fit runtime              : {np.percentile(fit_times,95)*1000:.0f} ms")
    print(f"  max fit runtime              : {np.max(fit_times)*1000:.0f} ms")

print("\n=== 4. STABILITY SUMMARY (where GARCH is WORSE than current) ===")
print(f"  Overall mean|gap|: current {gap(stats['cur']['ALL']):.2f}pp | GARCH {gap(stats['gar']['ALL']):.2f}pp")
worse = []
for k in years + ["High", "Medium", "Low"]:
    cd, gd = stats["cur"].get(k), stats["gar"].get(k)
    if cd and gd and gd[0.90][1] > 50:
        gc, gg = gap(cd), gap(gd)
        c90, g90 = cov(cd, .9), cov(gd, .9)
        if gg > gc + 0.3:   # GARCH meaningfully worse on mean gap
            worse.append((k, gc, gg, c90, g90))
if worse:
    print("  GARCH underperforms current in:")
    for k, gc, gg, c90, g90 in worse:
        print(f"     {k:>8}: mean|gap| {gg:.2f}pp vs {gc:.2f}pp (worse by {gg-gc:+.2f}pp); 90% cov {g90:.1f}% vs {c90:.1f}%")
else:
    print("  GARCH is >= current on mean|gap| in every year and bucket.")
print("\nDone.")
