import { useMemo, useState, Fragment } from "react";

const FLAT_COLS = [
    "id", "ticker", "entry_date", "exit_date", "trade_type", "side",
    "entry_price", "exit_price", "stop_loss", "target", "holding_period",
    "outcome", "return_pct", "r_multiple",
    "atr", "target_distance_pct", "stop_distance_pct", "target_atr", "stop_atr", "risk_reward",
    "confluence_score", "trend_signal", "trend_strength", "volume_signal",
    "relative_volume", "trigger",
];

function toCSV(trades) {
    const esc = (v) => {
        if (v === null || v === undefined) v = "";
        v = String(v).replace(/"/g, '""');
        return /[",\n]/.test(v) ? `"${v}"` : v;
    };
    const lines = [FLAT_COLS.join(",")];
    trades.forEach((t) => lines.push(FLAT_COLS.map((c) => esc(t[c])).join(",")));
    return lines.join("\n");
}

const outcomeColor = (o) =>
    o === "win" ? "#26a69a" : o === "loss" ? "#ef5350" : "#f0ad4e";

/**
 * TradeAuditTable — every backtested trade with its market-condition snapshot.
 * Filterable, searchable, expandable (S/R snapshot), and CSV-exportable.
 */
const TradeAuditTable = ({ trades }) => {
    const [search, setSearch] = useState("");
    const [outcome, setOutcome] = useState("all");
    const [side, setSide] = useState("all");
    const [expanded, setExpanded] = useState(null);

    const filtered = useMemo(() => {
        const q = search.trim().toLowerCase();
        return trades.filter(
            (t) =>
                (outcome === "all" || t.outcome === outcome) &&
                (side === "all" || t.side === side) &&
                (q === "" ||
                    `${t.trigger} ${t.entry_date} ${t.ticker}`.toLowerCase().includes(q))
        );
    }, [trades, search, outcome, side]);

    const exportCSV = () => {
        const blob = new Blob([toCSV(filtered)], { type: "text/csv" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `backtest_${trades[0]?.ticker || "trades"}.csv`;
        a.click();
        URL.revokeObjectURL(url);
    };

    const cell = { padding: "3px 6px", whiteSpace: "nowrap" };

    return (
        <div className="mt-3">
            <h6 className="mb-2">Trade Audit Trail ({filtered.length} of {trades.length})</h6>

            {/* Filters + export */}
            <div className="d-flex flex-wrap align-items-center gap-2 mb-2">
                <input
                    className="form-control form-control-sm"
                    style={{ width: 240 }}
                    placeholder="Search trigger / date…"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                />
                <select className="form-select form-select-sm" style={{ width: 120 }}
                        value={outcome} onChange={(e) => setOutcome(e.target.value)}>
                    <option value="all">All outcomes</option>
                    <option value="win">Win</option>
                    <option value="loss">Loss</option>
                    <option value="open">Open</option>
                </select>
                <select className="form-select form-select-sm" style={{ width: 110 }}
                        value={side} onChange={(e) => setSide(e.target.value)}>
                    <option value="all">All sides</option>
                    <option value="long">Long</option>
                    <option value="short">Short</option>
                </select>
                <button className="btn btn-sm btn-outline-info" onClick={exportCSV}>
                    ⤓ Export CSV
                </button>
            </div>

            <div style={{ overflowX: "auto" }}>
                <table className="table table-sm table-dark align-middle" style={{ fontSize: 12 }}>
                    <thead>
                        <tr>
                            <th style={cell}></th>
                            <th style={cell}>ID</th>
                            <th style={cell}>Entry</th>
                            <th style={cell}>Exit</th>
                            <th style={cell}>Type</th>
                            <th style={cell}>Side</th>
                            <th style={cell}>Entry₹</th>
                            <th style={cell}>Exit₹</th>
                            <th style={cell}>Stop</th>
                            <th style={cell}>Target</th>
                            <th style={cell}>Hold</th>
                            <th style={cell}>Outcome</th>
                            <th style={cell}>Ret%</th>
                            <th style={cell}>Tgt%</th>
                            <th style={cell}>Stop%</th>
                            <th style={cell}>R:R</th>
                            <th style={cell}>ATR</th>
                            <th style={cell}>Tgt-ATR</th>
                            <th style={cell}>Stop-ATR</th>
                            <th style={cell}>Score</th>
                            <th style={cell}>Trend</th>
                            <th style={cell}>RelVol</th>
                        </tr>
                    </thead>
                    <tbody>
                        {filtered.map((t) => (
                            <Fragment key={t.id}>
                                <tr style={{ cursor: "pointer" }}
                                    onClick={() => setExpanded(expanded === t.id ? null : t.id)}>
                                    <td style={cell}>{expanded === t.id ? "▾" : "▸"}</td>
                                    <td style={cell}>{t.id}</td>
                                    <td style={cell}>{t.entry_date}</td>
                                    <td style={cell}>{t.exit_date}</td>
                                    <td style={cell}>{t.trade_type}</td>
                                    <td style={{ ...cell, textTransform: "capitalize" }}>{t.side}</td>
                                    <td style={cell}>{t.entry_price}</td>
                                    <td style={cell}>{t.exit_price}</td>
                                    <td style={cell}>{t.stop_loss}</td>
                                    <td style={cell}>{t.target}</td>
                                    <td style={cell}>{t.holding_period}d</td>
                                    <td style={{ ...cell, color: outcomeColor(t.outcome) }}>{t.outcome}</td>
                                    <td style={{ ...cell, color: t.return_pct >= 0 ? "#26a69a" : "#ef5350" }}>
                                        {t.return_pct}%
                                    </td>
                                    <td style={cell}>{t.target_distance_pct}%</td>
                                    <td style={cell}>{t.stop_distance_pct}%</td>
                                    <td style={cell}>{t.risk_reward}</td>
                                    <td style={cell}>{t.atr}</td>
                                    <td style={{ ...cell, color: t.target_atr > 4 ? "#ef5350" : "#d1d4dc" }}>
                                        {t.target_atr}
                                    </td>
                                    <td style={cell}>{t.stop_atr}</td>
                                    <td style={cell}>{t.confluence_score}</td>
                                    <td style={cell}>{t.trend_signal}</td>
                                    <td style={cell}>{t.relative_volume}×</td>
                                </tr>
                                {expanded === t.id && (
                                    <tr>
                                        <td colSpan={22} style={{ background: "#15181f", padding: 12 }}>
                                            <div className="mb-2">
                                                <strong>Trigger:</strong> {t.trigger}
                                            </div>
                                            <div className="d-flex flex-wrap gap-4">
                                                <Snapshot title="Support (snapshot at entry)" rows={t.support}
                                                          cols={["level", "touches", "strength", "distance_pct"]} color="#26a69a" />
                                                <Snapshot title="Resistance (snapshot at entry)" rows={t.resistance}
                                                          cols={["level", "touches", "strength", "distance_pct"]} color="#ef5350" />
                                                {t.key_zones?.length > 0 && (
                                                    <Snapshot title="Key Zones" rows={t.key_zones}
                                                              cols={["center", "low", "high", "touches", "role_reversals", "strength", "distance_pct"]} color="#ff9800" />
                                                )}
                                            </div>
                                            <div className="text-secondary mt-2" style={{ fontSize: 12 }}>
                                                Volume: {t.volume_signal} ({t.relative_volume}× avg) · Trend:{" "}
                                                {t.trend_signal} ({t.trend_strength}) · Confluence: {t.confluence_score}/100
                                            </div>
                                        </td>
                                    </tr>
                                )}
                            </Fragment>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

const Snapshot = ({ title, rows, cols, color }) => (
    <div>
        <div style={{ color, fontWeight: 600, fontSize: 12, marginBottom: 4 }}>{title}</div>
        {rows.length === 0 ? (
            <div className="text-secondary" style={{ fontSize: 12 }}>none</div>
        ) : (
            <table className="table table-sm table-dark" style={{ fontSize: 11 }}>
                <thead>
                    <tr>{cols.map((c) => <th key={c} style={{ padding: "2px 6px" }}>{c}</th>)}</tr>
                </thead>
                <tbody>
                    {rows.map((r, i) => (
                        <tr key={i}>
                            {cols.map((c) => (
                                <td key={c} style={{ padding: "2px 6px" }}>
                                    {c === "distance_pct" ? `${r[c]}%` : c === "strength" ? `${r[c]}/100` : r[c]}
                                </td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            </table>
        )}
    </div>
);

export default TradeAuditTable;
