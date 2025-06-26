"""
Unit tests for Polygon.io API client

Tests cover:
- Rate limiting functionality
- API call error handling and retries
- Data validation and transformation
- Configuration validation
- Market status retrieval
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from dataclasses import dataclass

# Skip if dependencies not available
pytest = pytest.importorskip("pytest")

try:
    from src.trading_system.data_ingestion.polygon_client import (
        PolygonClient,
        PolygonAPIError,
        RateLimitExceededError,
        DataType,
        TimeFrame,
        OptionsContract,
        OptionsBar,
        RateLimitInfo
    )
    from src.trading_system.config.config import Config, APIConfig, DataConfig, TradingConfig, MLConfig, LoggingConfig
except ImportError as e:
    pytest.skip(f"Dependencies not available: {e}", allow_module_level=True)


@pytest.fixture
def mock_config():
    """Create a mock configuration for testing"""
    return Config(
        api=APIConfig(
            polygon_api_key="test_api_key_12345",
            polygon_rate_limit=5,
            polygon_max_retries=3
        ),
        data=DataConfig(),
        trading=TradingConfig(),
        ml=MLConfig(),
        logging=LoggingConfig()
    )


@pytest.fixture
def mock_polygon_rest_client():
    """Create a mock Polygon REST client"""
    with patch('src.trading_system.data_ingestion.polygon_client.RESTClient') as mock_client_class:
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        yield mock_client


@pytest.fixture
def polygon_client(mock_config, mock_polygon_rest_client):
    """Create a PolygonClient instance for testing"""
    return PolygonClient(mock_config)


class TestPolygonClientInitialization:
    """Test Polygon client initialization"""
    
    def test_successful_initialization(self, mock_config, mock_polygon_rest_client):
        """Test successful client initialization"""
        client = PolygonClient(mock_config)
        
        assert client.config == mock_config
        assert client.max_calls_per_minute == 5
        assert client.min_delay_seconds == 13
        assert client.rate_limit.calls_made == 0
        assert client.client is not None
    
    def test_initialization_with_invalid_api_key(self, mock_config):
        """Test initialization with invalid API key"""
        with patch('src.trading_system.data_ingestion.polygon_client.RESTClient') as mock_client_class:
            mock_client_class.side_effect = Exception("Invalid API key")
            
            with pytest.raises(PolygonAPIError, match="Client initialization failed"):
                PolygonClient(mock_config)


class TestRateLimiting:
    """Test rate limiting functionality"""
    
    def test_rate_limit_tracking(self, polygon_client):
        """Test rate limit tracking"""
        # Initially no calls made
        status = polygon_client.get_rate_limit_status()
        assert status['calls_made'] == 0
        assert status['calls_remaining'] == 5
        
        # Simulate calls
        polygon_client.rate_limit.calls_made = 3
        polygon_client.rate_limit.window_start = time.time()
        
        status = polygon_client.get_rate_limit_status()
        assert status['calls_made'] == 3
        assert status['calls_remaining'] == 2
    
    def test_rate_limit_window_reset(self, polygon_client):
        """Test rate limit window reset after 60 seconds"""
        # Set up rate limit state
        polygon_client.rate_limit.calls_made = 5
        polygon_client.rate_limit.window_start = time.time() - 61  # 61 seconds ago
        
        # Check rate limit should reset the window
        polygon_client._check_rate_limit()
        
        assert polygon_client.rate_limit.calls_made == 0
        assert polygon_client.rate_limit.window_start > time.time() - 1
    
    def test_minimum_delay_enforcement(self, polygon_client):
        """Test minimum delay between calls"""
        polygon_client.rate_limit.last_call_time = time.time()
        
        # Mock time.sleep to capture sleep calls
        with patch('time.sleep') as mock_sleep:
            polygon_client._check_rate_limit()
            
            # Should have slept for approximately min_delay_seconds
            mock_sleep.assert_called_once()
            sleep_time = mock_sleep.call_args[0][0]
            assert 12 <= sleep_time <= 13  # Allow for small timing differences


class TestAPICallHandling:
    """Test API call handling with retries and error handling"""
    
    def test_successful_api_call(self, polygon_client):
        """Test successful API call"""
        mock_func = Mock(return_value="success")
        
        result = polygon_client._make_api_call(mock_func, "arg1", kwarg1="value1")
        
        assert result == "success"
        mock_func.assert_called_once_with("arg1", kwarg1="value1")
        assert polygon_client.rate_limit.calls_made == 1
    
    def test_api_call_with_retries(self, polygon_client):
        """Test API call with retries on failure"""
        mock_func = Mock(side_effect=[Exception("Network error"), Exception("Server error"), "success"])
        
        with patch('time.sleep'):  # Mock sleep to speed up test
            result = polygon_client._make_api_call(mock_func)
        
        assert result == "success"
        assert mock_func.call_count == 3
        assert polygon_client.rate_limit.calls_made == 1  # Only successful calls count
    
    def test_api_call_max_retries_exceeded(self, polygon_client):
        """Test API call when max retries exceeded"""
        mock_func = Mock(side_effect=Exception("Persistent error"))
        
        with patch('time.sleep'):  # Mock sleep to speed up test
            with pytest.raises(PolygonAPIError, match="API call failed after 3 attempts"):
                polygon_client._make_api_call(mock_func)
        
        assert mock_func.call_count == 3


class TestOptionsContracts:
    """Test options contract retrieval"""
    
    def test_get_options_contracts_success(self, polygon_client, mock_polygon_rest_client):
        """Test successful options contract retrieval"""
        # Mock response data
        mock_contract_data = Mock()
        mock_contract_data.ticker = "O:AAPL240315C00150000"
        mock_contract_data.underlying_ticker = "AAPL"
        mock_contract_data.contract_type = "call"
        mock_contract_data.expiration_date = "2024-03-15"
        mock_contract_data.strike_price = 150.0
        mock_contract_data.exercise_style = "american"
        mock_contract_data.shares_per_contract = 100
        mock_contract_data.primary_exchange = "NASDAQ"
        mock_contract_data.created_at = "2024-01-01T00:00:00Z"
        mock_contract_data.updated_at = "2024-01-01T00:00:00Z"
        
        mock_response = Mock()
        mock_response.results = [mock_contract_data]
        mock_polygon_rest_client.list_options_contracts.return_value = mock_response
        
        with patch('time.sleep'):  # Mock sleep for rate limiting
            contracts = polygon_client.get_options_contracts("AAPL")
        
        assert len(contracts) == 1
        contract = contracts[0]
        assert isinstance(contract, OptionsContract)
        assert contract.ticker == "O:AAPL240315C00150000"
        assert contract.underlying_ticker == "AAPL"
        assert contract.contract_type == "call"
        assert contract.strike_price == 150.0
    
    def test_get_options_contracts_with_filters(self, polygon_client, mock_polygon_rest_client):
        """Test options contract retrieval with filters"""
        mock_response = Mock()
        mock_response.results = []
        mock_polygon_rest_client.list_options_contracts.return_value = mock_response
        
        with patch('time.sleep'):
            contracts = polygon_client.get_options_contracts(
                underlying_ticker="AAPL",
                expiration_date="2024-03-15",
                contract_type="call",
                strike_price_gte=140.0,
                strike_price_lte=160.0
            )
        
        mock_polygon_rest_client.list_options_contracts.assert_called_once_with(
            underlying_ticker="AAPL",
            expiration_date="2024-03-15",
            contract_type="call",
            strike_price_gte=140.0,
            strike_price_lte=160.0,
            expired=False,
            limit=1000
        )
        assert contracts == []
    
    def test_get_options_contracts_api_error(self, polygon_client, mock_polygon_rest_client):
        """Test options contract retrieval with API error"""
        mock_polygon_rest_client.list_options_contracts.side_effect = Exception("API Error")
        
        with patch('time.sleep'):
            with pytest.raises(PolygonAPIError, match="Failed to get options contracts"):
                polygon_client.get_options_contracts("AAPL")


class TestOptionsBars:
    """Test options bars retrieval"""
    
    def test_get_options_bars_success(self, polygon_client, mock_polygon_rest_client):
        """Test successful options bars retrieval"""
        # Mock bar data
        mock_bar_data = Mock()
        mock_bar_data.t = 1640995200000  # Unix timestamp in milliseconds
        mock_bar_data.o = 10.50
        mock_bar_data.h = 11.00
        mock_bar_data.l = 10.25
        mock_bar_data.c = 10.75
        mock_bar_data.v = 1000
        mock_bar_data.vw = 10.65
        mock_bar_data.n = 50
        
        mock_response = Mock()
        mock_response.results = [mock_bar_data]
        mock_polygon_rest_client.get_aggs.return_value = mock_response
        
        with patch('time.sleep'):
            bars = polygon_client.get_options_bars(
                "O:AAPL240315C00150000",
                TimeFrame.DAY,
                "2024-01-01",
                "2024-01-31"
            )
        
        assert len(bars) == 1
        bar = bars[0]
        assert isinstance(bar, OptionsBar)
        assert bar.ticker == "O:AAPL240315C00150000"
        assert bar.timestamp == 1640995200000
        assert bar.open == 10.50
        assert bar.close == 10.75
        assert bar.volume == 1000
    
    def test_get_options_bars_empty_response(self, polygon_client, mock_polygon_rest_client):
        """Test options bars retrieval with empty response"""
        mock_response = Mock()
        mock_response.results = None
        mock_polygon_rest_client.get_aggs.return_value = mock_response
        
        with patch('time.sleep'):
            bars = polygon_client.get_options_bars(
                "O:AAPL240315C00150000",
                TimeFrame.DAY,
                "2024-01-01",
                "2024-01-31"
            )
        
        assert bars == []


class TestUnderlyingBars:
    """Test underlying stock bars retrieval"""
    
    def test_get_underlying_bars_success(self, polygon_client, mock_polygon_rest_client):
        """Test successful underlying bars retrieval"""
        # Mock bar data
        mock_bar_data = Mock()
        mock_bar_data.t = 1640995200000
        mock_bar_data.o = 150.50
        mock_bar_data.h = 152.00
        mock_bar_data.l = 149.25
        mock_bar_data.c = 151.75
        mock_bar_data.v = 1000000
        mock_bar_data.vw = 151.25
        mock_bar_data.n = 5000
        
        mock_response = Mock()
        mock_response.results = [mock_bar_data]
        mock_polygon_rest_client.get_aggs.return_value = mock_response
        
        with patch('time.sleep'):
            df = polygon_client.get_underlying_bars(
                "AAPL",
                TimeFrame.DAY,
                "2024-01-01",
                "2024-01-31"
            )
        
        assert len(df) == 1
        assert 'open' in df.columns
        assert 'close' in df.columns
        assert 'volume' in df.columns
        assert df.iloc[0]['open'] == 150.50
        assert df.iloc[0]['close'] == 151.75
    
    def test_get_underlying_bars_empty_response(self, polygon_client, mock_polygon_rest_client):
        """Test underlying bars retrieval with empty response"""
        mock_response = Mock()
        mock_response.results = None
        mock_polygon_rest_client.get_aggs.return_value = mock_response
        
        with patch('time.sleep'):
            df = polygon_client.get_underlying_bars(
                "AAPL",
                TimeFrame.DAY,
                "2024-01-01",
                "2024-01-31"
            )
        
        assert df.empty


class TestMarketStatus:
    """Test market status functionality"""
    
    def test_get_market_status_success(self, polygon_client, mock_polygon_rest_client):
        """Test successful market status retrieval"""
        mock_exchange_data = Mock()
        mock_exchange_data.status = "open"
        mock_exchange_data.session = "regular"
        
        mock_response = Mock()
        mock_response.market = "open"
        mock_response.serverTime = "2024-01-01T15:30:00Z"
        mock_response.exchanges = {"NASDAQ": mock_exchange_data}
        
        mock_polygon_rest_client.get_market_status.return_value = mock_response
        
        with patch('time.sleep'):
            status = polygon_client.get_market_status()
        
        assert status['market'] == 'open'
        assert status['server_time'] == '2024-01-01T15:30:00Z'
        assert 'NASDAQ' in status['exchanges']
        assert status['exchanges']['NASDAQ']['status'] == 'open'
    
    def test_get_market_status_api_error(self, polygon_client, mock_polygon_rest_client):
        """Test market status retrieval with API error"""
        mock_polygon_rest_client.get_market_status.side_effect = Exception("API Error")
        
        with patch('time.sleep'):
            with pytest.raises(PolygonAPIError, match="Failed to get market status"):
                polygon_client.get_market_status()


class TestTickerValidation:
    """Test ticker validation functionality"""
    
    def test_validate_ticker_success(self, polygon_client, mock_polygon_rest_client):
        """Test successful ticker validation"""
        mock_response = Mock()
        mock_response.results = [Mock()]  # Non-empty results indicate valid ticker
        mock_polygon_rest_client.get_aggs.return_value = mock_response
        
        with patch('time.sleep'):
            is_valid = polygon_client.validate_ticker("AAPL")
        
        assert is_valid is True
    
    def test_validate_ticker_invalid(self, polygon_client, mock_polygon_rest_client):
        """Test ticker validation for invalid ticker"""
        mock_response = Mock()
        mock_response.results = None  # Empty results indicate invalid ticker
        mock_polygon_rest_client.get_aggs.return_value = mock_response
        
        with patch('time.sleep'):
            is_valid = polygon_client.validate_ticker("INVALID")
        
        assert is_valid is False
    
    def test_validate_ticker_api_error(self, polygon_client, mock_polygon_rest_client):
        """Test ticker validation with API error"""
        mock_polygon_rest_client.get_aggs.side_effect = Exception("API Error")
        
        with patch('time.sleep'):
            is_valid = polygon_client.validate_ticker("AAPL")
        
        assert is_valid is False


class TestDataClasses:
    """Test data class functionality"""
    
    def test_options_contract_creation(self):
        """Test OptionsContract data class creation"""
        contract = OptionsContract(
            ticker="O:AAPL240315C00150000",
            underlying_ticker="AAPL",
            contract_type="call",
            expiration_date="2024-03-15",
            strike_price=150.0,
            exercise_style="american",
            shares_per_contract=100,
            primary_exchange="NASDAQ"
        )
        
        assert contract.ticker == "O:AAPL240315C00150000"
        assert contract.underlying_ticker == "AAPL"
        assert contract.contract_type == "call"
        assert contract.strike_price == 150.0
    
    def test_options_bar_creation(self):
        """Test OptionsBar data class creation"""
        bar = OptionsBar(
            ticker="O:AAPL240315C00150000",
            timestamp=1640995200000,
            open=10.50,
            high=11.00,
            low=10.25,
            close=10.75,
            volume=1000,
            vwap=10.65,
            transactions=50
        )
        
        assert bar.ticker == "O:AAPL240315C00150000"
        assert bar.timestamp == 1640995200000
        assert bar.open == 10.50
        assert bar.volume == 1000
    
    def test_rate_limit_info_creation(self):
        """Test RateLimitInfo data class creation"""
        info = RateLimitInfo(
            calls_made=3,
            window_start=time.time(),
            last_call_time=time.time()
        )
        
        assert info.calls_made == 3
        assert info.window_start > 0
        assert info.last_call_time > 0


class TestEnums:
    """Test enum functionality"""
    
    def test_data_type_enum(self):
        """Test DataType enum values"""
        assert DataType.TRADES.value == "trades"
        assert DataType.QUOTES.value == "quotes"
        assert DataType.BARS.value == "bars"
        assert DataType.OPTIONS_CONTRACTS.value == "options_contracts"
        assert DataType.DAILY_BARS.value == "daily_bars"
    
    def test_time_frame_enum(self):
        """Test TimeFrame enum values"""
        assert TimeFrame.MINUTE.value == "minute"
        assert TimeFrame.HOUR.value == "hour"
        assert TimeFrame.DAY.value == "day"
        assert TimeFrame.WEEK.value == "week"
        assert TimeFrame.MONTH.value == "month"


if __name__ == "__main__":
    pytest.main([__file__])