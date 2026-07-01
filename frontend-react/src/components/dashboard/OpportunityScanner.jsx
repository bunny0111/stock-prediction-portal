import { useState } from "react";
import axiosInstance from "../../axiosInstance";

const riskColor = (r) => (r === "High" ? "#ef5350" : r === "Medium" ? "#e2b007" : "#26a69a");
const confColor = (c) => (c === "High" ? "#26a69a" : c === "Low" ? "#ef5350" : "#e2b007");

/**
 * OpportunityScanner (EXPERIMENTAL) — additive, does not replace the homepage.
 * GET /api/v1/scan/ — ranks a fixed liquid watchlist by expected next-day move
 * + expansion. Magnitude/risk only; NOT a directional signal.
 */
const OpportunityScanner = () => {
    const [open, setOpen] = useState(false);
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");

    const load = async () => {
        setLoading(true);
        setError("");
        try {
            const res = await axiosInstance.get("scan/");
            setData(res.data.data);
        } catch (e) {
            setError(e.response?.data?.error || "Could not run the scan.");
        } finally {
            setLoading(false);
        }
    };

    const toggle = () => {
        const next = !open;
        setOpen(next);
        if (next && !data) load();
    };

    return (
        <div className="mb-4">
            <button className="btn btn-sm btn-outline-warning" onClick={toggle}>
                🧪 {open ? "Hide" : "Open"} Opportunity Scanner (experimental)
            </button>

            {open && (
                <div className="text-light mt-3 p-3 rounded" style={{ background: "#15181f" }}>
                    <div className="d-flex justify-content-between align-items-center mb-1">
                        <h5 className="mb-0">Opportunity Scanner</h5>
                        <button className="btn btn-sm btn-outline-light" onClick={load} disabled={loading}>
                            ↻ Refresh
                        </button>
                    </div>
                    <p className="text-secondary" style={{ fontSize: 12, maxWidth: 760 }}>
                        Experimental. Ranks liquid stocks by <strong>expected next-day move</strong> and how{" "}
                        <strong>unusual</strong> today's volatility is vs the stock's own baseline (expansion).
                        Magnitude &amp; risk only — <strong>not a buy/sell signal</strong>; direction is your call.
                    </p>

                    {loading && <p>Scanning the watchlist… (first run fetches all stocks, ~20–30s)</p>}
                    {error && <div className="text-danger">{error}</div>}

                    {data && data.length > 0 && (
                        <table className="table table-sm table-dark align-middle" style={{ fontSize: 13, maxWidth: 760 }}>
                            <thead>
                                <tr>
                                    <th>#</th>
                                    <th>Ticker</th>
                                    <th>Exp. Move (±90%)</th>
                                    <th>Risk</th>
                                    <th>Confidence</th>
                                    <th style={{ minWidth: 150 }}>Opportunity</th>
                                </tr>
                            </thead>
                            <tbody>
                                {data.map((s, i) => (
                                    <tr key={s.ticker}>
                                        <td>{i + 1}</td>
                                        <td>
                                            <strong>{s.ticker.replace(".NS", "")}</strong>
                                            {s.limited_history && (
                                                <span title="limited history" style={{ color: "#e2b007" }}> ⚠</span>
                                            )}
                                        </td>
                                        <td>±{s.expected_move_pct}%</td>
                                        <td style={{ color: riskColor(s.risk_class) }}>{s.risk_class}</td>
                                        <td style={{ color: confColor(s.confidence) }}>{s.confidence}</td>
                                        <td>
                                            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                                <div style={{ flex: "0 0 90px", background: "#2a2e39", borderRadius: 3, height: 8 }}>
                                                    <div style={{ width: `${s.opportunity_score}%`, background: "#42a5f5", height: "100%", borderRadius: 3 }} />
                                                </div>
                                                <span style={{ width: 26 }}>{s.opportunity_score}</span>
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                    {data && data.length === 0 && !loading && (
                        <div className="text-secondary">No results — the data source may be unavailable right now.</div>
                    )}
                </div>
            )}
        </div>
    );
};

export default OpportunityScanner;
