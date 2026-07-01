"""
Volatility indicator — PURE function, no Django, no I/O.
"""


def average_true_range(highs, lows, closes, period=14):
    """
    ATR (Average True Range) — a measure of how much a stock typically moves
    per bar. True Range for a bar is the largest of:
        high-low, |high-prev_close|, |low-prev_close|
    ATR is the average of those over `period` bars. Used to size stop-loss
    buffers so they scale with the stock's own volatility.
    """
    if len(closes) < period + 1:
        return None
    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    return sum(trs[-period:]) / period
