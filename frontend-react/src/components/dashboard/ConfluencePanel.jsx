import { useEffect, useState } from "react";
import axiosInstance from "../../axiosInstance";

const dirColor = (s) =>
    s === "bullish" ? "#26a69a" : s === "bearish" ? "#ef5350" : "#6c757d";

const PRETTY = {
    trend: "Trend",
    support_resistance: "Support / Resistance",
    volume: "Volume",
};

/**
 * ConfluencePanel — the headline summary.
 * GET /api/v1/confluence/<ticker>/ — combines trend + S/R + volume into one score.
 */
const ConfluencePanel = ({ ticker, asOf = "", period = "2y" }) => {
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
                    `confluence/${encodeURIComponent(ticker)}/?period=${period}&interval=1d` +
                        (asOf ? `&as_of=${asOf}` : "")
                );
                if (active) setData(res.data.data);
            } catch (e) {
                if (active) setError(e.response?.data?.error || "Could not load confluence score.");
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
    const color = d ? dirColor(d.direction) : "#6c757d";

    return (
        <div className="text-light mt-4 p-3 rounded" style={{ background: "#15181f" }}>
            <h5 className="mb-2">Confluence Score {ticker ? `(${ticker})` : ""}</h5>
            {loading && <p>Scoring the setup…</p>}
            {error && <div className="text-danger">{error}</div>}

            {d && (
                <>
                    <div className="d-flex align-items-baseline gap-3 mb-2">
                        <span style={{ fontSize: 40, fontWeight: 700, color }}>
                            {d.score}
                            <span style={{ fontSize: 18, color: "#888" }}>/100</span>
                        </span>
                        <span
                            style={{
                                background: color,
                                padding: "3px 12px",
                                borderRadius: 4,
                                fontWeight: 600,
                            }}
                        >
                            {d.classification}
                        </span>
                        <span style={{ textTransform: "capitalize", color }}>{d.direction}</span>
                    </div>

                    {/* Score bar */}
                    <div style={{ background: "#2a2e39", borderRadius: 4, height: 10, maxWidth: 560 }}>
                        <div
                            style={{
                                width: `${d.score}%`,
                                background: color,
                                height: "100%",
                                borderRadius: 4,
                            }}
                        />
                    </div>

                    <table
                        className="table table-sm table-dark mt-3"
                        style={{ fontSize: "13px", maxWidth: 680 }}
                    >
                        <thead>
                            <tr>
                                <th>Factor</th>
                                <th>Signal</th>
                                <th>Confidence</th>
                                <th>Weight</th>
                                <th>Points</th>
                                <th>Why</th>
                            </tr>
                        </thead>
                        <tbody>
                            {d.factors.map((f) => {
                                const sign =
                                    f.signal === "bullish" ? 1 : f.signal === "bearish" ? -1 : 0;
                                return (
                                    <tr key={f.name}>
                                        <td>{PRETTY[f.name] || f.name}</td>
                                        <td style={{ color: dirColor(f.signal), textTransform: "capitalize" }}>
                                            {f.signal}
                                        </td>
                                        <td>{f.confidence}</td>
                                        <td>{f.weight}</td>
                                        <td style={{ color: f.contribution >= 0 ? "#26a69a" : "#ef5350" }}>
                                            {sign} × {f.confidence} × {f.weight} ={" "}
                                            <strong>
                                                {f.contribution > 0 ? `+${f.contribution}` : f.contribution}
                                            </strong>
                                        </td>
                                        <td>{f.reason}</td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>

                    <p className="text-secondary" style={{ fontSize: "13px", maxWidth: 700 }}>
                        <strong>How the points are computed:</strong> each factor's points ={" "}
                        <code>sign × confidence × weight</code>, where{" "}
                        <strong>sign</strong> = +1 bullish, −1 bearish, <strong>0 neutral</strong>{" "}
                        (so a neutral factor always scores 0). <strong>Confidence</strong> (0–1) comes
                        from each engine — trend strength, the nearby level's strength, or the volume
                        conviction. The final score is{" "}
                        <code>|bullish points − bearish points|</code>; a{" "}
                        <strong>high score means the factors agree</strong> (clean setup), a low score
                        means they conflict or are neutral. 0–30 Weak · 31–60 Moderate · 61–80 Strong ·
                        81–100 Very Strong.
                    </p>
                </>
            )}
        </div>
    );
};

export default ConfluencePanel;
