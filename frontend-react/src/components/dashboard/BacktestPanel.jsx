import { useEffect, useState } from "react";
import axiosInstance from "../../axiosInstance";
import TradeAuditTable from "./TradeAuditTable";
import ConditionAnalysis from "./ConditionAnalysis";

const PERIODS = ["1y", "2y", "3y", "5y", "max"];

/**
 * BacktestPanel — on-demand historical validation of the trade signal.
 * GET /api/v1/backtest/<ticker>/?period=&step=&max_holding=&min_history=
 *
 * Inputs are configurable so you can compare results across settings.
 */
const BacktestPanel = ({ ticker }) => {
    const [period, setPeriod] = useState("2y");
    const [step, setStep] = useState(5);
    const [maxHolding, setMaxHolding] = useState(20);
    const [minHistory, setMinHistory] = useState(150);
    const [minRr, setMinRr] = useState(0);
    const [minScore, setMinScore] = useState(0);
    const [targetMethod, setTargetMethod] = useState("A");

    const [data, setData] = useState(null);
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);

    // Clear stale results when the ticker changes.
    useEffect(() => {
        setData(null);
        setError("");
    }, [ticker]);

    const run = async () => {
        setLoading(true);
        setError("");
        setData(null);
        try {
            const res = await axiosInstance.get(
                `backtest/${encodeURIComponent(ticker)}/?period=${period}&step=${step}` +
                    `&max_holding=${maxHolding}&min_history=${minHistory}` +
                    `&min_rr=${minRr}&min_score=${minScore}&target_method=${targetMethod}`
            );
            setData(res.data.data);
        } catch (e) {
            setError(e.response?.data?.error || "Backtest failed.");
        } finally {
            setLoading(false);
        }
    };

    if (!ticker) return null;

    const numStyle = { width: 90 };

    return (
        <div className="text-light mt-4 p-3 rounded" style={{ background: "#15181f" }}>
            <h5 className="mb-2">Backtest / Validation {ticker ? `(${ticker})` : ""}</h5>

            {/* Configurable inputs */}
            <div className="d-flex flex-wrap align-items-end gap-3 mb-3">
                <div>
                    <label className="d-block text-secondary" style={{ fontSize: 12 }}>Period</label>
                    <select className="form-select form-select-sm" style={{ width: 100 }}
                            value={period} onChange={(e) => setPeriod(e.target.value)}>
                        {PERIODS.map((p) => <option key={p} value={p}>{p}</option>)}
                    </select>
                </div>
                <div>
                    <label className="d-block text-secondary" style={{ fontSize: 12 }}>
                        Step (days between tests)
                    </label>
                    <input type="number" className="form-control form-control-sm" style={numStyle}
                           value={step} min={1} max={30} onChange={(e) => setStep(e.target.value)} />
                </div>
                <div>
                    <label className="d-block text-secondary" style={{ fontSize: 12 }}>
                        Max holding (bars)
                    </label>
                    <input type="number" className="form-control form-control-sm" style={numStyle}
                           value={maxHolding} min={3} max={120}
                           onChange={(e) => setMaxHolding(e.target.value)} />
                </div>
                <div>
                    <label className="d-block text-secondary" style={{ fontSize: 12 }}>
                        Min history (bars)
                    </label>
                    <input type="number" className="form-control form-control-sm" style={numStyle}
                           value={minHistory} min={60} max={500}
                           onChange={(e) => setMinHistory(e.target.value)} />
                </div>
                <div>
                    <label className="d-block text-secondary" style={{ fontSize: 12 }}>
                        Min R:R (0 = off)
                    </label>
                    <input type="number" step="0.5" className="form-control form-control-sm" style={numStyle}
                           value={minRr} min={0} max={10}
                           onChange={(e) => setMinRr(e.target.value)} />
                </div>
                <div>
                    <label className="d-block text-secondary" style={{ fontSize: 12 }}>
                        Min score (0 = off)
                    </label>
                    <input type="number" step="1" className="form-control form-control-sm" style={numStyle}
                           value={minScore} min={0} max={100}
                           onChange={(e) => setMinScore(e.target.value)} />
                </div>
                <div>
                    <label className="d-block text-secondary" style={{ fontSize: 12 }}>
                        Target method
                    </label>
                    <select className="form-select form-select-sm" style={{ width: 200 }}
                            value={targetMethod} onChange={(e) => setTargetMethod(e.target.value)}>
                        <option value="A">A — nearest S/R level</option>
                        <option value="B">B — ATR-capped (2.5×)</option>
                    </select>
                </div>
                <button className="btn btn-info btn-sm" onClick={run} disabled={loading}>
                    {loading ? "Running…" : "Run Backtest"}
                </button>
            </div>

            {error && <div className="text-danger">{error}</div>}
            {data && data.note && <p className="text-secondary">{data.note}</p>}

            {data && data.trades > 0 && (
                <>
                    {/* Plain-English verdict */}
                    {data.verdict && (
                        <div
                            className="mb-3 p-2 rounded"
                            style={{
                                background: "#1c2230",
                                borderLeft: `4px solid ${
                                    data.verdict.rating === "Decent edge" ? "#26a69a" :
                                    data.verdict.rating === "Marginal edge" ? "#f0ad4e" : "#ef5350"
                                }`,
                            }}
                        >
                            {data.verdict.text}
                        </div>
                    )}

                    {/* Summary metrics */}
                    <div className="d-flex flex-wrap gap-4 mb-3">
                        {[
                            ["Trades", data.trades],
                            ["Win rate", `${data.win_rate}%`],
                            ["Profit factor", data.profit_factor ?? "—"],
                            ["Avg R / trade", data.avg_r],
                            ["Total R", data.total_r],
                            ["Max drawdown", `${data.max_drawdown_r}R`],
                        ].map(([k, v]) => (
                            <div key={k}>
                                <div className="text-secondary" style={{ fontSize: 12 }}>{k}</div>
                                <div style={{ fontSize: 20, fontWeight: 600 }}>{v}</div>
                            </div>
                        ))}
                    </div>

                    {/* Per-confluence-score breakdown — the key validation */}
                    <h6 className="mb-1">Performance by confluence score</h6>
                    <table className="table table-sm table-dark" style={{ fontSize: 13, maxWidth: 520 }}>
                        <thead>
                            <tr><th>Score band</th><th>Trades</th><th>Win rate</th><th>Avg R</th></tr>
                        </thead>
                        <tbody>
                            {Object.entries(data.by_score_band).map(([band, b]) => (
                                <tr key={band}>
                                    <td>{band}</td>
                                    <td>{b.trades}</td>
                                    <td>{b.win_rate}%</td>
                                    <td style={{ color: b.avg_r >= 0 ? "#26a69a" : "#ef5350" }}>
                                        {b.avg_r}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                    <p className="text-secondary" style={{ fontSize: 12, maxWidth: 620 }}>
                        If the system has an edge, <strong>higher score bands should show higher
                        win-rate / Avg R</strong> than lower ones. R-multiple = profit in units of
                        risk (a win to target = +R:R, a stop = −1R). Profit factor &gt; 1 = net
                        positive; max drawdown is the worst peak-to-trough in R.
                    </p>

                    {/* Target / Stop geometry diagnostics (is it targets or entries?) */}
                    {data.target_stop_diagnostics && (
                        <>
                            <h6 className="mb-1">Target / Stop diagnostics</h6>
                            <table className="table table-sm table-dark" style={{ fontSize: 13, maxWidth: 720 }}>
                                <thead>
                                    <tr>
                                        <th>Group</th><th>Trades</th>
                                        <th>Avg Tgt %</th><th>Avg Stop %</th>
                                        <th>Avg Tgt (ATR)</th><th>Avg Stop (ATR)</th><th>Avg R:R</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {[["all", "All"], ["win", "Wins"], ["loss", "Losses"], ["open", "Open"]].map(
                                        ([k, label]) => {
                                            const d = data.target_stop_diagnostics[k];
                                            if (!d) return null;
                                            return (
                                                <tr key={k}>
                                                    <td>{label}</td>
                                                    <td>{d.trades}</td>
                                                    <td>{d.avg_target_distance_pct}%</td>
                                                    <td>{d.avg_stop_distance_pct}%</td>
                                                    <td style={{ color: d.avg_target_atr > 4 ? "#ef5350" : "#26a69a" }}>
                                                        {d.avg_target_atr}
                                                    </td>
                                                    <td>{d.avg_stop_atr}</td>
                                                    <td>{d.avg_rr}</td>
                                                </tr>
                                            );
                                        }
                                    )}
                                </tbody>
                            </table>
                            <p className="text-secondary" style={{ fontSize: 12, maxWidth: 720 }}>
                                A target ≳ 4 ATR away is usually too far to reach in the holding window.
                                If <strong>Open</strong> and <strong>Loss</strong> rows show much larger
                                "Tgt (ATR)" than <strong>Wins</strong>, the targets are unrealistic; if
                                they're similar, the problem is entry quality, not targets.
                            </p>
                        </>
                    )}

                    {/* Condition-level analysis (which conditions made money) */}
                    {data.condition_analysis && <ConditionAnalysis analysis={data.condition_analysis} />}

                    {/* Full trade-by-trade audit trail */}
                    {data.all_trades && <TradeAuditTable trades={data.all_trades} />}
                </>
            )}
        </div>
    );
};

export default BacktestPanel;
