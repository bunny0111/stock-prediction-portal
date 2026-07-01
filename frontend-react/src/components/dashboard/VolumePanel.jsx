import { useEffect, useState } from "react";
import axiosInstance from "../../axiosInstance";

const badgeColor = (s) =>
    s === "bullish" ? "#26a69a" : s === "bearish" ? "#ef5350" : "#6c757d";

// Build a plain-English summary from the raw numbers.
function buildExplanation(data) {
    const d = data.details;
    const rv = d.relative_volume;
    const vol =
        rv >= 2 ? `an unusually high ${rv}× its average volume (a spike)` :
        rv >= 1.3 ? `above-average volume (${rv}× normal)` :
        rv <= 0.7 ? `below-average volume (${rv}× normal)` :
        `roughly average volume (${rv}× normal)`;
    const flow =
        d.obv_trend === "rising" ? "volume is flowing into up-days (accumulation)" :
        d.obv_trend === "falling" ? "volume is flowing into down-days (distribution)" :
        "money flow is flat";
    const concl =
        data.signal === "bullish" ? "This leans bullish — buyers are showing conviction." :
        data.signal === "bearish" ? "This leans bearish — sellers are showing conviction." :
        "No strong volume conviction either way right now.";
    return `The latest session traded on ${vol}, and ${flow}. ${concl}`;
}

/**
 * VolumePanel — shows the VolumeAnalysisService result for a ticker.
 * Fetches GET /api/v1/volume/<ticker>/ and renders signal + stats + explanation.
 */
const fmt = (n) => (n === undefined || n === null ? "—" : Number(n).toLocaleString());

const VolumePanel = ({ ticker, asOf = "", period = "2y" }) => {
    const [data, setData] = useState(null);
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);
    const [showCalc, setShowCalc] = useState(false);

    useEffect(() => {
        if (!ticker) return;
        let active = true;
        (async () => {
            setLoading(true);
            setError("");
            setData(null);
            try {
                const res = await axiosInstance.get(
                    `volume/${encodeURIComponent(ticker)}/?period=${period}&interval=1d` +
                        (asOf ? `&as_of=${asOf}` : "")
                );
                if (active) setData(res.data.data);
            } catch (e) {
                if (active) setError(e.response?.data?.error || "Could not load volume analysis.");
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
            <h5 className="mb-2">Volume Analysis {ticker ? `(${ticker})` : ""}</h5>
            {loading && <p>Loading volume analysis…</p>}
            {error && <div className="text-danger">{error}</div>}

            {d && d.note && <p className="text-secondary">{d.note}</p>}

            {d && !d.note && (
                <>
                    <span
                        style={{
                            background: badgeColor(data.signal),
                            padding: "2px 12px",
                            borderRadius: 4,
                            fontWeight: 600,
                            textTransform: "capitalize",
                        }}
                    >
                        {data.signal}
                    </span>
                    <span className="text-secondary ms-2">
                        confidence {Math.round(data.confidence * 100)}%
                    </span>

                    <table
                        className="table table-sm table-dark mt-2"
                        style={{ fontSize: "13px", maxWidth: 560 }}
                    >
                        <tbody>
                            <tr>
                                <td>Today's volume vs 20-day average</td>
                                <td>
                                    <strong>{d.relative_volume}×</strong>{" "}
                                    {d.volume_spike && (
                                        <span style={{ color: "#facc15" }}>(spike!)</span>
                                    )}
                                </td>
                            </tr>
                            <tr>
                                <td>Volume trend (recent participation)</td>
                                <td>{d.volume_trend}</td>
                            </tr>
                            <tr>
                                <td>OBV trend (money flow)</td>
                                <td>
                                    {d.obv_trend === "rising"
                                        ? "rising (accumulation)"
                                        : d.obv_trend === "falling"
                                        ? "falling (distribution)"
                                        : "flat"}
                                </td>
                            </tr>
                            <tr>
                                <td>Breakout confirmation</td>
                                <td>
                                    {d.breakout_confirmation
                                        ? `yes (${d.breakout_direction})`
                                        : "no"}
                                </td>
                            </tr>
                            <tr>
                                <td>Latest day change</td>
                                <td>{d.latest_change_pct}%</td>
                            </tr>
                        </tbody>
                    </table>

                    <p className="text-secondary" style={{ fontSize: "13px", maxWidth: 640 }}>
                        <strong>What this means:</strong> {buildExplanation(data)}
                    </p>

                    <button
                        type="button"
                        className="btn btn-sm btn-outline-secondary"
                        onClick={() => setShowCalc((s) => !s)}
                    >
                        {showCalc ? "▾ Hide calculation" : "▸ Show calculation"}
                    </button>

                    {showCalc && d.calc && (
                        <div
                            className="mt-2 p-3 rounded"
                            style={{
                                background: "#15181f",
                                fontFamily: "monospace",
                                fontSize: "12.5px",
                                lineHeight: 1.7,
                                maxWidth: 680,
                            }}
                        >
                            <div className="mb-2">
                                <strong>1. Relative volume</strong> = today's volume ÷ 20-day average
                                <br />= {fmt(d.calc.latest_volume)} ÷ {fmt(d.calc.baseline_20d)} ={" "}
                                <span style={{ color: "#facc15" }}>{d.relative_volume}×</span>
                                {"  "}(spike if ≥ {d.spike_threshold}× →{" "}
                                {d.volume_spike ? "yes" : "no"})
                            </div>

                            <div className="mb-2">
                                <strong>2. Volume trend</strong> = recent 10-day avg vs previous 10-day avg
                                <br />recent = {fmt(d.calc.recent_avg_10d)}, previous ={" "}
                                {fmt(d.calc.older_avg_10d)} →{" "}
                                <span style={{ color: "#4ea1ff" }}>{d.volume_trend}</span>
                            </div>

                            <div className="mb-2">
                                <strong>3. OBV trend (money flow)</strong> = OBV now vs OBV ~20 bars ago
                                <br />now = {fmt(d.calc.obv_now)}, past = {fmt(d.calc.obv_past)} →{" "}
                                <span style={{ color: "#4ea1ff" }}>{d.obv_trend}</span>
                            </div>

                            <div className="mb-2">
                                <strong>4. Breakout confirmation</strong> = volume spike AND |change| ≥ 1%
                                <br />spike = {d.volume_spike ? "yes" : "no"}, change ={" "}
                                {d.latest_change_pct}% →{" "}
                                <span style={{ color: "#4ea1ff" }}>
                                    {d.breakout_confirmation ? "yes" : "no"}
                                </span>
                            </div>

                            <div>
                                <strong>5. Confidence</strong> = min(relative_volume ÷ 3, 1) = min(
                                {d.relative_volume} ÷ 3, 1) ={" "}
                                <span style={{ color: "#facc15" }}>
                                    {Math.round(data.confidence * 100)}%
                                </span>
                            </div>
                        </div>
                    )}
                </>
            )}
        </div>
    );
};

export default VolumePanel;
