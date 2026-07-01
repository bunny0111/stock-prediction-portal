import {useEffect, useState, useRef} from "react";
import axios from "axios"
import axiosInstance from "../../axiosInstance"
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faSpinner } from '@fortawesome/free-solid-svg-icons'
import PriceChart from "../charts/PriceChart"
import RangeForecastPanel from "./RangeForecastPanel"
import BacktestPanel from "./BacktestPanel"
import NewsPanel from "./NewsPanel"

const Dashboard = () => {
    const [ticker, setTicker] = useState('');
    const [error, setError] = useState();
    const [loading, setLoading] = useState(false)
    const [plot, setPlot] = useState()
    const [ma100, setMA100] = useState()
    const [ma200, setMA200] = useState()
    const [prediction, setPrediction] = useState()
    const [mse, setMSE] = useState()
    const [rmse, setRMSE] = useState()
    const [r2, setR2] = useState()
    const [nextDay, setNextDay] = useState()
    const [lastClose, setLastClose] = useState()
    const [lastDate, setLastDate] = useState()
    const [chartTicker, setChartTicker] = useState()
    // Shared across the chart AND all analysis panels so an as-of date / period
    // change updates every panel point-in-time, not just the chart.
    const [asOf, setAsOf] = useState("")
    const [period, setPeriod] = useState("2y")
    // Ticker autocomplete (Indian stocks only)
    const [suggestions, setSuggestions] = useState([])
    const [showSug, setShowSug] = useState(false)
    const searchTimer = useRef()

    const fetchSuggestions = (q) => {
        clearTimeout(searchTimer.current)
        if (!q || q.trim().length < 1) { setSuggestions([]); setShowSug(false); return }
        searchTimer.current = setTimeout(async () => {
            try {
                const res = await axiosInstance.get(`search/?q=${encodeURIComponent(q)}`)
                setSuggestions(res.data.data || [])
                setShowSug(true)
            } catch { setSuggestions([]) }
        }, 250)
    }


    useEffect(() => {
        const fetchProtectedData = async () => {
            try{
                const response = await axiosInstance.get('/protected-view/');
                
            }catch(error){
                console.error('Error fetching data:', error)
            }
        }
        fetchProtectedData();
    }, [])

    const handleSubmit = async (e) => {
        e.preventDefault();
        setLoading(true)
        setError('')  // clear any previous error before a new attempt
        try{
            const response = await axiosInstance.post('/predict/', {
                ticker: ticker
            });
            console.log('Prediction:', response.data);
            const backendRoot = import.meta.env.VITE_BACKEND_ROOT
            const plotURL = `${backendRoot}${response.data.plot_img}`
            const ma100Url = `${backendRoot}${response.data.plot_100_dma}`
            const ma200Url = `${backendRoot}${response.data.plot_200_dma}`
            const predictionUrl = `${backendRoot}${response.data.plot_prediction}`
            console.log(plotURL)
            setPlot(plotURL)
            setMA100(ma100Url)
            setMA200(ma200Url)
            setPrediction(predictionUrl)
            setMSE(response.data.mse)
            setRMSE(response.data.rmse)
            setR2(response.data.r2)
            setNextDay(response.data.next_day_prediction)
            setLastClose(response.data.last_close)
            setLastDate(response.data.last_date)
            setChartTicker(ticker)

            // Set plots
            if(response.data.error){
                setError(response.data.error)
            }
        }catch(error){
            if (error.response) {
                console.error("Backend Error:", error.response.data);
                setError(error.response.data.error || "Something went wrong. Please try another ticker.");
            } else {
                console.error("Error:", error);
                setError("Could not reach the server. Please try again.");
            }
            // Clear previous results so a stale chart/plots aren't shown under an error.
            setPrediction();
            setChartTicker();
        }finally{
            setLoading(false);
        }
    }

    return (
        <div className="container">
            <div className="row">
                <div className="col-md-6 mx-auto">
                    <form onSubmit={handleSubmit} autoComplete="off">
                        <div style={{ position: "relative" }}>
                            <input
                                type="text"
                                className="form-control"
                                placeholder="Search Indian stock (name or symbol)"
                                value={ticker}
                                onChange={(e) => { setTicker(e.target.value); fetchSuggestions(e.target.value); }}
                                onFocus={() => { if (suggestions.length) setShowSug(true); }}
                                onBlur={() => setTimeout(() => setShowSug(false), 200)}
                                required
                            />
                            {showSug && suggestions.length > 0 && (
                                <div
                                    className="position-absolute w-100"
                                    style={{ zIndex: 30, background: "#1e222d", border: "1px solid #2a2e39", borderRadius: 4, maxHeight: 260, overflowY: "auto" }}
                                >
                                    {suggestions.map((s) => (
                                        <div
                                            key={s.symbol}
                                            onMouseDown={() => { setTicker(s.symbol); setShowSug(false); }}
                                            style={{ padding: "6px 10px", cursor: "pointer", borderBottom: "1px solid #2a2e39", color: "#d1d4dc" }}
                                        >
                                            <strong>{s.symbol}</strong>{" "}
                                            <span style={{ color: "#9aa0aa", fontSize: 13 }}>— {s.name}</span>{" "}
                                            <span style={{ color: "#6c757d", fontSize: 11 }}>{s.exchange}</span>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                        <small>{error && <div className="text-danger">{error}</div>}</small>
                        <button type='submit' className="btn btn-info mt-3">
                            {loading ? <span><FontAwesomeIcon icon={faSpinner} spin />Please Wait...</span>: 'See Prediction'}
                        </button>
                    </form>
                </div>

            {/* Interactive, hoverable price chart (new feature) */}
            {chartTicker && (
                <div className="col-12 mt-5">
                    <PriceChart
                        ticker={chartTicker}
                        predictedPrice={nextDay}
                        asOf={asOf}
                        setAsOf={setAsOf}
                        period={period}
                        setPeriod={setPeriod}
                    />
                    <RangeForecastPanel ticker={chartTicker} asOf={asOf} period={period} />
                    <NewsPanel ticker={chartTicker} />
                    <BacktestPanel ticker={chartTicker} />
                </div>
            )}

            {/*Print Prediction plots*/}
            {prediction && (
                <div className="prediction mt-5">
                {nextDay !== undefined && nextDay !== null && (
                    <div className="text-light text-center p-4 mb-3 bg-light-dark rounded">
                        <h4>📈 Predicted Next-Day Close</h4>
                        <h2 className="text-info">${nextDay}</h2>
                        {lastClose !== undefined && (
                            <p className="mb-0">Last close ({lastDate}): ${lastClose}</p>
                        )}
                    </div>
                )}
                <div className="p-3">
                    {plot && (
                        <img src={plot} style={{ maxWidth: '100%'}}/>
                    )}
                </div>
                <div className="p-3">
                    {ma100 && (
                        <img src={ma100} style={{ maxWidth: '100%'}}/>
                    )}
                </div>
                <div className="p-3">
                    {ma200 && (
                        <img src={ma200} style={{ maxWidth: '100%'}}/>
                    )}
                </div>
                <div className="p-3">
                    {prediction && (
                        <img src={prediction} style={{ maxWidth: '100%'}}/>
                    )}
                </div>
                <div className="text-light p3">
                    <h4>Model Evalution</h4>
                    <p>Mean Squared Error (MSE): {mse}</p>
                    <p>Root Mean Squared Error (RMSE): {rmse}</p>
                    <p>R-Squared Error: {r2}</p>

                </div>
            </div>
            )}
            
            </div>
        </div>
    )
}

export default Dashboard