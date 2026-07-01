"""
Trend math — PURE functions, no Django, no I/O.
"""


def linear_regression(xs, ys):
    """
    Fit a straight line y = slope*x + intercept by least squares.
    Returns (slope, intercept, r_squared).
      - slope     : how fast price changes per bar
      - r_squared : 0..1, how well the points fit a straight line
                    (1 = perfectly clean trend, 0 = no linear relationship)
    """
    n = len(xs)
    if n < 2:
        return 0.0, (ys[0] if ys else 0.0), 0.0

    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    if sxx == 0:
        return 0.0, mean_y, 0.0

    sxy = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x

    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    ss_res = sum((ys[i] - (slope * xs[i] + intercept)) ** 2 for i in range(n))
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

    return slope, intercept, r_squared
