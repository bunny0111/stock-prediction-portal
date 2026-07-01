"""
Return-distribution indicators — PURE functions (no Django, no I/O).

Used by the range-forecast engine to turn a window of past daily returns into
calibrated next-day intervals. Two building blocks:

  - empirical_interval : the VALIDATED primary method. It reads the actual
    distribution of past returns, so it is naturally fat-tail aware (a Gaussian
    over-covers the centre and under-covers the tails — the empirical interval
    does neither).
  - ewma_volatility    : RiskMetrics EWMA conditional volatility, a regime-
    sensitive scalar we use to widen/narrow the empirical interval for the
    CURRENT regime (volatility clusters, so recent vol predicts near-term vol).
"""

import math


def _clean(returns):
    return [float(r) for r in returns if r is not None and not math.isnan(float(r))]


def percentile(sorted_vals, p):
    """Linear-interpolated percentile. `p` in [0, 1]. `sorted_vals` must be sorted."""
    n = len(sorted_vals)
    if n == 0:
        return None
    if n == 1:
        return sorted_vals[0]
    idx = p * (n - 1)
    lo = math.floor(idx)
    hi = math.ceil(idx)
    if lo == hi:
        return sorted_vals[int(idx)]
    frac = idx - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def empirical_interval(returns, level):
    """
    Two-sided empirical return interval at `level` coverage (e.g. 0.90 -> the
    5th and 95th percentiles of past returns). Returns (q_low, q_high) as return
    fractions, or None if there are too few points to trust the distribution.
    """
    rs = sorted(_clean(returns))
    if len(rs) < 20:
        return None
    a = (1 - level) / 2.0
    return percentile(rs, a), percentile(rs, 1 - a)


def std(returns):
    """Sample standard deviation of returns (the flat-window volatility)."""
    rs = _clean(returns)
    if len(rs) < 2:
        return None
    m = sum(rs) / len(rs)
    return math.sqrt(sum((r - m) ** 2 for r in rs) / (len(rs) - 1))


def ewma_volatility(returns, lam=0.94):
    """
    RiskMetrics EWMA conditional volatility:  var_t = λ·var_{t-1} + (1-λ)·r².
    Reacts faster to the CURRENT regime than a flat-window std, which is exactly
    what we want for a *next-day* range when volatility is expanding or calming.
    """
    rs = _clean(returns)
    if len(rs) < 5:
        return None
    seed = rs[: min(20, len(rs))]
    var = sum(r * r for r in seed) / len(seed)
    for r in rs:
        var = lam * var + (1 - lam) * r * r
    return math.sqrt(var)
