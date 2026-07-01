import { useEffect, useState } from "react";
import axiosInstance from "../../axiosInstance";

const postureColor = (s) =>
    s === "Bullish" ? "#26a69a" : s === "Bearish" ? "#ef5350" : "#6c757d";

const confColor = (s) =>
    s === "High" ? "#26a69a" : s === "Low" ? "#ef5350" : "#e2b007";

const dirColor = (s) =>
    s === "bullish" ? "#26a69a" : s === "bearish" ? "#ef5350" : "#6c757d";

const PRETTY = { trend: "Trend", support_resistance: "Support / Resistance", volume: "Volume" };

const fmt = (v) => (v == null ? "—" : Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }));

/**
 * RangeForecastPanel — the calibrated next-day RANGE forecast (not a price prediction).
 * GET /api/v1/range-forecast/<ticker>/
 *
 * Primary engine: empirical rolling quantiles (EWMA-adjusted for regime).
 * ATR drives the expected high/low reach. Trend posture & confidence are
 * market-condition labels, not directional forecasts.
 */
const RangeForecastPanel = ({ ticker, asOf = "", period = "2y" }) => {
    const [data, setData] = useState(null);
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);
    const [side, setSide] = useState(null);   // "long" | "short" | null (direction = your call)
    const [showHelp, setShowHelp] = useState(false);
    const [showPosture, setShowPosture] = useState(false);
    const [showConf, setShowConf] = useState(false);

    useEffect(() => {
        if (!ticker) return;
        let active = true;
        (async () => {
            setLoading(true);
            setError("");
            setData(null);
            try {
                const res = await axiosInstance.get(
                    `range-forecast/${encodeURIComponent(ticker)}/?period=${period}&interval=1d` +
                        (asOf ? `&as_of=${asOf}` : "")
                );
                if (active) setData(res.data.data);
            } catch (e) {
                if (active) setError(e.response?.data?.error || "Could not load range forecast.");
            } finally {
                if (active) setLoading(false);
            }
        })();
        return () => {
            active = false;
        };
    }, [ticker, asOf, period]);

    if (!ticker) return null;
    const d = data?.details;
    const r = d?.ranges || {};
    const posture = d?.trend_posture;
    const conf = d?.confidence_level;
    const cal = d?.calibration;

    // Trade levels — auto-derived from the calibrated range; direction is the only input.
    let plan = null;
    if (d && !d.error && side && r["50"] && r["70"] && r["90"]) {
        const r50 = r["50"], r70 = r["70"], r90 = r["90"];
        if (side === "long") {
            const ez = [r70.low, r50.low];
            const entry = (ez[0] + ez[1]) / 2;
            const stop = r90.low, t1 = r70.high, t2 = d.expected_high, risk = entry - stop;
            plan = { ez, stop, t1, t2, risk, rr1: (t1 - entry) / risk, rr2: t2 != null ? (t2 - entry) / risk : null, edge: "lower", stopWord: "below" };
        } else {
            const ez = [r50.high, r70.high];
            const entry = (ez[0] + ez[1]) / 2;
            const stop = r90.high, t1 = r70.low, t2 = d.expected_low, risk = stop - entry;
            plan = { ez, stop, t1, t2, risk, rr1: (entry - t1) / risk, rr2: t2 != null ? (entry - t2) / risk : null, edge: "upper", stopWord: "above" };
        }
    }

    const RangeRow = ({ label, band, accent }) => (
        <div className="d-flex align-items-center justify-content-between py-2"
             style={{ borderBottom: "1px solid #2a2e39" }}>
            <span style={{ color: "#9aa0aa", fontSize: 13 }}>{label}</span>
            <span style={{ fontWeight: 600 }}>
                {band ? (
                    <>
                        <span style={{ color: "#ef5350" }}>{fmt(band.low)}</span>
                        <span style={{ color: "#6c757d" }}> &nbsp;to&nbsp; </span>
                        <span style={{ color: "#26a69a" }}>{fmt(band.high)}</span>
                        <span style={{ color: accent || "#6c757d", fontSize: 12 }}> &nbsp;(width {band.width_pct}%)</span>
                    </>
                ) : "—"}
            </span>
        </div>
    );

    return (
        <div className="text-light mt-4 p-3 rounded" style={{ background: "#15181f" }}>
            <h5 className="mb-3">Next-Day Range Forecast {ticker ? `(${ticker})` : ""}</h5>

            {loading && <p>Estimating the range…</p>}
            {error && <div className="text-danger">{error}</div>}

            {d && !d.error && (
                <>
                    {d.limited_history && (
                        <div className="mb-3 p-2 rounded" style={{ background: "#3a2e12", border: "1px solid #6b5414", color: "#f0c040", fontSize: 13 }}>
                            ⚠️ Limited historical data available ({d.history_days} trading days). Calibration estimates may be less reliable for this security.
                        </div>
                    )}
                    <div className="d-flex align-items-baseline gap-3 mb-3 flex-wrap">
                        <div>
                            <div style={{ color: "#9aa0aa", fontSize: 12 }}>Current Price</div>
                            <div style={{ fontSize: 32, fontWeight: 700 }}>{fmt(d.current_price)}</div>
                            <div style={{ color: "#6c757d", fontSize: 11 }}>as of {d.as_of_date}</div>
                        </div>
                        <div className="ms-auto d-flex gap-2 flex-wrap">
                            <button type="button"
                                onClick={() => setShowPosture((p) => !p)}
                                title="Click to see how this is calculated"
                                style={{ background: postureColor(posture?.label), padding: "4px 12px", borderRadius: 4, fontWeight: 600, border: "none", color: "#fff", cursor: "pointer" }}>
                                Trend Posture: {posture?.label || "—"} {showPosture ? "▲" : "▾"}
                            </button>
                            <button type="button"
                                onClick={() => setShowConf((c) => !c)}
                                title="Click to see how this is calculated"
                                style={{ background: confColor(conf?.label), padding: "4px 12px", borderRadius: 4, fontWeight: 600, color: "#15181f", border: "none", cursor: "pointer" }}>
                                Confidence: {conf?.label || "—"} {showConf ? "▲" : "▾"}
                            </button>
                        </div>
                    </div>

                    {/* Trend Posture breakdown — how the score is computed (click the badge) */}
                    {showPosture && posture?.factors?.length > 0 && (
                        <div className="mb-3 p-2 rounded" style={{ background: "#11151c", border: "1px solid #2a2e39", maxWidth: 680 }}>
                            <div style={{ fontSize: 13, marginBottom: 6 }}>
                                <strong>Trend Posture — how it's computed</strong>{" "}
                                · score {posture.score}/100 ({posture.classification})
                                {" · "}bull {posture.bull_points} − bear {posture.bear_points}
                            </div>
                            <table className="table table-sm table-dark mb-1" style={{ fontSize: 12.5 }}>
                                <thead>
                                    <tr><th>Factor</th><th>Signal</th><th>Conf.</th><th>Weight</th><th>Points</th><th>Why</th></tr>
                                </thead>
                                <tbody>
                                    {posture.factors.map((f) => {
                                        const sign = f.signal === "bullish" ? 1 : f.signal === "bearish" ? -1 : 0;
                                        return (
                                            <tr key={f.name}>
                                                <td>{PRETTY[f.name] || f.name}</td>
                                                <td style={{ color: dirColor(f.signal), textTransform: "capitalize" }}>{f.signal}</td>
                                                <td>{f.confidence}</td>
                                                <td>{f.weight}</td>
                                                <td style={{ color: f.contribution >= 0 ? "#26a69a" : "#ef5350" }}>
                                                    {sign} × {f.confidence} × {f.weight} ={" "}
                                                    <strong>{f.contribution > 0 ? `+${f.contribution}` : f.contribution}</strong>
                                                </td>
                                                <td>{f.reason}</td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                            <div className="text-secondary" style={{ fontSize: 12 }}>
                                Each factor's points = <code>sign × confidence × weight</code> (sign: +1 bullish, −1 bearish,
                                0 neutral). Posture = the sign of (bullish − bearish points); weights are Trend 40 / S-R 30 /
                                Volume 30. <strong>This describes the current market condition, not a forecast</strong> —
                                backtesting found no reliable directional edge in it.
                            </div>
                        </div>
                    )}

                    {/* Confidence breakdown — how the volatility-regime confidence is computed (click the badge) */}
                    {showConf && conf && (
                        <div className="mb-3 p-2 rounded" style={{ background: "#11151c", border: "1px solid #2a2e39", maxWidth: 680 }}>
                            <div style={{ fontSize: 13, marginBottom: 6 }}>
                                <strong>Confidence — how it's computed</strong> · regime factor {d.regime_ratio}×
                            </div>
                            <div className="text-secondary" style={{ fontSize: 12.5, lineHeight: 1.6 }}>
                                It reflects the <strong>volatility regime</strong> — is this stock currently more or less
                                volatile than its own recent norm? Computed from the <strong>regime factor</strong> =
                                recent (EWMA) volatility ÷ its 1-year-average volatility:
                            </div>
                            <table className="table table-sm table-dark mt-2 mb-1" style={{ fontSize: 12.5 }}>
                                <tbody>
                                    <tr><td style={{ color: "#26a69a", width: 90 }}>High</td><td>factor ≤ 0.90 — calmer than usual → range is tighter &amp; more reliable</td></tr>
                                    <tr><td style={{ color: "#e2b007" }}>Medium</td><td>0.90 – 1.15 — volatility near its average</td></tr>
                                    <tr><td style={{ color: "#ef5350" }}>Low</td><td>factor &gt; 1.15 (volatility expanding), or very limited history → range wider &amp; less stable</td></tr>
                                </tbody>
                            </table>
                            <div className="text-secondary" style={{ fontSize: 12.5 }}>
                                This stock: regime factor <strong>{d.regime_ratio}×</strong> → <strong>{conf.label}</strong>. {conf.detail}
                            </div>
                        </div>
                    )}

                    <div style={{ maxWidth: 560 }}>
                        <RangeRow label="50% Most Likely Zone" band={r["50"]} accent="#e2b007" />
                        <RangeRow label="70% Expected Range" band={r["70"]} accent="#e2b007" />
                        <RangeRow label="90% Expected Range" band={r["90"]} accent="#e2b007" />
                        <div className="d-flex align-items-center justify-content-between py-2"
                             style={{ borderBottom: "1px solid #2a2e39" }}>
                            <span style={{ color: "#9aa0aa", fontSize: 13 }}>Expected High / Low <span style={{ color: "#6c757d", fontSize: 11 }}>(±1 ATR)</span></span>
                            <span style={{ fontWeight: 600 }}>
                                <span style={{ color: "#26a69a" }}>{fmt(d.expected_high)}</span>
                                <span style={{ color: "#6c757d" }}> &nbsp;/&nbsp; </span>
                                <span style={{ color: "#ef5350" }}>{fmt(d.expected_low)}</span>
                            </span>
                        </div>
                    </div>

                    {/* Honest, earned confidence: show the historical calibration */}
                    {cal && (
                        <div className="mt-3 p-2 rounded" style={{ background: "#1b1f29", maxWidth: 560 }}>
                            <div style={{ fontSize: 12, color: "#9aa0aa", marginBottom: 4 }}>
                                Historical calibration for {ticker} — how often each interval actually contained
                                the next close ({cal.samples} point-in-time days). Closer to nominal = better.
                            </div>
                            <table className="table table-sm table-dark mb-0" style={{ fontSize: 13 }}>
                                <tbody>
                                    <tr>
                                        <td>Interval</td><td>50%</td><td>70%</td><td>90%</td>
                                    </tr>
                                    <tr>
                                        <td>Actual coverage</td>
                                        <td>{cal["50"]}%</td>
                                        <td>{cal["70"]}%</td>
                                        <td>{cal["90"]}%</td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                    )}

                    {/* Trade levels — auto-derived from the calibrated range; pick a side (direction is your call) */}
                    <div className="mt-3 p-2 rounded" style={{ background: "#10202a", border: "1px solid #1d3b4a", maxWidth: 560 }}>
                        <div className="d-flex align-items-center gap-2 flex-wrap mb-2">
                            <strong style={{ fontSize: 13 }}>Trade levels</strong>
                            <div className="btn-group btn-group-sm ms-1">
                                <button type="button"
                                    className={"btn btn-sm " + (side === "long" ? "btn-success" : "btn-outline-success")}
                                    onClick={() => setSide(side === "long" ? null : "long")}>Long</button>
                                <button type="button"
                                    className={"btn btn-sm " + (side === "short" ? "btn-danger" : "btn-outline-danger")}
                                    onClick={() => setSide(side === "short" ? null : "short")}>Short</button>
                            </div>
                            <span className="text-secondary" style={{ fontSize: 12 }}>← pick a side (direction is your call)</span>
                        </div>

                        {!side && (
                            <div className="text-secondary" style={{ fontSize: 12 }}>
                                Levels are <strong>auto-derived from the calibrated range — no typing</strong>. Pick Long or
                                Short to see entry zone / stop / target.
                            </div>
                        )}

                        {side && plan && (
                            <>
                                <table className="table table-sm table-dark mb-1" style={{ fontSize: 13 }}>
                                    <tbody>
                                        <tr>
                                            <td>Entry zone <span style={{ color: "#6c757d", fontSize: 11 }}>({plan.edge} edge — don't chase mid-range)</span></td>
                                            <td>{fmt(plan.ez[0])} – {fmt(plan.ez[1])}</td>
                                        </tr>
                                        <tr>
                                            <td style={{ color: "#ef5350" }}>Stop <span style={{ color: "#6c757d", fontSize: 11 }}>({plan.stopWord} 90% — ~5% noise hit)</span></td>
                                            <td style={{ color: "#ef5350" }}>{fmt(plan.stop)}</td>
                                        </tr>
                                        <tr>
                                            <td style={{ color: "#26a69a" }}>Target</td>
                                            <td style={{ color: "#26a69a" }}>
                                                {fmt(plan.t1)} <span style={{ color: "#6c757d", fontSize: 11 }}>(70%)</span>
                                                {plan.t2 != null && <> / {fmt(plan.t2)} <span style={{ color: "#6c757d", fontSize: 11 }}>(stretch)</span></>}
                                            </td>
                                        </tr>
                                        <tr><td>Risk / share</td><td>{fmt(plan.risk)} <span style={{ color: "#9aa0aa", fontSize: 11 }}>(from entry-zone mid)</span></td></tr>
                                        <tr>
                                            <td>Reward : Risk</td>
                                            <td>{plan.rr1.toFixed(1)} : 1 <span style={{ color: "#6c757d", fontSize: 11 }}>(70%)</span>
                                                {plan.rr2 != null && <> · {plan.rr2.toFixed(1)} : 1 <span style={{ color: "#6c757d", fontSize: 11 }}>(stretch)</span></>}
                                            </td>
                                        </tr>
                                    </tbody>
                                </table>
                                <div className="text-secondary" style={{ fontSize: 12 }}>
                                    <strong>Size</strong> = your risk budget ÷ {fmt(plan.risk)}/share. Entry = the {plan.edge} edge of the
                                    range; stop sits outside the 90% band (a break there is abnormal); target = the opposite
                                    expected extreme. <strong>You</strong> choose direction — these are risk levels, not a buy/sell signal.
                                </div>
                            </>
                        )}
                    </div>

                    <p className="text-secondary mt-3 mb-0" style={{ fontSize: 12, maxWidth: 700 }}>
                        <strong>How it's built:</strong> the 50/70/90 ranges come from the{" "}
                        <strong>empirical distribution of this stock's daily returns</strong> (fat-tail aware),
                        widened by an <strong>EWMA volatility</strong> regime factor ({d.regime_scale ?? d.regime_ratio}× —
                        ≥1, widens the band when volatility is expanding and never narrows below the calibrated
                        baseline). <strong>Expected High/Low</strong> use{" "}
                        <strong>ATR</strong> (avg true range {fmt(d.atr)}). <strong>Trend Posture</strong> and{" "}
                        <strong>Confidence</strong> describe the current market condition (from the Trend / Volume /
                        Support-Resistance engines and the volatility regime) — they are not directional forecasts.
                    </p>

                    {/* Collapsible help: where the data comes from & how it's calculated */}
                    <button type="button" className="btn btn-sm p-0 mt-2"
                        style={{ fontSize: 12, color: "#42a5f5", textDecoration: "none", boxShadow: "none" }}
                        onClick={() => setShowHelp((h) => !h)}>
                        ⓘ How this works — data &amp; method {showHelp ? "▲" : "▼"}
                    </button>
                    {showHelp && (
                        <div className="mt-2 p-3 rounded text-secondary"
                            style={{ background: "#11151c", border: "1px solid #2a2e39", fontSize: 12.5, maxWidth: 720, lineHeight: 1.6 }}>
                            <div className="mb-2">
                                <strong style={{ color: "#d1d4dc" }}>Where the data comes from</strong><br />
                                Daily price history (OHLCV) from <strong>Yahoo Finance</strong> — about the last year
                                (~250 trading days) of this stock's daily % changes. No manual inputs, no paid feeds.
                            </div>
                            <div className="mb-2">
                                <strong style={{ color: "#d1d4dc" }}>How the ranges are built</strong><br />
                                We read the <strong>actual distribution</strong> of those past daily moves (the real one,
                                fat tails included — not a textbook bell curve) and take percentiles: <strong>90% range =
                                5th–95th</strong> percentile, <strong>70% = 15th–85th</strong>, <strong>50% = 25th–75th</strong> —
                                applied to today's price. The band is then <strong>widened</strong> by a volatility-regime
                                factor (recent EWMA volatility vs the 1-year average) when volatility is rising; it never
                                narrows below the calibrated baseline.
                            </div>
                            <div className="mb-2">
                                <strong style={{ color: "#d1d4dc" }}>Width % &amp; the entry zone</strong><br />
                                The <strong>(width X%)</strong> next to each range = <code>(high − low) ÷ price × 100</code> —
                                the full span of that range as a % of price (e.g. 90%: (111.20 − 104.98) ÷ 108.01 × 100 = 5.76%).
                                The Trade-levels <strong>Entry Zone</strong> (long) is the band between the 70% and 50% lows, and its
                                width = <code>(50% low − 70% low) ÷ price × 100</code> (e.g. (1,301.26 − 1,296.02) ÷ 1,311.60 × 100 = 0.40%).
                                That's the gap between the <strong>15th and 25th percentile</strong> of recent daily returns — so it
                                scales with the stock's own volatility and shifts with the selected date. It's a placement guide,
                                not a signal.
                            </div>
                            <div className="mb-2">
                                <strong style={{ color: "#d1d4dc" }}>Expected High / Low</strong><br />
                                Today's price ± <strong>ATR</strong> (Average True Range — the typical daily high-to-low
                                swing over 14 days).
                            </div>
                            <div className="mb-2">
                                <strong style={{ color: "#d1d4dc" }}>Actual coverage — the trust check</strong><br />
                                For each of the last several hundred days we built the range using <strong>only the data
                                available before that day</strong>, then checked whether the next day's close landed inside.
                                A "90%" range that contained the close ~90% of the time is well-calibrated — that's how you
                                know the numbers mean what they say.
                            </div>
                            <div>
                                <strong style={{ color: "#d1d4dc" }}>What it does NOT do</strong><br />
                                It forecasts <strong>how much</strong> price is likely to move, <strong>not which way</strong>.
                                Daily direction isn't reliably predictable (tested thoroughly); the <em>size</em> of moves is,
                                because volatility clusters. Use it for <strong>sizing &amp; risk</strong>, not for picking direction.
                            </div>
                        </div>
                    )}
                </>
            )}
            {d?.error && <div className="text-secondary">{d.error}</div>}
        </div>
    );
};

export default RangeForecastPanel;
