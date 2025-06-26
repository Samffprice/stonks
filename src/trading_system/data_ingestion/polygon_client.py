"""
Polygon.io API Client for Options Trading System

This module provides a robust client for interacting with the Polygon.io API,
with strict rate limiting (5 calls/minute), comprehensive error handling,
and data validation for options data retrieval.
"""

import time
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict
import logging
from enum import Enum

import requests
import pandas as pd
from polygon import RESTClient

from ..config.settings import Config
from ..utils.logger import get_logger


class DataType(Enum):
    """Supported data types for polygon API"""
    TRADES = "trades"
    QUOTES = "quotes"
    BARS = "bars"
    OPTIONS_CONTRACTS = "options_contracts"
    DAILY_BARS = "daily_bars"


class TimeFrame(Enum):
    """Supported timeframes for historical data"""
    MINUTE = "minute"
    HOUR = "hour"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


@dataclass
class OptionsContract:
    """Options contract data structure"""
    ticker: str
    underlying_ticker: str
    contract_type: str  # 'call' or 'put'
    expiration_date: str
    strike_price: float
    exercise_style: str
    shares_per_contract: int
    primary_exchange: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class OptionsBar:
    """Options bar data structure"""
    ticker: str
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: int
    vwap: Optional[float] = None
    transactions: Optional[int] = None


@dataclass
class RateLimitInfo:
    """Rate limit tracking information"""
    calls_made: int = 0
    window_start: float = 0.0
    last_call_time: float = 0.0


class PolygonAPIError(Exception):
    """Custom exception for Polygon API errors"""
    pass


class RateLimitExceededError(PolygonAPIError):
    """Exception raised when rate limit is exceeded"""
    pass


class PolygonClient:
    """
    Polygon.io API client with rate limiting and error handling
    
    Features:
    - Rate limiting: 5 calls per minute with 13-second minimum delays
    - Automatic retry with exponential backoff
    - Comprehensive error handling
    - Data validation and transformation
    - Logging for monitoring and debugging
    """
    
    def __init__(self, config: Config):
        """
        Initialize the Polygon client
        
        Args:
            config: Application configuration containing API credentials
        """
        self.config = config
        self.logger = get_logger(f"{__name__}.PolygonClient")
        
        # Rate limiting configuration (5 calls per minute)
        self.max_calls_per_minute = 5
        self.min_delay_seconds = 13  # 60/5 + buffer = 13 seconds
        self.rate_limit = RateLimitInfo()
        
        # Initialize REST client
        try:
            self.client = RESTClient(api_key=config.api.polygon_api_key)
            self.logger.info("Polygon client initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize Polygon client: {e}")
            raise PolygonAPIError(f"Client initialization failed: {e}")
    
    def _check_rate_limit(self) -> None:
        """
        Check and enforce rate limiting
        
        Raises:
            RateLimitExceededError: If rate limit would be exceeded
        """
        current_time = time.time()
        
        # Reset window if more than 60 seconds have passed
        if current_time - self.rate_limit.window_start >= 60:
            self.rate_limit.calls_made = 0
            self.rate_limit.window_start = current_time
        
        # Check if we've exceeded the rate limit
        if self.rate_limit.calls_made >= self.max_calls_per_minute:
            wait_time = 60 - (current_time - self.rate_limit.window_start)
            if wait_time > 0:
                self.logger.warning(f"Rate limit reached. Waiting {wait_time:.2f} seconds")
                time.sleep(wait_time)
                # Reset after waiting
                self.rate_limit.calls_made = 0
                self.rate_limit.window_start = time.time()
        
        # Enforce minimum delay between calls
        time_since_last_call = current_time - self.rate_limit.last_call_time
        if time_since_last_call < self.min_delay_seconds:
            wait_time = self.min_delay_seconds - time_since_last_call
            self.logger.debug(f"Enforcing minimum delay. Waiting {wait_time:.2f} seconds")
            time.sleep(wait_time)
    
    def _make_api_call(self, func, *args, **kwargs) -> Any:
        """
        Make an API call with rate limiting and error handling
        
        Args:
            func: API function to call
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function
            
        Returns:
            API response data
            
        Raises:
            PolygonAPIError: If API call fails after retries
        """
        max_retries = 3
        base_delay = 1
        
        for attempt in range(max_retries):
            try:
                # Enforce rate limiting
                self._check_rate_limit()
                
                # Make the API call
                func_name = getattr(func, '__name__', str(func))
                self.logger.debug(f"Making API call: {func_name} (attempt {attempt + 1})")
                response = func(*args, **kwargs)
                
                # Update rate limit tracking
                self.rate_limit.calls_made += 1
                self.rate_limit.last_call_time = time.time()
                
                self.logger.debug(f"API call successful: {func_name}")
                return response
                
            except Exception as e:
                self.logger.warning(f"API call failed (attempt {attempt + 1}): {e}")
                
                if attempt == max_retries - 1:
                    func_name = getattr(func, '__name__', str(func))
                    self.logger.error(f"All retry attempts failed for {func_name}")
                    raise PolygonAPIError(f"API call failed after {max_retries} attempts: {e}")
                
                # Exponential backoff
                delay = base_delay * (2 ** attempt)
                self.logger.info(f"Retrying in {delay} seconds...")
                time.sleep(delay)
    
    def get_options_contracts(
        self,
        underlying_ticker: str,
        expiration_date: Optional[str] = None,
        contract_type: Optional[str] = None,
        strike_price_gte: Optional[float] = None,
        strike_price_lte: Optional[float] = None,
        expired: bool = False,
        limit: int = 1000
    ) -> List[OptionsContract]:
        """
        Get options contracts for an underlying ticker
        
        Args:
            underlying_ticker: The underlying stock ticker
            expiration_date: Expiration date in YYYY-MM-DD format
            contract_type: 'call' or 'put'
            strike_price_gte: Minimum strike price
            strike_price_lte: Maximum strike price
            expired: Include expired contracts
            limit: Maximum number of contracts to return
            
        Returns:
            List of options contracts
        """
        self.logger.info(f"Fetching options contracts for {underlying_ticker}")
        
        try:
            response = self._make_api_call(
                self.client.list_options_contracts,
                underlying_ticker=underlying_ticker,
                expiration_date=expiration_date,
                contract_type=contract_type,
                strike_price_gte=strike_price_gte,
                strike_price_lte=strike_price_lte,
                expired=expired,
                limit=limit
            )
            
            contracts = []
            if hasattr(response, 'results') and response.results:
                for contract_data in response.results:
                    contract = OptionsContract(
                        ticker=getattr(contract_data, 'ticker', ''),
                        underlying_ticker=getattr(contract_data, 'underlying_ticker', underlying_ticker),
                        contract_type=getattr(contract_data, 'contract_type', ''),
                        expiration_date=getattr(contract_data, 'expiration_date', ''),
                        strike_price=getattr(contract_data, 'strike_price', 0.0),
                        exercise_style=getattr(contract_data, 'exercise_style', ''),
                        shares_per_contract=getattr(contract_data, 'shares_per_contract', 100),
                        primary_exchange=getattr(contract_data, 'primary_exchange', ''),
                        created_at=getattr(contract_data, 'created_at', None),
                        updated_at=getattr(contract_data, 'updated_at', None)
                    )
                    contracts.append(contract)
            
            self.logger.info(f"Retrieved {len(contracts)} options contracts for {underlying_ticker}")
            return contracts
            
        except Exception as e:
            self.logger.error(f"Failed to get options contracts for {underlying_ticker}: {e}")
            raise PolygonAPIError(f"Failed to get options contracts: {e}")
    
    def get_options_bars(
        self,
        options_ticker: str,
        timespan: TimeFrame,
        from_date: str,
        to_date: str,
        adjusted: bool = True,
        sort: str = "asc",
        limit: int = 5000
    ) -> List[OptionsBar]:
        """
        Get historical bars for an options contract
        
        Args:
            options_ticker: The options ticker symbol
            timespan: Timeframe for the bars
            from_date: Start date in YYYY-MM-DD format
            to_date: End date in YYYY-MM-DD format
            adjusted: Whether to return adjusted data
            sort: Sort order ('asc' or 'desc')
            limit: Maximum number of bars to return
            
        Returns:
            List of options bars
        """
        self.logger.info(f"Fetching options bars for {options_ticker} from {from_date} to {to_date}")
        
        try:
            response = self._make_api_call(
                self.client.get_aggs,
                ticker=options_ticker,
                multiplier=1,
                timespan=timespan.value,
                from_=from_date,
                to=to_date,
                adjusted=adjusted,
                sort=sort,
                limit=limit
            )
            
            bars = []
            if hasattr(response, 'results') and response.results:
                for bar_data in response.results:
                    bar = OptionsBar(
                        ticker=options_ticker,
                        timestamp=getattr(bar_data, 't', 0),
                        open=getattr(bar_data, 'o', 0.0),
                        high=getattr(bar_data, 'h', 0.0),
                        low=getattr(bar_data, 'l', 0.0),
                        close=getattr(bar_data, 'c', 0.0),
                        volume=getattr(bar_data, 'v', 0),
                        vwap=getattr(bar_data, 'vw', None),
                        transactions=getattr(bar_data, 'n', None)
                    )
                    bars.append(bar)
            
            self.logger.info(f"Retrieved {len(bars)} bars for {options_ticker}")
            return bars
            
        except Exception as e:
            self.logger.error(f"Failed to get options bars for {options_ticker}: {e}")
            raise PolygonAPIError(f"Failed to get options bars: {e}")
    
    def get_underlying_bars(
        self,
        ticker: str,
        timespan: TimeFrame,
        from_date: str,
        to_date: str,
        adjusted: bool = True,
        sort: str = "asc",
        limit: int = 5000
    ) -> pd.DataFrame:
        """
        Get historical bars for the underlying stock
        
        Args:
            ticker: The stock ticker symbol
            timespan: Timeframe for the bars
            from_date: Start date in YYYY-MM-DD format
            to_date: End date in YYYY-MM-DD format
            adjusted: Whether to return adjusted data
            sort: Sort order ('asc' or 'desc')
            limit: Maximum number of bars to return
            
        Returns:
            DataFrame with OHLCV data
        """
        self.logger.info(f"Fetching underlying bars for {ticker} from {from_date} to {to_date}")
        
        try:
            response = self._make_api_call(
                self.client.get_aggs,
                ticker=ticker,
                multiplier=1,
                timespan=timespan.value,
                from_=from_date,
                to=to_date,
                adjusted=adjusted,
                sort=sort,
                limit=limit
            )
            
            data = []
            if hasattr(response, 'results') and response.results:
                for bar in response.results:
                    data.append({
                        'timestamp': getattr(bar, 't', 0),
                        'open': getattr(bar, 'o', 0.0),
                        'high': getattr(bar, 'h', 0.0),
                        'low': getattr(bar, 'l', 0.0),
                        'close': getattr(bar, 'c', 0.0),
                        'volume': getattr(bar, 'v', 0),
                        'vwap': getattr(bar, 'vw', None),
                        'transactions': getattr(bar, 'n', None)
                    })
            
            df = pd.DataFrame(data)
            if not df.empty:
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                df.set_index('timestamp', inplace=True)
            
            self.logger.info(f"Retrieved {len(df)} bars for {ticker}")
            return df
            
        except Exception as e:
            self.logger.error(f"Failed to get underlying bars for {ticker}: {e}")
            raise PolygonAPIError(f"Failed to get underlying bars: {e}")
    
    def get_market_status(self) -> Dict[str, Any]:
        """
        Get current market status
        
        Returns:
            Dictionary containing market status information
        """
        self.logger.debug("Fetching market status")
        
        try:
            response = self._make_api_call(self.client.get_market_status)
            
            status = {
                'market': getattr(response, 'market', 'unknown'),
                'server_time': getattr(response, 'serverTime', ''),
                'exchanges': {}
            }
            
            if hasattr(response, 'exchanges'):
                for exchange_name, exchange_data in response.exchanges.items():
                    status['exchanges'][exchange_name] = {
                        'status': getattr(exchange_data, 'status', 'unknown'),
                        'session': getattr(exchange_data, 'session', 'unknown')
                    }
            
            self.logger.debug("Market status retrieved successfully")
            return status
            
        except Exception as e:
            self.logger.error(f"Failed to get market status: {e}")
            raise PolygonAPIError(f"Failed to get market status: {e}")
    
    def validate_ticker(self, ticker: str) -> bool:
        """
        Validate that a ticker exists and is tradeable
        
        Args:
            ticker: The ticker symbol to validate
            
        Returns:
            True if ticker is valid, False otherwise
        """
        self.logger.debug(f"Validating ticker: {ticker}")
        
        try:
            # Try to get recent data for the ticker
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            
            response = self._make_api_call(
                self.client.get_aggs,
                ticker=ticker,
                multiplier=1,
                timespan='day',
                from_=start_date,
                to=end_date,
                limit=1
            )
            
            is_valid = hasattr(response, 'results') and response.results is not None
            self.logger.debug(f"Ticker {ticker} validation result: {is_valid}")
            return is_valid
            
        except Exception as e:
            self.logger.warning(f"Ticker validation failed for {ticker}: {e}")
            return False
    
    def get_rate_limit_status(self) -> Dict[str, Any]:
        """
        Get current rate limit status
        
        Returns:
            Dictionary with rate limit information
        """
        current_time = time.time()
        time_in_window = current_time - self.rate_limit.window_start
        calls_remaining = max(0, self.max_calls_per_minute - self.rate_limit.calls_made)
        time_until_reset = max(0, 60 - time_in_window)
        
        return {
            'calls_made': self.rate_limit.calls_made,
            'calls_remaining': calls_remaining,
            'window_start': self.rate_limit.window_start,
            'time_in_window': time_in_window,
            'time_until_reset': time_until_reset,
            'last_call_time': self.rate_limit.last_call_time
        }