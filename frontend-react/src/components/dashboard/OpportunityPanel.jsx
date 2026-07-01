import { useEffect, useState } from "react";
import axiosInstance from "../../axiosInstance";

const sideColor = (s) => (s === "long" ? "#26a69a" : s === "short" ? "#ef5350" : "#6c757d");
const rrColor = (q) => (q === "good" ? "#26a69a" : q === "fair" ? "#f0ad4e" : "#ef5350");
const trendColor = (t) =>
    t === "uptrend" ? "#26a69a" : t === "downtrend" ? "#ef5350" : "#6c757d";

const TrendBadge = ({ direction, strength }) =>
    direction ? (
        <span
            style={{
                background: trendColor(direction),
                padding: "2px 10px",
                borderRadius: 4,
                fontSize: 13,
                textTransform: "capitalize",
            }}
        >
            {direction}
            {strength ? ` · ${strength}` : ""}
        </span>
    ) : null;

/**
 * OpportunityPanel — educational trade plan.
 * GET /api/v1/opportunity/<ticker>/
 */
const OpportunityPanel = ({ ticker, asOf = "", period = "2y" }) => {
    const [data, setData] = useState(null);
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (!ticker) return;
        let active = true;
        (async () => {
            setLoading(true);
            setError("");
            setData(null);
            try {
                const res = await axiosInstance.get(
                    `opportunity/${encodeURIComponent(ticker)}/?period=${period}&interval=1d` +
                        (asOf ? `&as_of=${asOf}` : "")
                );
                if (active) setData(res.data.data);
            } catch (e) {
                if (active) setError(e.response?.data?.error || "Could not load opportunity analysis.");
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

    return (
        <div className="text-light mt-4">
            <h5 className="mb-2">Reference Levels {ticker ? `(${ticker})` : ""}</h5>
            {loading && <p>Building reference levels…</p>}
            {error && <div className="text-danger">{error}</div>}

            {d && d.no_trade && (
                <>
                    <div className="mb-2">
                        <span className="text-secondary me-2" style={{ fontSize: 13 }}>Trend:</span>
                        <TrendBadge direction={d.trend_direction} strength={d.trend_strength} />
                    </div>
                    <p className="text-secondary">
                        <strong>No clear trade setup.</strong> {d.reason} (confluence score{" "}
                        {d.confluence_score}/100, {d.setup_quality}).
                    </p>
                </>
            )}

            {d && !d.no_trade && (
                <>
                    <div className="d-flex align-items-center flex-wrap gap-3 mb-2">
                        <span
                            style={{
                                background: sideColor(d.direction),
                                padding: "3px 14px",
                                borderRadius: 4,
                                fontWeight: 700,
                                textTransform: "uppercase",
                            }}
                        >
                            {d.direction}
                        </span>
                        <span>
                            <span className="text-secondary me-1" style={{ fontSize: 13 }}>Trend:</span>
                            <TrendBadge direction={d.trend_direction} strength={d.trend_strength} />
                        </span>
                        <span className="text-secondary">
                            {d.setup_quality} setup (confluence {d.confluence_score}/100)
                        </span>
                        <span style={{ color: rrColor(d.rr_quality) }}>
                            risk/reward: {d.rr_quality}
                        </span>
                    </div>

                    <table
                        className="table table-sm table-dark"
                        style={{ fontSize: "13px", maxWidth: 560 }}
                    >
                        <tbody>
                            <tr>
                                <td>Entry zone</td>
                                <td>
                                    {d.entry_zone[0]} – {d.entry_zone[1]}
                                </td>
                            </tr>
                            <tr>
                                <td style={{ color: "#ef5350" }}>Stop-loss</td>
                                <td style={{ color: "#ef5350" }}>
                                    {d.stop_loss} (risk {d.risk}/share)
                                </td>
                            </tr>
                            {d.targets.map((t, i) => (
                                <tr key={i}>
                                    <td style={{ color: "#26a69a" }}>
                                        Target {i + 1}
                                    </td>
                                    <td style={{ color: "#26a69a" }}>
                                        {t.price} (reward {t.reward}, R:R{" "}
                                        <strong>{t.risk_reward}</strong>)
                                    </td>
                                </tr>
                            ))}
                            <tr>
                                <td>ATR (volatility)</td>
                                <td>{d.atr}</td>
                            </tr>
                        </tbody>
                    </table>

                    <p className="text-secondary" style={{ fontSize: "13px", maxWidth: 660 }}>
                        <strong>How this was built:</strong> direction from the confluence score; the
                        stop sits just beyond the nearest{" "}
                        {d.direction === "long" ? "support" : "resistance"} (buffered by ATR), and
                        targets are the next{" "}
                        {d.direction === "long" ? "resistance" : "support"} levels. Risk/Reward (R:R)
                        is reward ÷ risk — aim for ≥ 2.
                    </p>
                </>
            )}
        </div>
    );
};

export default OpportunityPanel;
