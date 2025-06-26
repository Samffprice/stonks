"""
Polygon.io API client for fetching market data.

This module provides a comprehensive client for interacting with the Polygon.io API,
including rate limiting, error handling, and data transformation.
"""

import time
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import List, Optional, Dict, Any, Union
import requests
import logging

from ..config.settings import Config
from ..utils.logger import get_logger
from .models import (
    OHLCVData, NewsArticle, OptionsContract, TechnicalIndicator,
    APIResponse, RateLimitInfo, validate_ticker_symbol
)


class PolygonAPIError(Exception):
    """Custom exception for Polygon API errors."""
    
    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[Dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data


class RateLimiter:
    """Rate limiter for API calls."""
    
    def __init__(self, calls_per_minute: int = 5):
        self.calls_per_minute = calls_per_minute
        self.call_times: List[float] = []
        self.logger = get_logger('api.ratelimiter')
    
    def wait_if_needed(self) -> None:
        """Wait if necessary to respect rate limits."""
        now = time.time()
        
        # Remove calls older than 1 minute
        cutoff_time = now - 60
        self.call_times = [t for t in self.call_times if t > cutoff_time]
        
        # Check if we need to wait
        if len(self.call_times) >= self.calls_per_minute:
            wait_time = 60 - (now - self.call_times[0]) + 1  # Add 1 second buffer
            self.logger.info(f"Rate limit reached. Waiting {wait_time:.1f} seconds")
            time.sleep(wait_time)
            
            # Clean up old calls again after waiting
            now = time.time()
            cutoff_time = now - 60
            self.call_times = [t for t in self.call_times if t > cutoff_time]
    
    def record_call(self) -> None:
        """Record that an API call was made."""
        self.call_times.append(time.time())
    
    def get_info(self) -> RateLimitInfo:
        """Get current rate limit information."""
        now = time.time()
        cutoff_time = now - 60
        recent_calls = [t for t in self.call_times if t > cutoff_time]
        
        calls_remaining = max(0, self.calls_per_minute - len(recent_calls))
        reset_time = datetime.utcnow()
        
        if recent_calls:
            reset_time = datetime.fromtimestamp(recent_calls[0] + 60)
        
        return RateLimitInfo(
            calls_remaining=calls_remaining,
            reset_time=reset_time,
            calls_per_minute=self.calls_per_minute
        )


class PolygonClient:
    """Polygon.io API client with rate limiting and error handling."""
    
    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self.api_key = self.config.api.polygon_api_key
        self.base_url = "https://api.polygon.io"
        self.rate_limiter = RateLimiter(self.config.api.polygon_rate_limit)
        self.logger = get_logger('api.polygon')
        
        # Set up session for HTTP connections
        self.session = requests.Session()
        self.max_retries = self.config.api.polygon_max_retries
        
        if not self.api_key:
            raise ValueError("Polygon API key is required")
    
    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> APIResponse:
        """Make a rate-limited request to the Polygon API with retries."""
        # Wait for rate limiting
        self.rate_limiter.wait_if_needed()
        
        # Prepare request
        url = f"{self.base_url}{endpoint}"
        request_params = {"apikey": self.api_key}
        if params:
            request_params.update(params)
        
        last_exception = None
        for attempt in range(self.max_retries + 1):
            try:
                self.logger.debug(f"Making request to {endpoint} with params: {params} (attempt {attempt + 1})")
                response = self.session.get(url, params=request_params, timeout=30)
                self.rate_limiter.record_call()
                
                # Handle response
                if response.status_code == 200:
                    data = response.json()
                    return APIResponse(
                        status=data.get("status", "OK"),
                        request_id=data.get("request_id"),
                        next_url=data.get("next_url"),
                        count=data.get("count"),
                        results=data.get("results", [])
                    )
                elif response.status_code in [429, 500, 502, 503, 504] and attempt < self.max_retries:
                    # Retry on server errors and rate limits
                    wait_time = 2 ** attempt  # Exponential backoff
                    self.logger.warning(f"Request failed with status {response.status_code}, retrying in {wait_time}s")
                    time.sleep(wait_time)
                    continue
                else:
                    error_msg = f"API request failed with status {response.status_code}"
                    try:
                        error_data = response.json()
                        error_msg += f": {error_data.get('error', 'Unknown error')}"
                    except:
                        error_msg += f": {response.text}"
                    
                    raise PolygonAPIError(error_msg, response.status_code)
                    
            except requests.exceptions.RequestException as e:
                last_exception = e
                if attempt < self.max_retries:
                    wait_time = 2 ** attempt
                    self.logger.warning(f"Request failed: {str(e)}, retrying in {wait_time}s")
                    time.sleep(wait_time)
                    continue
                else:
                    raise PolygonAPIError(f"Request failed after {self.max_retries} retries: {str(e)}")
        
        # Should not reach here, but just in case
        raise PolygonAPIError(f"Request failed after {self.max_retries} retries: {str(last_exception)}")
    
    def get_stock_bars(
        self,
        symbol: str,
        start_date: Union[str, date],
        end_date: Union[str, date],
        timespan: str = "day",
        multiplier: int = 1,
        limit: int = 5000
    ) -> List[OHLCVData]:
        """
        Get OHLCV bars for a stock.
        
        Args:
            symbol: Stock symbol
            start_date: Start date (YYYY-MM-DD format or date object)
            end_date: End date (YYYY-MM-DD format or date object)
            timespan: Timespan (minute, hour, day, week, month, quarter, year)
            multiplier: Multiplier for timespan
            limit: Maximum number of results
        
        Returns:
            List of OHLCVData objects
        """
        symbol = validate_ticker_symbol(symbol)
        
        # Convert dates to strings if needed
        if isinstance(start_date, date):
            start_date = start_date.strftime("%Y-%m-%d")
        if isinstance(end_date, date):
            end_date = end_date.strftime("%Y-%m-%d")
        
        endpoint = f"/v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/{start_date}/{end_date}"
        params = {
            "adjusted": "true",
            "sort": "asc",
            "limit": limit
        }
        
        response = self._make_request(endpoint, params)
        bars = []
        
        for result in response.results:
            try:
                bar = OHLCVData(
                    symbol=symbol,
                    timestamp=datetime.fromtimestamp(result["t"] / 1000),
                    open=Decimal(str(result["o"])),
                    high=Decimal(str(result["h"])),
                    low=Decimal(str(result["l"])),
                    close=Decimal(str(result["c"])),
                    volume=int(result["v"]),
                    vwap=Decimal(str(result.get("vw", 0))) if result.get("vw") else None
                )
                bars.append(bar)
            except (KeyError, ValueError) as e:
                self.logger.warning(f"Failed to parse bar data for {symbol}: {e}")
                continue
        
        self.logger.info(f"Retrieved {len(bars)} bars for {symbol}")
        return bars
    
    def get_news(
        self,
        symbol: Optional[str] = None,
        start_date: Optional[Union[str, date]] = None,
        end_date: Optional[Union[str, date]] = None,
        limit: int = 1000
    ) -> List[NewsArticle]:
        """
        Get news articles.
        
        Args:
            symbol: Optional stock symbol to filter by
            start_date: Start date for news articles
            end_date: End date for news articles  
            limit: Maximum number of articles
        
        Returns:
            List of NewsArticle objects
        """
        endpoint = "/v2/reference/news"
        params = {"limit": limit, "sort": "published_utc"}
        
        if symbol:
            symbol = validate_ticker_symbol(symbol)
            params["ticker"] = symbol
        
        if start_date:
            if isinstance(start_date, date):
                start_date = start_date.strftime("%Y-%m-%d")
            params["published_utc.gte"] = start_date
        
        if end_date:
            if isinstance(end_date, date):
                end_date = end_date.strftime("%Y-%m-%d")
            params["published_utc.lte"] = end_date
        
        response = self._make_request(endpoint, params)
        articles = []
        
        for result in response.results:
            try:
                article = NewsArticle(
                    id=result["id"],
                    title=result["title"],
                    description=result.get("description"),
                    author=result.get("author"),
                    published_utc=datetime.fromisoformat(result["published_utc"].replace("Z", "+00:00")),
                    article_url=result.get("article_url"),
                    tickers=result.get("tickers", []),
                    keywords=result.get("keywords", [])
                )
                articles.append(article)
            except (KeyError, ValueError) as e:
                self.logger.warning(f"Failed to parse news article: {e}")
                continue
        
        self.logger.info(f"Retrieved {len(articles)} news articles")
        return articles
    
    def get_options_contracts(
        self,
        underlying_symbol: str,
        expiration_date: Optional[Union[str, date]] = None,
        strike_price: Optional[float] = None,
        option_type: Optional[str] = None,
        limit: int = 1000
    ) -> List[OptionsContract]:
        """
        Get options contracts for an underlying symbol.
        
        Args:
            underlying_symbol: Underlying stock symbol
            expiration_date: Optional expiration date to filter by
            strike_price: Optional strike price to filter by
            option_type: Optional option type ('call' or 'put')
            limit: Maximum number of contracts
        
        Returns:
            List of OptionsContract objects
        """
        underlying_symbol = validate_ticker_symbol(underlying_symbol)
        
        endpoint = "/v3/reference/options/contracts"
        params = {
            "underlying_ticker": underlying_symbol,
            "limit": limit,
            "sort": "expiration_date"
        }
        
        if expiration_date:
            if isinstance(expiration_date, date):
                expiration_date = expiration_date.strftime("%Y-%m-%d")
            params["expiration_date"] = expiration_date
        
        if strike_price:
            params["strike_price"] = strike_price
        
        if option_type:
            if option_type.lower() not in ['call', 'put']:
                raise ValueError("option_type must be 'call' or 'put'")
            params["contract_type"] = option_type.lower()
        
        response = self._make_request(endpoint, params)
        contracts = []
        
        for result in response.results:
            try:
                contract = OptionsContract(
                    contract_symbol=result["ticker"],
                    underlying_ticker=result["underlying_ticker"],
                    strike_price=Decimal(str(result["strike_price"])),
                    expiration_date=datetime.strptime(result["expiration_date"], "%Y-%m-%d").date(),
                    option_type=result["contract_type"]
                )
                contracts.append(contract)
            except (KeyError, ValueError) as e:
                self.logger.warning(f"Failed to parse options contract: {e}")
                continue
        
        self.logger.info(f"Retrieved {len(contracts)} options contracts for {underlying_symbol}")
        return contracts
    
    def get_technical_indicators(
        self,
        symbol: str,
        indicator_name: str,
        start_date: Union[str, date],
        end_date: Union[str, date],
        timespan: str = "day",
        period: int = 50,
        limit: int = 5000
    ) -> List[TechnicalIndicator]:
        """
        Get technical indicators for a symbol.
        
        Args:
            symbol: Stock symbol
            indicator_name: Technical indicator name (sma, ema, rsi, etc.)
            start_date: Start date
            end_date: End date
            timespan: Timespan for calculation
            period: Period for indicator calculation
            limit: Maximum number of results
        
        Returns:
            List of TechnicalIndicator objects
        """
        symbol = validate_ticker_symbol(symbol)
        
        # Convert dates to strings if needed
        if isinstance(start_date, date):
            start_date = start_date.strftime("%Y-%m-%d")
        if isinstance(end_date, date):
            end_date = end_date.strftime("%Y-%m-%d")
        
        endpoint = f"/v1/indicators/{indicator_name}/{symbol}"
        params = {
            "timestamp.gte": start_date,
            "timestamp.lte": end_date,
            "timespan": timespan,
            f"{indicator_name}.window": period,
            "limit": limit,
            "order": "asc"
        }
        
        response = self._make_request(endpoint, params)
        indicators = []
        
        for result in response.results:
            try:
                indicator = TechnicalIndicator(
                    symbol=symbol,
                    timestamp=datetime.fromtimestamp(result["timestamp"] / 1000),
                    indicator_name=indicator_name,
                    value=float(result.get("value", result.get(indicator_name, {}).get("value", 0))),
                    period=period
                )
                indicators.append(indicator)
            except (KeyError, ValueError) as e:
                self.logger.warning(f"Failed to parse technical indicator: {e}")
                continue
        
        self.logger.info(f"Retrieved {len(indicators)} {indicator_name} indicators for {symbol}")
        return indicators
    
    def get_rate_limit_info(self) -> RateLimitInfo:
        """Get current rate limit information."""
        return self.rate_limiter.get_info()
    
    def health_check(self) -> bool:
        """Perform a health check on the API connection."""
        try:
            # Make a simple request to check connectivity
            endpoint = "/v2/reference/tickers"
            params = {"limit": 1}
            response = self._make_request(endpoint, params)
            return response.status == "OK"
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            return False