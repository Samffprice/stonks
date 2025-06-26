"""
Data ingestion module for the AI Options Trading System.

This module handles fetching and processing market data from external APIs,
primarily Polygon.io for OHLCV data, news, options contracts, and technical indicators.
"""

from .models import (
    OHLCVData,
    NewsArticle,
    OptionsContract,
    TechnicalIndicator,
    MarketData,
    APIResponse,
    RateLimitInfo,
    convert_to_dataframe,
    validate_ticker_symbol,
)

from .polygon_client import (
    PolygonClient,
    PolygonAPIError,
    RateLimitExceededError,
    DataType,
    TimeFrame,
    OptionsContract as PolygonOptionsContract,
    OptionsBar,
    RateLimitInfo as PolygonRateLimitInfo,
)

from .eod_collector import (
    EODDataCollector,
    DataStorage,
    CollectionProgress,
)

__all__ = [
    # Models
    "OHLCVData",
    "NewsArticle", 
    "OptionsContract",
    "TechnicalIndicator",
    "MarketData",
    "APIResponse",
    "RateLimitInfo",
    "convert_to_dataframe",
    "validate_ticker_symbol",
    
    # Polygon Client
    "PolygonClient",
    "PolygonAPIError",
    "RateLimitExceededError",
    "DataType",
    "TimeFrame",
    "PolygonOptionsContract",
    "OptionsBar",
    "PolygonRateLimitInfo",
    
    # EOD Collector
    "EODDataCollector",
    "DataStorage", 
    "CollectionProgress",
]