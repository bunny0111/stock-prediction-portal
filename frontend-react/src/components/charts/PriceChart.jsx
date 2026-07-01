import { useEffect, useRef, useState } from "react";
import {
    createChart,
    CandlestickSeries,
    HistogramSeries,
    LineSeries,
    CrosshairMode,
    LineStyle,
    createSeriesMarkers,
} from "lightweight-charts";
import axiosInstance from "../../axiosInstance";

/**
 * PriceChart
 * ----------
 * An INTERACTIVE candlestick chart (TradingView lightweight-charts).
 * Unlike the static PNG plots, you can hover anywhere to read the exact
 * date and OHLC values via the crosshair + tooltip box.
 *
 * It fetches its data from the new MarketDataService endpoint:
 *   GET /api/v1/market-data/<ticker>/?period=<period>&interval=1d
 *
 * Props:
 *   ticker         - stock symbol to display (e.g. "AAPL")
 *   predictedPrice - (optional) LSTM next-day close, drawn as a marker line
 */
const PERIODS = [
    { label: "1Y", value: "1y" },
    { label: "2Y", value: "2y" },
    { label: "5Y", value: "5y" },
    { label: "Max", value: "max" },
];

// Orange "key reaction zone" overlay — the level(s) price reacted to the most
// AND flipped between support/resistance the most (role reversals).
const SHOW_KEY_ZONES = true;

// Diagonal trendlines are hidden (subjective / unreliable). The trend
// direction/strength analysis still shows in the Trend panel, and the backend
// still computes the lines. Flip to true to draw them again.
const SHOW_TRENDLINES = false;

const PriceChart = ({ ticker, predictedPrice, asOf, setAsOf, period, setPeriod }) => {
    const containerRef = useRef();
    const tooltipRef = useRef();
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);
    const [sr, setSr] = useState(null);          // support/resistance details
    const [fullscreen, setFullscreen] = useState(false);
    // period + asOf are controlled by the Dashboard so all panels stay in sync.
    const [dateBounds, setDateBounds] = useState({ min: "", max: "" });

    // Let the user exit fullscreen with the ESC key.
    useEffect(() => {
        const onKey = (e) => {
            if (e.key === "Escape") setFullscreen(false);
        };
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, []);

    useEffect(() => {
        if (!ticker) return;

        let chart;
        let disposed = false;

        const build = async () => {
            setLoading(true);
            setError("");
            setSr(null);
            try {
                const res = await axiosInstance.get(
                    `market-data/${encodeURIComponent(ticker)}/?period=${period}&interval=1d`
                );
                if (disposed) return;
                const candles = res.data.data.candles;

                if (!disposed && candles.length) {
                    setDateBounds({
                        min: candles[0].date,
                        max: candles[candles.length - 1].date,
                    });
                }
                // Index of the as-of cutoff (last candle on/before the chosen date).
                let asOfIndex = -1;
                if (asOf) {
                    for (let i = 0; i < candles.length; i++) {
                        if (candles[i].date <= asOf) asOfIndex = i;
                        else break;
                    }
                }

                // Fetch support/resistance up front so the price axis can be
                // expanded to include those levels (otherwise a level far from
                // the recent candles would sit off-screen, like RELIANCE 1207).
                let det = null;
                try {
                    const srRes = await axiosInstance.get(
                        `support-resistance/${encodeURIComponent(ticker)}/?period=${period}&interval=1d` +
                            (asOf ? `&as_of=${asOf}` : "")
                    );
                    if (disposed) return;
                    det = srRes.data.data.details;
                } catch (srErr) {
                    // S/R is a bonus layer; ignore its failures.
                }

                // Fetch trend analysis (for the trendline overlay). Optional.
                let trend = null;
                try {
                    const tRes = await axiosInstance.get(
                        `trend/${encodeURIComponent(ticker)}/?period=${period}&interval=1d` +
                            (asOf ? `&as_of=${asOf}` : "")
                    );
                    if (disposed) return;
                    trend = tRes.data.data;
                } catch (tErr) {
                    // trend overlay is optional
                }

                // Fetch the calibrated next-day range forecast so its levels can
                // be drawn on the chart as tradeable bands. Optional/point-in-time.
                let rangeFc = null;
                try {
                    const rRes = await axiosInstance.get(
                        `range-forecast/${encodeURIComponent(ticker)}/?period=${period}&interval=1d` +
                            (asOf ? `&as_of=${asOf}` : "")
                    );
                    if (disposed) return;
                    rangeFc = rRes.data.data.details;
                } catch (rErr) {
                    // range overlay is optional
                }

                // Collect extra price levels (S/R + prediction) so the price
                // axis always includes them, not just the candle highs/lows.
                const extraLevels = [];
                if (det) {
                    (det.support || []).forEach((z) => extraLevels.push(z.level));
                    (det.resistance || []).forEach((z) => extraLevels.push(z.level));
                }
                // Predicted line is "today's" forecast — hide it during a
                // historical as-of review (it isn't relevant to a past date).
                if (!asOf && predictedPrice !== undefined && predictedPrice !== null) {
                    extraLevels.push(predictedPrice);
                }
                if (SHOW_KEY_ZONES && det && det.key_zones) {
                    det.key_zones.forEach((z) => extraLevels.push(z.low, z.high));
                }
                if (rangeFc && !rangeFc.error) {
                    if (rangeFc.expected_high) extraLevels.push(rangeFc.expected_high);
                    if (rangeFc.expected_low) extraLevels.push(rangeFc.expected_low);
                    const r90 = rangeFc.ranges && rangeFc.ranges["90"];
                    if (r90) extraLevels.push(r90.low, r90.high);
                }
                if (SHOW_TRENDLINES && trend && trend.viz && Array.isArray(trend.viz.trendlines)) {
                    trend.viz.trendlines.forEach((tl) =>
                        (tl.points || []).forEach((pt) => extraLevels.push(pt.price))
                    );
                }

                // 1. Create the chart inside our container div.
                chart = createChart(containerRef.current, {
                    autoSize: true,
                    layout: { background: { color: "#1e222d" }, textColor: "#d1d4dc" },
                    grid: {
                        vertLines: { color: "#2a2e39" },
                        horzLines: { color: "#2a2e39" },
                    },
                    crosshair: { mode: CrosshairMode.Normal },
                    rightPriceScale: { borderColor: "#2a2e39" },
                    timeScale: {
                        borderColor: "#2a2e39",
                        timeVisible: false,
                        rightOffset: 5,        // leave whitespace on the right edge
                    },
                    // Explicitly enable TradingView-style drag/zoom interactions.
                    handleScroll: {
                        mouseWheel: true,
                        pressedMouseMove: true,   // click + drag to pan
                        horzTouchDrag: true,
                        vertTouchDrag: true,
                    },
                    handleScale: {
                        mouseWheel: true,         // wheel to zoom
                        pinch: true,
                        axisPressedMouseMove: true,
                        axisDoubleClickReset: true,
                    },
                });

                // 2. Candlestick series (price).
                const candleSeries = chart.addSeries(CandlestickSeries, {
                    upColor: "#26a69a",
                    downColor: "#ef5350",
                    borderVisible: false,
                    wickUpColor: "#26a69a",
                    wickDownColor: "#ef5350",
                    // Expand the price axis to include S/R + predicted levels so
                    // they are always visible, even when far from recent candles.
                    autoscaleInfoProvider: (original) => {
                        const r = original();
                        if (!r || !r.priceRange || extraLevels.length === 0) return r;
                        r.priceRange.minValue = Math.min(r.priceRange.minValue, ...extraLevels);
                        r.priceRange.maxValue = Math.max(r.priceRange.maxValue, ...extraLevels);
                        return r;
                    },
                });
                candleSeries.setData(
                    candles.map((c) => ({
                        time: c.date,
                        open: c.open,
                        high: c.high,
                        low: c.low,
                        close: c.close,
                    }))
                );

                // 2b. Mark the LSTM predicted next-day close as a horizontal line
                // (skipped during a historical as-of review).
                if (!asOf && predictedPrice !== undefined && predictedPrice !== null) {
                    candleSeries.createPriceLine({
                        price: predictedPrice,
                        color: "#facc15",
                        lineWidth: 2,
                        lineStyle: LineStyle.Dashed,
                        axisLabelVisible: true,
                        title: `Predicted ${predictedPrice}`,
                    });
                }

                // 2b-ii. Calibrated next-day range forecast — blue band you can
                // trade against: solid = expected high/low (±1 ATR reach),
                // dashed = the 90% expected range edges.
                if (rangeFc && !rangeFc.error) {
                    const fc = "#42a5f5";
                    const r90 = rangeFc.ranges && rangeFc.ranges["90"];
                    if (r90) {
                        candleSeries.createPriceLine({
                            price: r90.high, color: fc, lineWidth: 1, lineStyle: LineStyle.Dashed,
                            axisLabelVisible: true, title: `90% ${r90.high}`,
                        });
                        candleSeries.createPriceLine({
                            price: r90.low, color: fc, lineWidth: 1, lineStyle: LineStyle.Dashed,
                            axisLabelVisible: true, title: `90% ${r90.low}`,
                        });
                    }
                    if (rangeFc.expected_high) {
                        candleSeries.createPriceLine({
                            price: rangeFc.expected_high, color: fc, lineWidth: 2, lineStyle: LineStyle.Solid,
                            axisLabelVisible: true, title: `Exp High ${rangeFc.expected_high}`,
                        });
                    }
                    if (rangeFc.expected_low) {
                        candleSeries.createPriceLine({
                            price: rangeFc.expected_low, color: fc, lineWidth: 2, lineStyle: LineStyle.Solid,
                            axisLabelVisible: true, title: `Exp Low ${rangeFc.expected_low}`,
                        });
                    }
                }

                // 2c. Trendline overlays — hidden via SHOW_TRENDLINES (subjective).
                // Backend still computes them; the Trend panel still shows direction.
                if (SHOW_TRENDLINES && trend && trend.viz && Array.isArray(trend.viz.trendlines)) {
                    trend.viz.trendlines.forEach((tl) => {
                        if (!tl.points || tl.points.length !== 2) return;
                        const tlSeries = chart.addSeries(LineSeries, {
                            color: tl.type === "resistance" ? "#ab47bc" : "#26c6da",
                            lineWidth: 2,
                            priceLineVisible: false,
                            lastValueVisible: false,
                            crosshairMarkerVisible: false,
                        });
                        tlSeries.setData(
                            tl.points.map((pt) => ({ time: pt.date, value: pt.price }))
                        );
                    });
                }

                // 3. Volume as a histogram on a separate, bottom scale.
                const volumeSeries = chart.addSeries(HistogramSeries, {
                    priceFormat: { type: "volume" },
                    priceScaleId: "vol",
                });
                chart.priceScale("vol").applyOptions({
                    scaleMargins: { top: 0.8, bottom: 0 },
                });
                volumeSeries.setData(
                    candles.map((c) => ({
                        time: c.date,
                        value: c.volume,
                        color: c.close >= c.open ? "#26a69a66" : "#ef535066",
                    }))
                );

                // Show a recent slice (last ~130 bars) instead of cramming all
                // data into view, so older history sits off-screen to the left
                // and you can click-drag right to scroll back through it.
                const total = candles.length;
                if (asOf && asOfIndex >= 0) {
                    // Centre the view on the cutoff: show ~80 bars before it and
                    // everything after, so you can review how the levels held.
                    chart.timeScale().setVisibleLogicalRange({
                        from: Math.max(0, asOfIndex - 80),
                        to: total + 5,
                    });
                } else if (total > 130) {
                    chart.timeScale().setVisibleLogicalRange({
                        from: total - 130,
                        to: total + 5,
                    });
                } else {
                    chart.timeScale().fitContent();
                }

                // 4. Hover tooltip showing date + OHLC for the bar under the cursor.
                chart.subscribeCrosshairMove((param) => {
                    const tip = tooltipRef.current;
                    if (!tip) return;
                    if (!param.time || !param.point) {
                        tip.style.display = "none";
                        return;
                    }
                    const bar = param.seriesData.get(candleSeries);
                    if (!bar) {
                        tip.style.display = "none";
                        return;
                    }
                    tip.style.display = "block";
                    tip.style.left = param.point.x + 15 + "px";
                    tip.style.top = param.point.y + 15 + "px";
                    tip.innerHTML = `
                        <div style="font-weight:600;margin-bottom:4px">${param.time}</div>
                        <div>O: ${bar.open}</div>
                        <div>H: ${bar.high}</div>
                        <div>L: ${bar.low}</div>
                        <div>C: ${bar.close}</div>
                    `;
                });

                // 5. Draw the support & resistance lines (already fetched above).
                if (det) {
                    // Skip any S/R line that falls inside an orange key-zone band —
                    // the band already marks that area, so this avoids overlap.
                    const inKeyZone = (price) =>
                        SHOW_KEY_ZONES &&
                        (det.key_zones || []).some((z) => price >= z.low && price <= z.high);

                    (det.resistance || []).forEach((z) => {
                        if (inKeyZone(z.level)) return;
                        candleSeries.createPriceLine({
                            price: z.level,
                            color: "#ef5350",       // red = ceiling
                            lineWidth: 1,
                            lineStyle: LineStyle.Dotted,
                            axisLabelVisible: true,
                            title: `R ${z.level} (${z.touches}x)`,
                        });
                    });
                    (det.support || []).forEach((z) => {
                        if (inKeyZone(z.level)) return;
                        candleSeries.createPriceLine({
                            price: z.level,
                            color: "#26a69a",       // green = floor
                            lineWidth: 1,
                            lineStyle: LineStyle.Dotted,
                            axisLabelVisible: true,
                            title: `S ${z.level} (${z.touches}x)`,
                        });
                    });

                    // Key reaction zones — an orange band (center line + faint edges).
                    // Hidden for now via SHOW_KEY_ZONES; backend still computes them.
                    if (SHOW_KEY_ZONES) {
                        (det.key_zones || []).forEach((z) => {
                            // Bold line at the STRONGEST reaction level (where inside
                            // the zone price reacted most), not just the geometric center.
                            candleSeries.createPriceLine({
                                price: z.strongest_level,
                                color: "#ff9800",
                                lineWidth: 2,
                                lineStyle: LineStyle.Solid,
                                axisLabelVisible: true,
                                title: `KEY ${z.strongest_level} (${z.touches}x ↕)`,
                            });
                            candleSeries.createPriceLine({
                                price: z.high, color: "#ff980077", lineWidth: 1,
                                lineStyle: LineStyle.Dotted, axisLabelVisible: false,
                            });
                            candleSeries.createPriceLine({
                                price: z.low, color: "#ff980077", lineWidth: 1,
                                lineStyle: LineStyle.Dotted, axisLabelVisible: false,
                            });
                        });
                    }

                    // Mark EVERY individual touch with a dot so they're easy to find:
                    // red above the bar for resistance touches, green below for support.
                    const markers = [];
                    (det.resistance || []).forEach((z) =>
                        (z.touch_points || []).forEach((t) =>
                            markers.push({ time: t.date, position: "aboveBar", color: "#ef5350", shape: "circle" })
                        )
                    );
                    (det.support || []).forEach((z) =>
                        (z.touch_points || []).forEach((t) =>
                            markers.push({ time: t.date, position: "belowBar", color: "#26a69a", shape: "circle" })
                        )
                    );
                    // Mark the as-of cutoff so it's clear which candles came AFTER
                    // the levels were computed (the ones you use to verify).
                    if (asOf && asOfIndex >= 0) {
                        markers.push({
                            time: candles[asOfIndex].date,
                            position: "aboveBar",
                            color: "#ffffff",
                            shape: "arrowDown",
                            text: "as-of",
                        });
                    }
                    markers.sort((a, b) => (a.time < b.time ? -1 : a.time > b.time ? 1 : 0));
                    if (markers.length) createSeriesMarkers(candleSeries, markers);

                    setSr(det);
                }
            } catch (err) {
                if (!disposed) {
                    setError(
                        err.response?.data?.error || "Could not load chart data."
                    );
                }
            } finally {
                if (!disposed) setLoading(false);
            }
        };

        build();

        // Cleanup when ticker/period/prediction changes or component unmounts.
        return () => {
            disposed = true;
            if (chart) chart.remove();
        };
    }, [ticker, period, predictedPrice, asOf]);

    return (
        <div
            className="mb-4"
            style={
                fullscreen
                    ? {
                          position: "fixed",
                          inset: 0,
                          zIndex: 1050,
                          background: "#1e222d",
                          padding: "16px",
                          overflow: "auto",
                      }
                    : undefined
            }
        >
            <div className="d-flex justify-content-between align-items-center mb-2">
                <h5 className="text-light mb-0">
                    Interactive Price Chart {ticker ? `(${ticker})` : ""}
                </h5>
                <div className="d-flex align-items-center gap-2">
                    <div className="btn-group btn-group-sm">
                        {PERIODS.map((p) => (
                            <button
                                key={p.value}
                                type="button"
                                className={
                                    "btn " +
                                    (period === p.value ? "btn-info" : "btn-outline-info")
                                }
                                onClick={() => setPeriod(p.value)}
                            >
                                {p.label}
                            </button>
                        ))}
                    </div>
                    <input
                        type="date"
                        className="form-control form-control-sm"
                        style={{ width: 160 }}
                        value={asOf}
                        min={dateBounds.min}
                        max={dateBounds.max}
                        onChange={(e) => setAsOf(e.target.value)}
                        title="Show support/resistance as of this date"
                    />
                    {asOf && (
                        <button
                            type="button"
                            className="btn btn-sm btn-outline-light"
                            onClick={() => setAsOf("")}
                        >
                            Clear date
                        </button>
                    )}
                    <button
                        type="button"
                        className="btn btn-sm btn-outline-light"
                        onClick={() => setFullscreen((f) => !f)}
                        title={fullscreen ? "Exit fullscreen (Esc)" : "Open fullscreen"}
                    >
                        {fullscreen ? "✕ Close" : "⤢ Fullscreen"}
                    </button>
                </div>
            </div>
            {loading && <p className="text-light">Loading chart…</p>}
            {error && <div className="text-danger">{error}</div>}
            <div style={{ position: "relative" }}>
                <div
                    ref={containerRef}
                    style={{
                        height: fullscreen ? "calc(100vh - 160px)" : 480,
                        width: "100%",
                    }}
                />
                <div
                    ref={tooltipRef}
                    style={{
                        position: "absolute",
                        display: "none",
                        padding: "6px 8px",
                        boxSizing: "border-box",
                        fontSize: "12px",
                        color: "#fff",
                        background: "rgba(0,0,0,0.8)",
                        borderRadius: "4px",
                        pointerEvents: "none",
                        zIndex: 10,
                    }}
                />
            </div>
            <small className="text-secondary">
                Hover over the chart to see the date and price (O/H/L/C). The{" "}
                <span style={{ color: "#42a5f5" }}>blue lines</span> are the next-day forecast levels —
                solid = expected high/low, dashed = the 90% expected range.
                {predictedPrice !== undefined && predictedPrice !== null && (
                    <> The dashed yellow line marks the LSTM predicted next-day close.</>
                )}
            </small>

            {/* Why these support / resistance levels were marked */}
            {sr && (sr.support?.length > 0 || sr.resistance?.length > 0) && (
                <div className="mt-3 text-light">
                    {SHOW_KEY_ZONES && sr.key_zones?.length > 0 && (
                        <div className="mb-3">
                            <strong style={{ color: "#ff9800" }}>
                                Key Reaction Zone{sr.key_zones.length > 1 ? "s" : ""} (orange band)
                            </strong>
                            <div className="d-flex flex-wrap gap-3 mt-2">
                                {sr.key_zones.map((z, i) => {
                                    const row = (label, value, color) => (
                                        <tr>
                                            <td className="text-secondary pe-3">{label}</td>
                                            <td style={{ color, fontWeight: color ? 600 : 400 }}>{value}</td>
                                        </tr>
                                    );
                                    return (
                                        <div
                                            key={i}
                                            className="p-2 rounded"
                                            style={{ background: "#2a2310", border: "1px solid #ff980055", minWidth: 250 }}
                                        >
                                            <table style={{ fontSize: 13 }}>
                                                <tbody>
                                                    {row("Zone", `${z.low} – ${z.high}`)}
                                                    {row("Center", z.center)}
                                                    {row("Zone Width", z.width)}
                                                    {row("Support Touches", z.lows, "#26a69a")}
                                                    {row("Resistance Touches", z.highs, "#ef5350")}
                                                    {row("Role Flips", z.role_reversals)}
                                                    {row("Strongest Reaction", z.strongest_level, "#ff9800")}
                                                    {row("Strength", `${Math.round(z.strength * 100)}/100`)}
                                                </tbody>
                                            </table>
                                        </div>
                                    );
                                })}
                            </div>
                            <div className="text-secondary" style={{ fontSize: "12px", marginTop: 6 }}>
                                The bold orange line is the <strong>strongest reaction level</strong> —
                                where inside the zone price reacted most. The faint band edges show the
                                zone's full width.
                            </div>
                        </div>
                    )}
                    <h6 className="mb-1">Why these support / resistance levels?</h6>
                    <p className="text-secondary" style={{ fontSize: "13px", marginBottom: "8px" }}>
                        Each level is marked where price <strong>reversed multiple times</strong> — every
                        reversal counts as a “touch”. A level with more touches, and more recent touches,
                        is stronger. Each individual touch is marked with a coloured dot on the chart
                        (green below the bar = support touch, red above = resistance touch).
                        Levels <span style={{ color: "#ef5350" }}>above</span> the current
                        price act as <span style={{ color: "#ef5350" }}>resistance</span> (ceilings);
                        levels <span style={{ color: "#26a69a" }}>below</span> act as{" "}
                        <span style={{ color: "#26a69a" }}>support</span> (floors).
                    </p>
                    <table className="table table-sm table-dark align-middle" style={{ fontSize: "13px" }}>
                        <thead>
                            <tr>
                                <th>Type</th>
                                <th>Level</th>
                                <th>Touches</th>
                                <th>Touch dates</th>
                                <th>Distance</th>
                                <th>Strength</th>
                            </tr>
                        </thead>
                        <tbody>
                            {sr.resistance.map((z, i) => (
                                <tr key={"r" + i}>
                                    <td style={{ color: "#ef5350" }}>Resistance</td>
                                    <td>{z.level}</td>
                                    <td>{z.touches}</td>
                                    <td style={{ fontSize: "12px" }}>
                                        {(z.touch_points || []).map((t) => t.date).join(", ")}
                                    </td>
                                    <td>{z.distance_pct}%</td>
                                    <td>{Math.round(z.strength * 100)}%</td>
                                </tr>
                            ))}
                            {sr.support.map((z, i) => (
                                <tr key={"s" + i}>
                                    <td style={{ color: "#26a69a" }}>Support</td>
                                    <td>{z.level}</td>
                                    <td>{z.touches}</td>
                                    <td style={{ fontSize: "12px" }}>
                                        {(z.touch_points || []).map((t) => t.date).join(", ")}
                                    </td>
                                    <td>{z.distance_pct}%</td>
                                    <td>{Math.round(z.strength * 100)}%</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
};

export default PriceChart;
