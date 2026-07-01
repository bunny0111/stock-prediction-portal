import { useEffect, useState } from "react";
import axiosInstance from "../../axiosInstance";

const dirColor = (dir) =>
    dir === "uptrend" ? "#26a69a" : dir === "downtrend" ? "#ef5350" : "#6c757d";

function buildExplanation(d) {
    if (d.direction === "uptrend") {
        return `Price is in an uptrend (${d.structure}), trending up about ${Math.abs(
            d.slope_pct_per_bar
        )}% per day. The trend is ${d.strength_label} (cleanliness R²=${d.r_squared}).`;
    }
    if (d.direction === "downtrend") {
        return `Price is in a downtrend (${d.structure}), trending down about ${Math.abs(
            d.slope_pct_per_bar
        )}% per day. The trend is ${d.strength_label} (cleanliness R²=${d.r_squared}).`;
    }
    return `No clear trend — price action is sideways/choppy (${d.structure}). Direction and structure don't agree, so there's no reliable trend to follow right now.`;
}

/**
 * TrendPanel — shows TrendAnalysisService result for a ticker.
 * GET /api/v1/trend/<ticker>/
 */
const TrendPanel = ({ ticker, asOf = "", period = "2y" }) => {
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
                    `trend/${encodeURIComponent(ticker)}/?period=${period}&interval=1d` +
                        (asOf ? `&as_of=${asOf}` : "")
                );
                if (active) setData(res.data.data);
            } catch (e) {
                if (active) setError(e.response?.data?.error || "Could not load trend analysis.");
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
            <h5 className="mb-2">Trend Analysis {ticker ? `(${ticker})` : ""}</h5>
            {loading && <p>Loading trend analysis…</p>}
            {error && <div className="text-danger">{error}</div>}
            {d && d.note && <p className="text-secondary">{d.note}</p>}

            {d && !d.note && (
                <>
                    <span
                        style={{
                            background: dirColor(d.direction),
                            padding: "2px 12px",
                            borderRadius: 4,
                            fontWeight: 600,
                            textTransform: "capitalize",
                        }}
                    >
                        {d.direction}
                    </span>
                    <span className="text-secondary ms-2">
                        {d.strength_label} ({Math.round(d.strength * 100)}%)
                    </span>

                    <table
                        className="table table-sm table-dark mt-2"
                        style={{ fontSize: "13px", maxWidth: 560 }}
                    >
                        <tbody>
                            <tr>
                                <td>Direction</td>
                                <td style={{ textTransform: "capitalize" }}>{d.direction}</td>
                            </tr>
                            <tr>
                                <td>Price structure</td>
                                <td>{d.structure}</td>
                            </tr>
                            <tr>
                                <td>Slope (per day)</td>
                                <td>{d.slope_pct_per_bar}%</td>
                            </tr>
                            <tr>
                                <td>Trend cleanliness (R²)</td>
                                <td>{d.r_squared}</td>
                            </tr>
                        </tbody>
                    </table>

                    <p className="text-secondary" style={{ fontSize: "13px", maxWidth: 660 }}>
                        <strong>What this means:</strong> {buildExplanation(d)}
                    </p>
                </>
            )}
        </div>
    );
};

export default TrendPanel;
