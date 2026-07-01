import { useEffect, useState } from "react";
import axiosInstance from "../../axiosInstance";

/**
 * NewsPanel — recent company news from yfinance (display-only, no AI).
 * GET /api/v1/news/<ticker>/
 */
const NewsPanel = ({ ticker }) => {
    const [items, setItems] = useState(null);
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (!ticker) return;
        let active = true;
        (async () => {
            setLoading(true);
            setError("");
            setItems(null);
            try {
                const res = await axiosInstance.get(`news/${encodeURIComponent(ticker)}/`);
                if (active) setItems(res.data.data.items);
            } catch (e) {
                if (active) setError(e.response?.data?.error || "Could not load news.");
            } finally {
                if (active) setLoading(false);
            }
        })();
        return () => {
            active = false;
        };
    }, [ticker]);

    if (!ticker) return null;

    return (
        <div className="text-light mt-4">
            <h5 className="mb-2">News {ticker ? `(${ticker})` : ""}</h5>
            {loading && <p>Loading news…</p>}
            {error && <div className="text-danger">{error}</div>}
            {items && items.length === 0 && (
                <p className="text-secondary">No recent news found for this ticker.</p>
            )}

            {items && items.length > 0 && (
                <div className="d-flex flex-column gap-3" style={{ maxWidth: 760 }}>
                    {items.map((n, i) => (
                        <div
                            key={i}
                            className="d-flex gap-3 p-2 rounded"
                            style={{ background: "#15181f" }}
                        >
                            {n.thumbnail && (
                                <img
                                    src={n.thumbnail}
                                    alt=""
                                    style={{ width: 96, height: 64, objectFit: "cover", borderRadius: 4 }}
                                    onError={(e) => { e.target.style.display = "none"; }}
                                />
                            )}
                            <div>
                                <a
                                    href={n.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    style={{ color: "#4ea1ff", fontWeight: 600, textDecoration: "none" }}
                                >
                                    {n.title}
                                </a>
                                <div className="text-secondary" style={{ fontSize: 12 }}>
                                    {n.publisher}
                                    {n.published ? ` · ${n.published}` : ""}
                                </div>
                                {n.summary && (
                                    <div className="text-secondary" style={{ fontSize: 13, marginTop: 4 }}>
                                        {n.summary.length > 180
                                            ? n.summary.slice(0, 180) + "…"
                                            : n.summary}
                                    </div>
                                )}
                            </div>
                        </div>
                    ))}
                </div>
            )}
            <small className="text-secondary d-block mt-2">
                News from Yahoo Finance, for context only.
            </small>
        </div>
    );
};

export default NewsPanel;
