"""
Range-forecast calibration validation (ticker-level + year-by-year).

Reuses the PRODUCTION method (RangeForecastService._regime_ratio + the empirical
interval indicator) so the reported coverage matches what the live endpoint does.
Leakage-safe: each day's interval uses only returns strictly before it.
"""
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "stock_prediction_main.settings")
django.setup()

from analysis.services.range_forecast import RangeForecastService, LEVELS, WINDOW, MIN_RETURNS
from analysis.indicators.distribution import empirical_interval
from analysis.services.market_data import MarketDataError

svc = RangeForecastService()
TICKERS = ["RELIANCE.NS", "INFY.NS", "HDFCBANK.NS", "TATASTEEL.NS", "^NSEI", "TMPV.NS", "TMCV.NS"]
LONG = {"RELIANCE.NS", "INFY.NS", "HDFCBANK.NS", "TATASTEEL.NS", "^NSEI"}  # for the yearly pool


def coverage(ticker, period="10y"):
    candles = svc.market.get_ohlcv(ticker, period=period)["candles"]
    closes = [c["close"] for c in candles]
    dates = [c["date"] for c in candles]
    returns = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))]
    rdates = dates[1:]  # aligned to returns[j] -> rdates[j]
    overall = {L: [0, 0] for L in LEVELS}
    yearly = {}
    for i in range(MIN_RETURNS, len(returns)):
        win = returns[max(0, i - WINDOW):i]
        if len(win) < MIN_RETURNS:
            continue
        ratio = svc._regime_ratio(win)
        r = returns[i]
        yr = rdates[i][:4]
        for L in LEVELS:
            iv = empirical_interval(win, L)
            if iv is None:
                continue
            lo, hi = iv[0] * ratio, iv[1] * ratio
            inside = int(lo <= r <= hi)
            overall[L][0] += inside; overall[L][1] += 1
            yearly.setdefault(yr, {LL: [0, 0] for LL in LEVELS})
            yearly[yr][L][0] += inside; yearly[yr][L][1] += 1
    return overall, yearly, len(returns)


pct = lambda hc: (hc[0] / hc[1] * 100) if hc[1] else float("nan")

print("=== TASK 3: TICKER-LEVEL CALIBRATION (10y, point-in-time) ===")
print(f"  {'ticker':13}{'history':>9}{'50%':>9}{'70%':>9}{'90%':>9}{'samples':>9}")
pool = {}
for t in TICKERS:
    try:
        ov, yr, hist = coverage(t)
    except MarketDataError as e:
        print(f"  {t:13}  ERROR: {e}")
        continue
    n = ov[0.90][1]
    print(f"  {t:13}{hist:>9}{pct(ov[0.50]):>8.1f}%{pct(ov[0.70]):>8.1f}%{pct(ov[0.90]):>8.1f}%{n:>9}")
    if t in LONG:
        for y, lv in yr.items():
            pool.setdefault(y, {L: [0, 0] for L in LEVELS})
            for L in LEVELS:
                pool[y][L][0] += lv[L][0]; pool[y][L][1] += lv[L][1]

print("\n  Nominal targets: 50 / 70 / 90.  Within a few points = well-calibrated.\n")

print("=== TASK 4: YEAR-BY-YEAR CALIBRATION (pooled across the 5 long-history names) ===")
print("  (does overall calibration hide instability in a specific market regime?)")
print(f"  {'year':>6}{'50%':>9}{'70%':>9}{'90%':>9}{'n':>9}")
for y in sorted(pool):
    lv = pool[y]
    n = lv[0.90][1]
    if n < 100:
        continue
    print(f"  {y:>6}{pct(lv[0.50]):>8.1f}%{pct(lv[0.70]):>8.1f}%{pct(lv[0.90]):>8.1f}%{n:>9}")
print("\nDone.")
