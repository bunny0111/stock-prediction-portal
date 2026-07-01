"""
Pivot (swing point) detection — a PURE function, no Django, no I/O.

A "swing high" is a candle whose high is the highest within a window of bars
on either side of it (a local peak where price turned down). A "swing low" is
the opposite (a local trough where price turned up). These turning points are
the raw material for support/resistance: they are the exact spots where price
actually reversed.
"""


def find_swing_points(highs, lows, window=5):
    """
    highs, lows : lists of floats (per-candle high and low prices)
    window      : how many bars to compare on EACH side (larger = fewer,
                  more significant pivots)

    Returns (swing_highs, swing_lows), each a list of (index, price) tuples.
    """
    swing_highs = []
    swing_lows = []
    n = len(highs)

    # We can't evaluate the first/last `window` bars (no full neighbourhood).
    for i in range(window, n - window):
        local_highs = highs[i - window: i + window + 1]
        local_lows = lows[i - window: i + window + 1]

        # Because bar i is included in the slice, ">= max" means "is the max".
        if highs[i] >= max(local_highs):
            swing_highs.append((i, highs[i]))
        if lows[i] <= min(local_lows):
            swing_lows.append((i, lows[i]))

    return swing_highs, swing_lows
