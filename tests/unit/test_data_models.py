"""
Unit tests for data models.

Tests the Pydantic models and validation logic for various data types
used throughout the trading system.
"""

import pytest
from datetime import datetime, date
from decimal import Decimal

try:
    from src.trading_system.data_ingestion.models import (
        OHLCVData, NewsArticle, OptionsContract, TechnicalIndicator,
        MarketData, APIResponse, RateLimitInfo,
        convert_to_dataframe, validate_ticker_symbol
    )
    MODELS_AVAILABLE = True
except ImportError:
    MODELS_AVAILABLE = False


@pytest.mark.skipif(not MODELS_AVAILABLE, reason="Data models not available")
class TestOHLCVData:
    """Test OHLCV data model."""
    
    def test_valid_ohlcv_creation(self):
        """Test creating valid OHLCV data."""
        ohlcv = OHLCVData(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 15, 16, 0, 0),
            open=Decimal("150.00"),
            high=Decimal("155.00"),
            low=Decimal("149.00"),
            close=Decimal("154.00"),
            volume=1000000
        )
        
        assert ohlcv.symbol == "AAPL"
        assert ohlcv.open == Decimal("150.00")
        assert ohlcv.volume == 1000000
    
    def test_ohlcv_price_validation(self):
        """Test price validation in OHLCV data."""
        with pytest.raises(ValueError, match="Prices must be positive"):
            OHLCVData(
                symbol="AAPL",
                timestamp=datetime.now(),
                open=Decimal("-150.00"),  # Invalid negative price
                high=Decimal("155.00"),
                low=Decimal("149.00"),
                close=Decimal("154.00"),
                volume=1000000
            )
    
    def test_ohlcv_volume_validation(self):
        """Test volume validation."""
        with pytest.raises(ValueError, match="Volume must be non-negative"):
            OHLCVData(
                symbol="AAPL",
                timestamp=datetime.now(),
                open=Decimal("150.00"),
                high=Decimal("155.00"),
                low=Decimal("149.00"),
                close=Decimal("154.00"),
                volume=-1000  # Invalid negative volume
            )
    
    def test_ohlcv_automatic_decimal_conversion(self):
        """Test automatic conversion of floats to Decimal."""
        ohlcv = OHLCVData(
            symbol="AAPL",
            timestamp=datetime.now(),
            open=150.00,  # Float input
            high=155.00,
            low=149.00,
            close=154.00,
            volume=1000000
        )
        
        assert isinstance(ohlcv.open, Decimal)
        assert ohlcv.open == Decimal("150.00")


@pytest.mark.skipif(not MODELS_AVAILABLE, reason="Data models not available")
class TestNewsArticle:
    """Test news article model."""
    
    def test_valid_news_creation(self):
        """Test creating valid news article."""
        article = NewsArticle(
            id="test-123",
            title="Test Article",
            published_utc=datetime(2024, 1, 15, 12, 0, 0),
            tickers=["AAPL", "MSFT"],
            keywords=["earnings", "tech"]
        )
        
        assert article.id == "test-123"
        assert article.title == "Test Article"
        assert len(article.tickers) == 2
    
    def test_sentiment_validation(self):
        """Test sentiment score validation."""
        # Valid sentiment
        article = NewsArticle(
            id="test-123",
            title="Test Article",
            published_utc=datetime.now(),
            sentiment_score=0.5
        )
        assert article.sentiment_score == 0.5
        
        # Invalid sentiment - too high
        with pytest.raises(ValueError, match="Sentiment score must be between -1 and 1"):
            NewsArticle(
                id="test-123",
                title="Test Article",
                published_utc=datetime.now(),
                sentiment_score=1.5
            )


@pytest.mark.skipif(not MODELS_AVAILABLE, reason="Data models not available")
class TestOptionsContract:
    """Test options contract model."""
    
    def test_valid_options_creation(self):
        """Test creating valid options contract."""
        contract = OptionsContract(
            contract_symbol="AAPL240119C00150000",
            underlying_ticker="AAPL",
            strike_price=Decimal("150.00"),
            expiration_date=date(2024, 1, 19),
            option_type="call",
            last_price=Decimal("5.50")
        )
        
        assert contract.underlying_ticker == "AAPL"
        assert contract.option_type == "call"
        assert contract.strike_price == Decimal("150.00")
    
    def test_option_type_validation(self):
        """Test option type validation."""
        # Valid types
        for option_type in ["call", "put", "CALL", "PUT"]:
            contract = OptionsContract(
                contract_symbol="TEST",
                underlying_ticker="AAPL",
                strike_price=Decimal("150.00"),
                expiration_date=date(2024, 1, 19),
                option_type=option_type
            )
            assert contract.option_type in ["call", "put"]
        
        # Invalid type
        with pytest.raises(ValueError, match="Option type must be 'call' or 'put'"):
            OptionsContract(
                contract_symbol="TEST",
                underlying_ticker="AAPL",
                strike_price=Decimal("150.00"),
                expiration_date=date(2024, 1, 19),
                option_type="invalid"
            )


@pytest.mark.skipif(not MODELS_AVAILABLE, reason="Data models not available")
class TestTechnicalIndicator:
    """Test technical indicator model."""
    
    def test_valid_indicator_creation(self):
        """Test creating valid technical indicator."""
        indicator = TechnicalIndicator(
            symbol="AAPL",
            timestamp=datetime.now(),
            indicator_name="sma",
            value=150.25,
            period=20
        )
        
        assert indicator.symbol == "AAPL"
        assert indicator.indicator_name == "sma"
        assert indicator.value == 150.25
    
    def test_indicator_name_validation(self):
        """Test indicator name validation."""
        # Valid indicator
        indicator = TechnicalIndicator(
            symbol="AAPL",
            timestamp=datetime.now(),
            indicator_name="RSI",  # Should be normalized to lowercase
            value=50.0
        )
        assert indicator.indicator_name == "rsi"
        
        # Invalid indicator
        with pytest.raises(ValueError, match="Invalid indicator"):
            TechnicalIndicator(
                symbol="AAPL",
                timestamp=datetime.now(),
                indicator_name="invalid_indicator",
                value=50.0
            )


@pytest.mark.skipif(not MODELS_AVAILABLE, reason="Data models not available")
class TestRateLimitInfo:
    """Test rate limit information model."""
    
    def test_should_wait_logic(self):
        """Test rate limiting logic."""
        # Should not wait when calls remaining
        rate_limit = RateLimitInfo(
            calls_remaining=3,
            reset_time=datetime.utcnow()
        )
        assert not rate_limit.should_wait()
        
        # Should wait when no calls remaining
        rate_limit = RateLimitInfo(
            calls_remaining=0,
            reset_time=datetime.utcnow()
        )
        assert rate_limit.should_wait()
    
    def test_seconds_until_reset(self):
        """Test calculation of seconds until reset."""
        from datetime import timedelta
        
        # Future reset time
        future_time = datetime.utcnow() + timedelta(seconds=60)
        rate_limit = RateLimitInfo(
            calls_remaining=5,
            reset_time=future_time
        )
        seconds = rate_limit.seconds_until_reset()
        assert 50 <= seconds <= 70  # Allow some timing variance
        
        # Past reset time
        past_time = datetime.utcnow() - timedelta(seconds=60)
        rate_limit = RateLimitInfo(
            calls_remaining=5,
            reset_time=past_time
        )
        assert rate_limit.seconds_until_reset() == 0.0


@pytest.mark.skipif(not MODELS_AVAILABLE, reason="Data models not available")
class TestUtilityFunctions:
    """Test utility functions."""
    
    def test_validate_ticker_symbol(self):
        """Test ticker symbol validation."""
        # Valid symbols
        assert validate_ticker_symbol("AAPL") == "AAPL"
        assert validate_ticker_symbol("aapl") == "AAPL"
        assert validate_ticker_symbol(" MSFT ") == "MSFT"
        assert validate_ticker_symbol("BRK.A") == "BRK.A"
        
        # Invalid symbols
        with pytest.raises(ValueError, match="Symbol must be a non-empty string"):
            validate_ticker_symbol("")
        
        with pytest.raises(ValueError, match="Symbol contains invalid characters"):
            validate_ticker_symbol("AAPL@")
        
        with pytest.raises(ValueError, match="Symbol too long"):
            validate_ticker_symbol("VERYLONGSYMBOL")
    
    def test_convert_to_dataframe(self):
        """Test conversion of models to DataFrame."""
        try:
            import pandas as pd
            
            # Test with data
            ohlcv_list = [
                OHLCVData(
                    symbol="AAPL",
                    timestamp=datetime(2024, 1, 15),
                    open=Decimal("150.00"),
                    high=Decimal("155.00"),
                    low=Decimal("149.00"),
                    close=Decimal("154.00"),
                    volume=1000000
                ),
                OHLCVData(
                    symbol="AAPL",
                    timestamp=datetime(2024, 1, 16),
                    open=Decimal("154.00"),
                    high=Decimal("158.00"),
                    low=Decimal("153.00"),
                    close=Decimal("157.00"),
                    volume=1200000
                )
            ]
            
            df = convert_to_dataframe(ohlcv_list)
            assert len(df) == 2
            assert "symbol" in df.columns
            assert df.iloc[0]["symbol"] == "AAPL"
            
            # Test with empty list
            empty_df = convert_to_dataframe([])
            assert len(empty_df) == 0
            
        except ImportError:
            pytest.skip("pandas not available")


if __name__ == "__main__":
    pytest.main([__file__])