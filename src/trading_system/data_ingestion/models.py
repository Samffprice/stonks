"""
Data models for the trading system.

This module defines Pydantic models for various data types fetched from
the Polygon.io API and used throughout the trading system.
"""

from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator
import pandas as pd


class OHLCVData(BaseModel):
    """OHLCV (Open, High, Low, Close, Volume) data model."""
    
    symbol: str = Field(..., description="Stock symbol")
    timestamp: datetime = Field(..., description="Timestamp of the data point")
    open: Decimal = Field(..., description="Opening price")
    high: Decimal = Field(..., description="Highest price")
    low: Decimal = Field(..., description="Lowest price")
    close: Decimal = Field(..., description="Closing price")
    volume: int = Field(..., description="Trading volume")
    vwap: Optional[Decimal] = Field(None, description="Volume weighted average price")
    
    @field_validator('open', 'high', 'low', 'close', 'vwap', mode='before')
    @classmethod
    def validate_prices(cls, v):
        """Ensure prices are positive and convert to Decimal."""
        if v is None:
            return v
        if isinstance(v, (int, float)):
            v = Decimal(str(v))
        if v <= 0:
            raise ValueError("Prices must be positive")
        return v
    
    @field_validator('volume', mode='before')
    @classmethod
    def validate_volume(cls, v):
        """Ensure volume is non-negative."""
        if v < 0:
            raise ValueError("Volume must be non-negative")
        return v


class NewsArticle(BaseModel):
    """News article data model."""
    
    id: str = Field(..., description="Unique article identifier")
    title: str = Field(..., description="Article title")
    description: Optional[str] = Field(None, description="Article description")
    author: Optional[str] = Field(None, description="Article author")
    published_utc: datetime = Field(..., description="Publication timestamp")
    article_url: Optional[str] = Field(None, description="URL to full article")
    tickers: List[str] = Field(default_factory=list, description="Related stock symbols")
    keywords: List[str] = Field(default_factory=list, description="Article keywords")
    sentiment_score: Optional[float] = Field(None, description="Sentiment analysis score")
    
    @field_validator('sentiment_score')
    @classmethod
    def validate_sentiment(cls, v):
        """Ensure sentiment score is between -1 and 1."""
        if v is not None and not (-1 <= v <= 1):
            raise ValueError("Sentiment score must be between -1 and 1")
        return v


class OptionsContract(BaseModel):
    """Options contract data model."""
    
    contract_symbol: str = Field(..., description="Options contract symbol")
    underlying_ticker: str = Field(..., description="Underlying stock symbol")
    strike_price: Decimal = Field(..., description="Strike price")
    expiration_date: date = Field(..., description="Expiration date")
    option_type: str = Field(..., description="Option type: 'call' or 'put'")
    last_price: Optional[Decimal] = Field(None, description="Last traded price")
    bid: Optional[Decimal] = Field(None, description="Bid price")
    ask: Optional[Decimal] = Field(None, description="Ask price")
    volume: Optional[int] = Field(None, description="Daily volume")
    open_interest: Optional[int] = Field(None, description="Open interest")
    implied_volatility: Optional[float] = Field(None, description="Implied volatility")
    delta: Optional[float] = Field(None, description="Delta greek")
    gamma: Optional[float] = Field(None, description="Gamma greek")
    theta: Optional[float] = Field(None, description="Theta greek")
    vega: Optional[float] = Field(None, description="Vega greek")
    
    @field_validator('option_type')
    @classmethod
    def validate_option_type(cls, v):
        """Ensure option type is valid."""
        if v.lower() not in ['call', 'put']:
            raise ValueError("Option type must be 'call' or 'put'")
        return v.lower()
    
    @field_validator('strike_price', 'last_price', 'bid', 'ask', mode='before')
    @classmethod
    def validate_prices(cls, v):
        """Validate price fields."""
        if v is None:
            return v
        if isinstance(v, (int, float)):
            v = Decimal(str(v))
        if v < 0:
            raise ValueError("Prices must be non-negative")
        return v


class TechnicalIndicator(BaseModel):
    """Technical indicator data model."""
    
    symbol: str = Field(..., description="Stock symbol")
    timestamp: datetime = Field(..., description="Timestamp")
    indicator_name: str = Field(..., description="Name of the technical indicator")
    value: float = Field(..., description="Indicator value")
    period: Optional[int] = Field(None, description="Period used for calculation")
    
    @field_validator('indicator_name')
    @classmethod
    def validate_indicator_name(cls, v):
        """Validate indicator name."""
        valid_indicators = [
            'sma', 'ema', 'rsi', 'macd', 'bb_upper', 'bb_lower', 'bb_middle',
            'atr', 'stoch_k', 'stoch_d', 'cci', 'williams_r'
        ]
        if v.lower() not in valid_indicators:
            raise ValueError(f"Invalid indicator: {v}. Must be one of {valid_indicators}")
        return v.lower()


class MarketData(BaseModel):
    """Aggregated market data model."""
    
    symbol: str = Field(..., description="Stock symbol")
    data_date: date = Field(..., description="Data date")
    ohlcv: OHLCVData = Field(..., description="OHLCV data")
    news_articles: List[NewsArticle] = Field(default_factory=list, description="Related news")
    options_contracts: List[OptionsContract] = Field(default_factory=list, description="Options data")
    technical_indicators: List[TechnicalIndicator] = Field(default_factory=list, description="Technical indicators")
    market_cap: Optional[int] = Field(None, description="Market capitalization")
    sector: Optional[str] = Field(None, description="Company sector")


class APIResponse(BaseModel):
    """Generic API response wrapper."""
    
    status: str = Field(..., description="Response status")
    request_id: Optional[str] = Field(None, description="Request identifier")
    next_url: Optional[str] = Field(None, description="URL for pagination")
    count: Optional[int] = Field(None, description="Number of results")
    results: List[Dict[str, Any]] = Field(default_factory=list, description="Response data")
    

class RateLimitInfo(BaseModel):
    """Rate limiting information."""
    
    calls_remaining: int = Field(..., description="API calls remaining")
    reset_time: datetime = Field(..., description="When rate limit resets")
    calls_per_minute: int = Field(default=5, description="Calls allowed per minute")
    
    def should_wait(self) -> bool:
        """Check if we should wait before making another call."""
        return self.calls_remaining <= 0
    
    def seconds_until_reset(self) -> float:
        """Calculate seconds until rate limit reset."""
        now = datetime.utcnow()
        if self.reset_time > now:
            return (self.reset_time - now).total_seconds()
        return 0.0


def convert_to_dataframe(data_list: List[BaseModel]) -> pd.DataFrame:
    """Convert a list of Pydantic models to a pandas DataFrame."""
    if not data_list:
        return pd.DataFrame()
    
    # Convert to dict and then to DataFrame
    data_dicts = [item.dict() for item in data_list]
    return pd.DataFrame(data_dicts)


def validate_ticker_symbol(symbol: str) -> str:
    """Validate and normalize ticker symbol."""
    if not symbol or not isinstance(symbol, str):
        raise ValueError("Symbol must be a non-empty string")
    
    symbol = symbol.upper().strip()
    
    # Basic validation - alphanumeric characters only
    if not symbol.replace('.', '').replace('-', '').isalnum():
        raise ValueError("Symbol contains invalid characters")
    
    if len(symbol) > 10:
        raise ValueError("Symbol too long")
    
    return symbol