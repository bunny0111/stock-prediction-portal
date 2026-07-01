const DIMENSIONS = [
    ["by_confluence_band", "Confluence Score", ["0-20", "21-40", "41-60", "61-80", "81-100"]],
    ["by_trend_strength", "Trend Strength", ["weak", "moderate", "strong"]],
    ["by_relative_volume", "Relative Volume", ["<0.7", "0.7-1.0", "1.0-1.5", "1.5-2.0", "2.0+"]],
    ["by_sr_strength", "S/R Strength (entry level)", ["0-50", "51-70", "71-85", "86-100"]],
    ["by_distance_to_support", "Distance to Support", ["0-1%", "1-3%", "3-5%", "5%+"]],
    ["by_distance_to_resistance", "Distance to Resistance", ["0-1%", "1-3%", "3-5%", "5%+"]],
    ["by_role_flips", "Role-Flip Count", ["0", "1", "2", "3+"]],
    ["by_holding_period", "Holding Period", ["1-3d", "4-7d", "8-14d", "15+d"]],
];

const pfColor = (pf) => (pf == null ? "#d1d4dc" : pf >= 1.2 ? "#26a69a" : pf < 1 ? "#ef5350" : "#f0ad4e");

const GroupTable = ({ title, data, order }) => {
    const keys = order.filter((k) => data[k]);
    Object.keys(data).forEach((k) => { if (!keys.includes(k)) keys.push(k); });
    if (keys.length === 0) return null;
    return (
        <div style={{ minWidth: 320 }}>
            <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4 }}>{title}</div>
            <table className="table table-sm table-dark" style={{ fontSize: 12 }}>
                <thead>
                    <tr>
                        <th>Band</th><th>n</th><th>Win%</th><th>Ret%</th><th>Avg R</th><th>PF</th><th>Tot R</th>
                    </tr>
                </thead>
                <tbody>
                    {keys.map((k) => {
                        const d = data[k];
                        return (
                            <tr key={k}>
                                <td>{k}</td>
                                <td>{d.trades}</td>
                                <td>{d.win_rate}%</td>
                                <td>{d.avg_return_pct}%</td>
                                <td style={{ color: d.avg_r >= 0 ? "#26a69a" : "#ef5350" }}>{d.avg_r}</td>
                                <td style={{ color: pfColor(d.profit_factor) }}>{d.profit_factor ?? "—"}</td>
                                <td style={{ color: d.total_r >= 0 ? "#26a69a" : "#ef5350" }}>{d.total_r}</td>
                            </tr>
                        );
                    })}
                </tbody>
            </table>
        </div>
    );
};

/** ConditionAnalysis — winners-vs-losers stats grouped by market condition. */
const ConditionAnalysis = ({ analysis }) => {
    if (!analysis) return null;
    return (
        <div className="mt-3">
            <h6 className="mb-1">Condition Analysis (which conditions made money)</h6>
            <p className="text-secondary" style={{ fontSize: 12, maxWidth: 720 }}>
                For a real edge, a condition should show <strong>higher Win% / PF / Total R</strong> in
                its "good" bands. <span style={{ color: "#26a69a" }}>Green PF ≥ 1.2</span> ·{" "}
                <span style={{ color: "#f0ad4e" }}>amber 1.0–1.2</span> ·{" "}
                <span style={{ color: "#ef5350" }}>red &lt; 1.0 (losing)</span>. Small samples per band are noisy.
            </p>
            <div className="d-flex flex-wrap gap-4">
                {DIMENSIONS.map(([key, title, order]) => (
                    <GroupTable key={key} title={title} data={analysis[key] || {}} order={order} />
                ))}
            </div>
        </div>
    );
};

export default ConditionAnalysis;
