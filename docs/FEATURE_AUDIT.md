# Feature Audit — Inventory of Embedded Assumptions

**Purpose:** document exactly what each analysis engine measures, how it scores, which
parts are evidence-based vs. hand-picked heuristics, and whether Phase 3 validation
supported or contradicted each assumption. **No logic was changed to produce this.**

**The single overarching Phase 3 finding:** the signal outputs (Trend, S/R, Volume,
Confluence) do **not** separate profitable stocks from unprofitable ones. Per-stock PF
ranged 0.37–2.44 with identical signal profiles (avg confluence ≈25, trend ≈2, S/R ≈77)
in both the best and worst stocks. Performance is **stock-selection-driven, not
signal-driven.** Every assumption below is judged against that backdrop.

A blanket truth first: **the raw *measurements* (linear regression, swing detection,
clustering, OBV, ATR) are standard and correctly implemented — they measure real things.
But every *weight, threshold, and scoring formula* that turns those measurements into
signals/scores was hand-picked by the author and never calibrated against outcomes.**

---

## 1. Trend Analysis

**Inputs**
- Last `lookback = 60` closing prices (linear regression).
- Swing highs/lows from `find_swing_points(window=5)` (structure).

**Calculation**
- `slope, intercept, R² = linear_regression(last 60 closes)`.
- `slope_pct = slope / mean_price × 100`.
- Structure: last 2 swing highs + last 2 swing lows → HH+HL = uptrend, LH+LL = downtrend, else sideways.
- Direction = combine slope direction (threshold ±0.05%/bar) with structure; they must agree (or one neutral), else sideways.
- Strength: `steepness = min(|slope_pct| / 0.3, 1.0)`; `strength = 0.6·R² + 0.4·steepness` (or `0.3·R²` if sideways).
- Label: ≥0.66 strong, ≥0.33 moderate, else weak.

**Core assumption:** *a cleaner (high R²) / steeper trend is stronger and more likely to continue.*

**Heuristic / never validated:** `lookback=60`, pivot `window=5`, slope threshold `±0.05%`, steepness normaliser `0.3%/bar`, strength weights `0.6/0.4` (and `0.3` for sideways), label cutoffs `0.66/0.33`.

**Evidence-based:** the regression and swing math (standard). Nothing about the *scoring* is.

**Phase 3 verdict: CONTRADICTED.** Per-stock robustness: strong-vs-weak trend split **7 stocks show / 7 contradict**, mean Δ ≈ 0. The aggregate "strong trend PF 1.10" was driven by outliers (HDFCBANK strong-trend PF 12.8). Trend strength does not robustly distinguish winners.

---

## 2. Support / Resistance

**Inputs**
- Swing highs (resistance) and swing lows (support) from `find_swing_points(window=5)`.

**Calculation (levels)**
- Cluster pivots of each type within `tolerance_pct = 1.5%`.
- Per level: `touches`, `touch_score = min(touches/4, 1)`, `recency = last_index/(n-1)`, `strength = 0.6·touch_score + 0.4·recency`.
- Keep strongest, enforce `min_gap = 1.5%`, cap `max_levels = 5`, require `min_touches = 2`.
- **Signal:** if price within **2%** of nearest support → bullish; within 2% of nearest resistance → bearish; else neutral. `confidence = that level's strength`.

**Calculation (key reaction zones)**
- Cluster all pivots together (`tolerance 2%`); require ≥1 high AND ≥1 low AND `≥3 touches`.
- `role_reversals` = chronological count of resistance↔support flips.
- `strength = 0.35·min(touches/6,1) + 0.40·min(role_reversals/4,1) + 0.25·recency`; rank by reversals→touches; `top = 2`.
- `strongest_level` = densest sub-cluster within `0.6%`.

**Core assumption:** *levels touched more often / more recently are stronger, and price bounces when near a strong level (the basis for "near support → bullish").*

**Heuristic / never validated:** `window=5`, clustering tolerances `1.5%`/`2%`, `touch_score` cap at 4 (zones at 6), strength weights `0.6/0.4` and `0.35/0.40/0.25`, the **2% "near a level" proximity** that triggers the signal, `min_touches 2/3`, `min_gap 1.5%`, `max_levels 5`, `role_reversals/4`, `strongest_level 0.6%`.

**Evidence-based:** clustering/counting is mechanically sound.

**Phase 3 verdict: CONTRADICTED.** S/R-strength split (≥70 vs <70): **6 show / 8 contradict**, median Δ **−0.13** (strong levels slightly *underperform* per stock). The "near support → bullish" rule produces the counter-trend LONGs that backtested near breakeven. Top vs bottom stocks had near-identical avg S/R strength (76.9 vs 75.1).

---

## 3. Volume Analysis

**Inputs**
- `volumes`, `closes`, `opens`.

**Calculation**
- `relative_volume = latest_volume / 20-day average (prior 20)`.
- `spike = relative_volume ≥ 2.0`.
- `volume_trend`: recent 10-day avg vs prior 10-day avg (rising if > ×1.1, falling if < ×0.9).
- `OBV` (add volume on up-closes, subtract on down-closes); `obv_trend` = OBV now vs 20 bars ago.
- `breakout = spike AND |1-day % change| ≥ 1%`.
- **Signal:** spike+up-day = bullish; spike+down-day = bearish; else if OBV-rising AND volume-rising = bullish; OBV-falling AND volume-rising = bearish; else neutral.
- `confidence = min(relative_volume / 3, 1)`.

**Core assumption:** *high volume confirms the move — high/rising volume = stronger, more bullish conviction.*

**Heuristic / never validated:** `avg_period 20`, `spike_mult 2.0`, trend windows `10/10` with `±10%`, OBV lookback `20`, breakout `1%`, **confidence divisor `3`**, and the entire signal mapping.

**Evidence-based:** OBV and the ratios are standard arithmetic.

**Phase 3 verdict: CONTRADICTED — and INVERTED.** This is the key finding: **low relative volume (<0.7) was the best band (PF 1.17); high volume (1.5–2.0 PF 0.68, 2.0+ PF 0.59) lost.** The core "high volume = bullish confirmation" assumption is **backwards.** The low>high tendency was also the *only* mildly robust cross-stock effect (9/14 stocks), but still weak.

---

## 4. Confluence Score

**Inputs**
- `signal` + `confidence` from Trend (weight **40**), Support/Resistance (**30**), Volume (**30**).

**Calculation**
- Per factor: `contribution = sign × confidence × weight` (sign = +1 bull, −1 bear, 0 neutral).
- `net = bull_points − bear_points`; `score = min(|net|, 100)`.
- Direction: bullish if net > **+5**, bearish if < **−5**, else neutral.
- Classification: 0–30 Weak · 31–60 Moderate · 61–80 Strong · 81–100 Very Strong.

**Core assumption:** *when independent factors agree, the setup is stronger; a higher score = a better, more tradeable setup.*

**Heuristic / never validated:** weights `40/30/30`, direction threshold `±5`, band cutoffs `30/60/80`. It also **inherits every unvalidated assumption of its three inputs** — including the *inverted* volume signal (so volume contributes the wrong sign on high-volume days).

**Evidence-based:** the weighted-sum arithmetic is correct; nothing about the weights or the "agreement = edge" premise is validated.

**Phase 3 verdict: CONTRADICTED.** Confluence score is non-monotonic (band 0–20 PF 1.02, 21–40 PF 0.95, 41–60 PF 1.25). High-confluence trades are too rare per stock to validate (n=3–11). Top vs bottom stocks differ by only ~4 score points (26.7 vs 22.8, both "Weak"). The score does not separate profitable stocks.

---

## Inventory summary

| Engine | Real measurement (sound) | Hand-picked & unvalidated | Phase 3 verdict |
|--------|--------------------------|---------------------------|-----------------|
| Trend | regression slope, R², swing structure | lookback 60, window 5, ±0.05% dir threshold, 0.3% steepness, 0.6/0.4 & 0.3 weights, 0.66/0.33 labels | **Contradicted** (7/7, mean ≈0) |
| S/R | pivot clustering, touch counts, role flips | tolerances 1.5/2%, touch cap 4/6, 0.6/0.4 & 0.35/0.40/0.25 weights, 2% proximity, min_touches, gaps, strongest 0.6% | **Contradicted** (6/8, median −0.13) |
| Volume | relative volume, OBV, trend ratios | avg 20, spike 2.0, 10/10 ±10%, OBV 20, breakout 1%, **confidence ÷3** | **Contradicted & inverted** (low > high) |
| Confluence | weighted-sum arithmetic | weights 40/30/30, ±5 direction, 30/60/80 bands + all inherited input assumptions | **Contradicted** (non-monotonic) |

## Bottom line

- **What the platform actually measures:** real, standard technical quantities (trend slope, support/resistance touch zones, relative volume, OBV) — computed correctly.
- **What it assumes (and that failed validation):** that *strong trend, strong levels, high volume, and high confluence predict better outcomes.* Phase 3 contradicted all four; one (volume) is outright backwards.
- **Not a single weight, threshold, or scoring formula in the platform has ever been validated against trade outcomes.** They are all reasonable-sounding defaults chosen by the author.
- **The only empirically-supported (mild) signal so far is the inversion of the volume assumption** — low relative volume tended to do better than high, on a majority of stocks.

This inventory is the prerequisite for any future change: each item above is a hypothesis to be tested, not a fact to be built upon.
