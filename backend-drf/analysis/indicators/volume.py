"""
Volume indicators — PURE functions, no Django, no I/O.
"""


def average(values, period):
    """Simple average of the last `period` values (None if not enough data)."""
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def on_balance_volume(closes, volumes):
    """
    On-Balance Volume (OBV): a running total that ADDS the day's volume when
    price closed up and SUBTRACTS it when price closed down. A rising OBV means
    volume is flowing into up-days (accumulation / bullish); a falling OBV means
    volume is flowing into down-days (distribution / bearish).
    """
    obv = [0]
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            obv.append(obv[-1] + volumes[i])
        elif closes[i] < closes[i - 1]:
            obv.append(obv[-1] - volumes[i])
        else:
            obv.append(obv[-1])
    return obv
