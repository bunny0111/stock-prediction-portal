from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from .services.market_data import MarketDataService, MarketDataError
from .services.support_resistance import SupportResistanceService
from .services.volume_analysis import VolumeAnalysisService
from .services.trend_analysis import TrendAnalysisService
from .services.confluence import ConfluenceScoringService
from .services.opportunity import OpportunityService
from .services.backtest import BacktestService
from .services.news import NewsAnalysisService
from .services.range_forecast import RangeForecastService
from .services.opportunity_scan import OpportunityScanService


class TickerSearchView(APIView):
    """
    GET /api/v1/search/?q=<query>

    Autocomplete suggestions for INDIAN stocks (NSE/BSE) by name or symbol.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        query = request.query_params.get("q", "")
        return Response({"status": "success", "data": MarketDataService().search(query)})


class MarketDataView(APIView):
    """
    GET /api/v1/market-data/<ticker>/?period=2y&interval=1d

    A THIN view: it does not contain business logic. It only
      1. reads inputs,
      2. calls the service,
      3. returns the result (or a clean error).
    All the real work lives in MarketDataService.
    """
    permission_classes = [IsAuthenticated]  # same JWT protection as the rest of the app

    def get(self, request, ticker):
        period = request.query_params.get("period", "2y")
        interval = request.query_params.get("interval", "1d")

        try:
            data = MarketDataService().get_ohlcv(ticker, period=period, interval=interval)
        except MarketDataError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        return Response({"status": "success", "data": data})


class SupportResistanceView(APIView):
    """
    GET /api/v1/support-resistance/<ticker>/?period=2y&interval=1d

    Thin view: reads inputs, calls SupportResistanceService, returns the
    uniform {signal, confidence, details, viz} result.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, ticker):
        period = request.query_params.get("period", "2y")
        interval = request.query_params.get("interval", "1d")
        as_of = request.query_params.get("as_of") or None  # YYYY-MM-DD cutoff (optional)

        try:
            data = SupportResistanceService().analyze(
                ticker, period=period, interval=interval, as_of=as_of
            )
        except MarketDataError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        return Response({"status": "success", "data": data})


class VolumeAnalysisView(APIView):
    """
    GET /api/v1/volume/<ticker>/?period=1y&interval=1d

    Thin view -> VolumeAnalysisService -> uniform {signal, confidence, details, viz}.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, ticker):
        period = request.query_params.get("period", "1y")
        interval = request.query_params.get("interval", "1d")
        as_of = request.query_params.get("as_of") or None

        try:
            data = VolumeAnalysisService().analyze(
                ticker, period=period, interval=interval, as_of=as_of
            )
        except MarketDataError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        return Response({"status": "success", "data": data})


class TrendAnalysisView(APIView):
    """
    GET /api/v1/trend/<ticker>/?period=1y&interval=1d&as_of=YYYY-MM-DD

    Thin view -> TrendAnalysisService -> uniform {signal, confidence, details, viz}.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, ticker):
        period = request.query_params.get("period", "1y")
        interval = request.query_params.get("interval", "1d")
        as_of = request.query_params.get("as_of") or None

        try:
            data = TrendAnalysisService().analyze(
                ticker, period=period, interval=interval, as_of=as_of
            )
        except MarketDataError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        return Response({"status": "success", "data": data})


class ConfluenceView(APIView):
    """
    GET /api/v1/confluence/<ticker>/?period=1y&interval=1d&as_of=YYYY-MM-DD

    Combines Trend + Support/Resistance + Volume into one 0-100 setup score.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, ticker):
        period = request.query_params.get("period", "1y")
        interval = request.query_params.get("interval", "1d")
        as_of = request.query_params.get("as_of") or None

        try:
            data = ConfluenceScoringService().analyze(
                ticker, period=period, interval=interval, as_of=as_of
            )
        except MarketDataError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        return Response({"status": "success", "data": data})


class OpportunityView(APIView):
    """
    GET /api/v1/opportunity/<ticker>/?period=1y&interval=1d&as_of=YYYY-MM-DD

    Builds an educational trade plan (entry / stop / targets / risk-reward).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, ticker):
        period = request.query_params.get("period", "1y")
        interval = request.query_params.get("interval", "1d")
        as_of = request.query_params.get("as_of") or None

        try:
            data = OpportunityService().analyze(
                ticker, period=period, interval=interval, as_of=as_of
            )
        except MarketDataError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        return Response({"status": "success", "data": data})


class BacktestView(APIView):
    """
    GET /api/v1/backtest/<ticker>/?period=2y&step=5&max_holding=20&min_history=150

    Replays the trade signal over history and reports win rate, profit factor,
    R-multiple, drawdown, and a per-confluence-score breakdown. Heavy endpoint.
    All run parameters are configurable via query string.
    """
    permission_classes = [IsAuthenticated]

    def _int(self, request, name, default, lo, hi):
        try:
            return max(lo, min(hi, int(request.query_params.get(name, default))))
        except (TypeError, ValueError):
            return default

    def get(self, request, ticker):
        period = request.query_params.get("period", "2y")
        step = self._int(request, "step", 5, 1, 30)
        max_holding = self._int(request, "max_holding", 20, 3, 120)
        min_history = self._int(request, "min_history", 150, 60, 500)
        min_score = self._int(request, "min_score", 0, 0, 100)
        try:
            min_rr = max(0.0, min(10.0, float(request.query_params.get("min_rr", 0))))
        except (TypeError, ValueError):
            min_rr = 0.0
        target_method = "B" if request.query_params.get("target_method") == "B" else "A"

        try:
            data = BacktestService().run(
                ticker, period=period, step=step,
                max_holding=max_holding, min_history=min_history,
                min_rr=min_rr, min_score=min_score, target_method=target_method,
            )
        except MarketDataError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        return Response({"status": "success", "data": data})


class RangeForecastView(APIView):
    """
    GET /api/v1/range-forecast/<ticker>/?period=2y&interval=1d&as_of=YYYY-MM-DD

    Calibrated probabilistic next-day RANGE forecast (50/70/90 intervals,
    expected high/low, trend posture, confidence) — NOT a price prediction.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, ticker):
        period = request.query_params.get("period", "2y")
        interval = request.query_params.get("interval", "1d")
        as_of = request.query_params.get("as_of") or None

        try:
            data = RangeForecastService().analyze(
                ticker, period=period, interval=interval, as_of=as_of
            )
        except MarketDataError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        return Response({"status": "success", "data": data})


class OpportunityScanView(APIView):
    """
    GET /api/v1/scan/

    EXPERIMENTAL multi-stock scanner: ranks a fixed liquid watchlist by expected
    next-day move + expansion (Opportunity Score). Magnitude/risk only — no
    direction. Heavier than single-stock endpoints (fetches the whole watchlist).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        data = OpportunityScanService().scan()
        return Response({"status": "success", "data": data})


class NewsView(APIView):
    """
    GET /api/v1/news/<ticker>/

    Recent company news from yfinance (display-only, no AI, no sentiment).
    Always returns 200 — news is optional context, so an empty list is fine.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, ticker):
        data = NewsAnalysisService().get_news(ticker)
        return Response({"status": "success", "data": data})
