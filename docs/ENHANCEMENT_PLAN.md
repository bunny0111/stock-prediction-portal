# Stock Prediction Portal → Practical Financial Analysis Platform

**Type:** Enhancement of the existing app (NOT a rewrite, NOT a new project).
**Goal:** Evolve from "predict next-day price" to "detect and rank objective trading setups, then prove they work via backtesting." Subjective inputs (sentiment, chart patterns) are added **last**, only after the objective core is validated.

## Hard constraints (locked for this stage)

**Do NOT:** create a new project · redesign architecture from scratch · replace JWT auth · change the database · migrate SQLite → PostgreSQL · make any LLM provider mandatory · make pattern recognition an early-stage feature.

**Do:** reuse the existing React + Django architecture · keep JWT · keep SQLite · build new functionality as extensions · build objective/measurable engines first · ensure every module can be validated through backtesting.

---

## Architectural Philosophy

> Build and validate **objective** signals first. Prove that **Trend + Support/Resistance + Volume** provides useful, backtested information *before* introducing subjective components (sentiment, patterns). Every module must be designed so its contribution can be measured by the Validation Engine.

**Canonical priority order:**

1. Market Data → 2. Support & Resistance → 3. Volume Analysis → 4. Trend Analysis → 5. Confluence Scoring → 6. Opportunity Analysis → 7. Backtesting / Validation → 8. News & Sentiment → 9. Pattern Recognition

---

## 1. Architecture Changes (within existing project)

The only structural change is introducing a **service layer** inside the current Django project — no rewrite, no new project.

```
View (thin)  →  Service (business logic)  →  Indicator/Util (pure functions)
```

- **Views** only validate the request, call a service, serialize the result.
- **Services** are plain Python classes, framework-agnostic, unit-testable.
- **Indicators** (pivots, ATR, OBV, rel-volume) are pure functions over arrays — no Django, no I/O.

Add a new `analysis` Django app to house the engines. **The existing `api` (LSTM) and `accounts` (JWT auth) apps stay exactly as they are.** SQLite stays. The LSTM endpoint remains available for comparison, clearly labeled as the educational model — not part of the decision engine.

**Orchestration rule:** `ConfluenceScoringService` does not re-fetch data. `MarketDataService` fetches once; its output is passed down to every engine. Fetch once, pass down.

**No mandatory async/queue at this stage.** Keep requests synchronous for now. If latency becomes a problem later (mainly Phase 4 sentiment), a background-job layer can be added without changing the API contracts. Not part of this roadmap.

---

## 2. Database (SQLite — unchanged)

**SQLite stays for the entire scope of this roadmap.** No PostgreSQL migration. Keep models lightweight and lean on `JSONField` so engine outputs can evolve without constant migrations.

Models are added incrementally, only when a phase needs them:

| Model | Added in | Purpose |
|-------|----------|---------|
| `MarketDataCache` | Phase 1 | Cache yfinance OHLCV payloads: `ticker, interval, period, payload(JSON), fetched_at` |
| `AnalysisSnapshot` | Phase 2 | Saved analysis result: `ticker, result(JSON), confluence_score, created_at` |
| `BacktestResult` | Phase 3 | Validation outcomes: `config(JSON), ticker, win_rate, profit_factor, avg_rr, max_drawdown, sample_size, created_at` |
| `NewsItem` | Phase 4 | Cached yfinance news: `ticker, title, publisher, url, published_at` (optional `sentiment, score` only if rule-based scoring is added later) |
| `PatternDetection` | Phase 5 | Detected-pattern log: `ticker, pattern_name, confidence, status, detected_at` |

Caching uses Django's cache framework backed by the database/local memory — no Redis required at this stage.

---

## 3. Backend Implementation Plan

Each engine is a service class with a single responsibility and a **uniform return contract** so confluence and the frontend stay simple:

```python
{
  "signal": "bullish" | "bearish" | "neutral",
  "confidence": 0.0–1.0,
  "details": { ... },     # engine-specific numbers
  "viz": { ... }          # coordinates/levels for the chart to draw
}
```

Services by phase:

- **MarketDataService** — fetch + cache OHLCV, info, earnings, dividends, splits, news; retries, graceful handling of bad/empty tickers. Single source of data for all engines.
- **SupportResistanceService** — cluster pivot highs/lows into zones, score by touches + recency, add round-number levels, compute distance from current price.
- **VolumeAnalysisService** — relative volume vs N-day average, volume spikes, breakout confirmation, OBV/volume trend; classify bullish/bearish/neutral.
- **TrendAnalysisService** — swing pivots, trendlines via linear regression on pivots, trend direction + strength, trendline-break detection.
- **ConfluenceScoringService** — combine Trend + S/R + Volume using a **configurable weighting config**; return total score, classification, and a per-factor breakdown ("why").
- **OpportunityService** — from confluence + S/R + ATR, derive entry zone, stop-loss, targets, risk/reward.
- **ValidationService** — backtest a confluence config over history: win rate, profit factor, avg R/R, max drawdown, sample size.
- **NewsAnalysisService** (Phase 4) — fetch/normalize/dedupe yfinance news only; **no sentiment, no AI** (see §11).
- **RuleBasedSentimentService** (Phase 4, optional/deferred) — local keyword scorer, fully offline; kept separate from news collection (see §11).
- **PatternRecognitionService** (Phase 5) — orchestrates individual detectors; every pattern returns confidence and is backtestable.

Design rules: services never import views; indicators are pure functions (prefer `pandas-ta` over hand-rolling); every engine degrades gracefully (one failure → partial result with a `warnings` array, never a 500).

---

## 4. Frontend Implementation Plan

Extend the existing React dashboard — keep `axiosInstance` + JWT interceptor as the single API client.

- **Charts:** move from static matplotlib PNGs to JSON + an interactive library (**TradingView Lightweight Charts** or Plotly) so trendlines, S/R, and (later) patterns render as overlays. This can be introduced gradually.
- **Dashboard tabs:** Overview (chart + confluence badge) · Technical (trend / S-R / volume) · Opportunity (entry/stop/target + R/R) · (later) Backtest results · News (yfinance feed, display-only) · Patterns.
- **Cleanup:** migrate `Login.jsx`/`Register.jsx` from raw `axios` + hardcoded URLs to `axiosInstance`.
- Optionally adopt React Query for caching/loading states as the number of endpoints grows.
- Every opportunity view carries a clear **"Educational analysis, not financial advice"** disclaimer.

---

## 5. API Design

Base `/api/v1/`, all JWT-authenticated. Accept `?interval=1d&period=2y` where relevant. Standard envelope: `{ status, data, meta: { ticker, generated_at, cache_hit } }`.

| Method | Endpoint | Phase | Returns |
|--------|----------|-------|---------|
| GET | `/analysis/{ticker}/` | 2 | Orchestrated: market + trend + S/R + volume + confluence + opportunity |
| GET | `/market-data/{ticker}/` | 1 | OHLCV + corporate actions + earnings |
| GET | `/support-resistance/{ticker}/` | 1 | S/R zones + distances |
| GET | `/volume/{ticker}/` | 1 | Volume signals |
| GET | `/trend/{ticker}/` | 1 | Trend direction/strength + trendlines |
| GET | `/opportunity/{ticker}/` | 2 | Entry/stop/targets/RR |
| POST | `/backtest/` | 3 | Run validation for a config → metrics |
| GET | `/news/{ticker}/` | 4 | yfinance news items (display only; optional rule-based sentiment field later) |
| GET | `/patterns/{ticker}/` | 5 | Detected patterns |

Granular endpoints power individual tabs / lazy loading; `/analysis/` is the one-shot for the overview. Version the confluence config so saved snapshots stay interpretable.

---

## 6. Folder Structure

```
backend-drf/
  analysis/                         # NEW app
    models.py                       # caches/snapshots/backtests (added per phase)
    serializers.py
    views.py                        # thin DRF views
    urls.py
    services/
      market_data.py
      support_resistance.py
      volume.py
      trend.py
      confluence.py                 # orchestrator
      opportunity.py
      validation.py                 # backtesting
      news.py                       # Phase 4 — yfinance news only, no AI
      sentiment_rules.py            # Phase 4 (optional) — local keyword scorer, no AI
      patterns/                     # Phase 5
        base.py                     # BasePattern + registry
        double.py  flags.py  triangles.py  head_shoulders.py  cup_handle.py
    indicators/                     # PURE functions, no Django
      pivots.py  volatility.py  volume.py  moving_averages.py
    tests/                          # unit tests per service/indicator
  api/                              # existing LSTM endpoint — UNCHANGED
  accounts/                        # existing JWT auth — UNCHANGED
  stock_prediction_main/

frontend-react/src/
  api/                              # axiosInstance + per-module calls
  components/dashboard/             # Overview, TechnicalTab, OpportunityTab, ...
  components/charts/                # reusable chart components
```

---

## 7. Revised Development Roadmap

### Phase 0 — Foundation Refactor
Prepare the codebase **without changing functionality**. Introduce the service-layer architecture; create the `analysis` app; extract reusable service classes; separate business logic from API views. **SQLite, JWT, and project structure unchanged.**
→ *Outcome: a clean foundation for future engines.*

### Phase 1 — Core Technical Analysis Engines
Build the objective, verifiable core: **MarketDataService, SupportResistanceService, TrendAnalysisService, VolumeAnalysisService.** Surface each on the dashboard.
→ *Outcome: meaningful technical analysis with no ML and no sentiment.*

### Phase 2 — Confluence & Opportunity
**ConfluenceScoringService** combines Trend + S/R + Volume → score, classification, confidence. **OpportunityService** derives entry/stop/target + risk/reward.
→ *Outcome: the platform identifies and ranks opportunities using objective criteria.*

### Phase 3 — Validation & Backtesting (critical)
**ValidationService:** historical testing, win-rate, profit-factor, risk/reward, drawdown. A confluence score untested against history is only a hypothesis — **backtesting is mandatory before any further modules.**
→ *Outcome: evidence the framework has measurable value.*

### Phase 4 — News (yfinance only) + optional rule-based sentiment
**Start simple:** `NewsAnalysisService` collects yfinance news and the dashboard **displays** it — nothing more. **No AI/LLM, no external sentiment service.** Sentiment is optional and deferred; if added later it uses a separate, local **rule-based** keyword scorer only. See §11.
→ *Outcome: contextual news layered onto the validated core, with zero AI dependency.*

### Phase 5 — Pattern Recognition (supporting signal only)
Double Bottom/Top, Flag, Pennant, Cup & Handle, Head & Shoulders, Triangles. **Every pattern returns a confidence score and must be validated through ValidationService.** Patterns are a supporting signal, never the centerpiece.
→ *Outcome: subjective patterns added only after the objective core is proven.*

---

## 8. Priority Order

1. Market Data · 2. Support & Resistance · 3. Volume Analysis · 4. Trend Analysis · 5. Confluence Scoring · 6. Opportunity Analysis · 7. Backtesting / Validation · 8. News & Sentiment · 9. Pattern Recognition

Rationale: objective + verifiable first; wire confluence early (even with 3 inputs) to prove the pipeline; **validate before** adding subjective parts.

---

## 9. Potential Technical Challenges

- **Pattern recognition is subjective and false-positive-prone** (Cup & Handle has no universal definition). Mitigation: Phase 5 only, always attach confidence, validate via backtesting, keep it a supporting signal.
- **yfinance reliability/limits:** unofficial API, rate limits, schema drift, thin/stale news, **no historical news archive** (limits sentiment backtesting). Mitigation: aggressive caching, retries, graceful degradation; recommend (not require) a paid news source later.
- **Lookahead bias in backtesting** — the classic killer. Mitigation: strict point-in-time slicing; sanity-test the tester on a known result.
- **Overfitting confluence weights** = curve-fitting. Mitigation: out-of-sample / walk-forward validation; keep configs simple and versioned.
- **Latency** of running multiple engines per request. Mitigation: fetch-once/pass-down + caching; defer any queue/async until actually needed.
- **"Advice" framing risk** — entry/stop/target edges toward financial advice. Mitigation: prominent disclaimers, educational framing, never auto-trade.

---

## 10. Reliability & Maintainability

- **Test pure functions hard** — indicators and pattern geometry are deterministic; unit-test against known fixtures.
- **Uniform engine contract** (`signal/confidence/details/viz`) → simple confluence + simple frontend.
- **Config over code** for confluence weights and thresholds — versioned config, not hardcoded numbers.
- **Graceful degradation** — one engine failing returns partials with `warnings`, never a 500.
- **Observability** — log cache hits, fetch failures, engine timings.
- **Secret hygiene** — the committed `backend-drf/.env` holds a live `SECRET_KEY`; gitignore + rotate it early. Same for any future provider keys.
- **Keep the LSTM endpoint isolated** in `api/`, labeled as the educational/comparison model.
- **Honesty in the UI** — show confidence and the per-factor breakdown; always carry the not-financial-advice disclaimer.

---

## 11. News & Sentiment (Phase 4 — yfinance only, NO AI/LLM)

**Locked constraints for this module:**

- **Source:** yfinance news **only**. No other news API.
- **No external AI/LLM whatsoever** — no Claude, no OpenAI, no Gemini, no FinBERT, no hosted ML service of any kind.
- **Start minimal:** initially just **collect and display** Yahoo Finance news. No scoring.
- **Sentiment is optional and deferred** — if added later, it must use **simple local rule-based methods** (keyword/lexicon), not AI.
- **`NewsAnalysisService` stays independent from any sentiment logic** so news display never depends on scoring.

### Step 1 (do this first): News collection + display
```
yfinance News  →  NewsAnalysisService  →  /news/{ticker}/  →  Display in dashboard
```
`NewsAnalysisService` fetches `ticker.news` via yfinance, normalizes each item (title, publisher, link, publish time), dedupes, and returns a clean list. The frontend renders a simple news feed. **That is the entire initial deliverable.**

### Step 2 (optional, later): Rule-based sentiment — separate service
If/when sentiment is wanted, add a **separate, self-contained** `RuleBasedSentimentService` that scores a headline using a local positive/negative keyword lexicon (e.g. "beats", "surge", "upgrade" → positive; "miss", "lawsuit", "downgrade" → negative) and returns `{sentiment, score}`.

- Fully offline, deterministic, zero dependencies, zero cost.
- Kept **separate** from `NewsAnalysisService` — news collection never depends on it.
- No provider interface or abstraction is needed at this stage (there is only one local method). An interface can be reconsidered far in the future *only if* requirements change — it is explicitly out of scope now.

> The earlier "swappable AI provider" design is removed per constraint. Phase 4 introduces **no AI dependency and no vendor integration** — the platform runs entirely on yfinance + (optionally) local keyword rules.

---

## North star

> Build objective, testable engines (Trend + S/R + Volume) → combine via configurable confluence → derive opportunity (entry/stop/target/RR) → **prove the edge with backtesting** → only then layer in yfinance news (display-only, no AI) and supporting pattern signals. Everything measurable, everything validated, nothing presented as a guarantee.
