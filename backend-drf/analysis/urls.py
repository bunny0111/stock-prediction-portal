from django.urls import path
from .views import (
    TickerSearchView,
    MarketDataView,
    SupportResistanceView,
    VolumeAnalysisView,
    TrendAnalysisView,
    ConfluenceView,
    OpportunityView,
    BacktestView,
    NewsView,
    RangeForecastView,
    OpportunityScanView,
)

urlpatterns = [
    # New analysis platform endpoints live under /api/v1/ alongside the existing API.
    path('search/', TickerSearchView.as_view(), name='ticker_search'),
    path('market-data/<str:ticker>/', MarketDataView.as_view(), name='market_data'),
    path('support-resistance/<str:ticker>/', SupportResistanceView.as_view(), name='support_resistance'),
    path('volume/<str:ticker>/', VolumeAnalysisView.as_view(), name='volume_analysis'),
    path('trend/<str:ticker>/', TrendAnalysisView.as_view(), name='trend_analysis'),
    path('confluence/<str:ticker>/', ConfluenceView.as_view(), name='confluence'),
    path('opportunity/<str:ticker>/', OpportunityView.as_view(), name='opportunity'),
    path('backtest/<str:ticker>/', BacktestView.as_view(), name='backtest'),
    path('range-forecast/<str:ticker>/', RangeForecastView.as_view(), name='range_forecast'),
    path('scan/', OpportunityScanView.as_view(), name='opportunity_scan'),
    path('news/<str:ticker>/', NewsView.as_view(), name='news'),
]
