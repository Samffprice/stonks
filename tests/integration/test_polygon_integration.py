"""
Integration tests for Polygon.io API client

These tests verify the Polygon client works correctly with the actual
configuration system and logging, using mocked API responses.
"""

import pytest
import time
import os
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

# Test if we can import the modules
try:
    import sys
    sys.path.insert(0, '/workspace/src')
    
    from trading_system.data_ingestion.polygon_client import (
        PolygonClient,
        PolygonAPIError,
        TimeFrame,
        OptionsContract,
        OptionsBar
    )
    from trading_system.config.settings import Config
    IMPORTS_AVAILABLE = True
except ImportError as e:
    IMPORTS_AVAILABLE = False
    import_error = str(e)


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason=f"Imports not available: {import_error if not IMPORTS_AVAILABLE else ''}")
class TestPolygonClientIntegration:
    """Integration tests for Polygon client"""
    
    def setup_method(self):
        """Set up test environment"""
        # Create a test config
        os.environ['POLYGON_API_KEY'] = 'test_key_12345'
        self.config = Config()
    
    def teardown_method(self):
        """Clean up test environment"""
        if 'POLYGON_API_KEY' in os.environ:
            del os.environ['POLYGON_API_KEY']
    
    @patch('trading_system.data_ingestion.polygon_client.RESTClient')
    def test_client_initialization_and_basic_functionality(self, mock_rest_client_class):
        """Test client initialization and basic functionality"""
        # Mock the REST client
        mock_client = Mock()
        mock_rest_client_class.return_value = mock_client
        
        # Create client
        client = PolygonClient(self.config)
        
        # Verify initialization
        assert client.config == self.config
        assert client.max_calls_per_minute == 5
        assert client.min_delay_seconds == 13
        assert client.rate_limit.calls_made == 0
        
        # Test rate limit status
        status = client.get_rate_limit_status()
        assert 'calls_made' in status
        assert 'calls_remaining' in status
        assert status['calls_made'] == 0
        assert status['calls_remaining'] == 5
    
    @patch('trading_system.data_ingestion.polygon_client.RESTClient')
    def test_options_contracts_workflow(self, mock_rest_client_class):
        """Test complete options contracts workflow"""
        # Mock the REST client and response
        mock_client = Mock()
        mock_rest_client_class.return_value = mock_client
        
        # Create mock contract data
        mock_contract = Mock()
        mock_contract.ticker = "O:AAPL240315C00150000"
        mock_contract.underlying_ticker = "AAPL"
        mock_contract.contract_type = "call"
        mock_contract.expiration_date = "2024-03-15"
        mock_contract.strike_price = 150.0
        mock_contract.exercise_style = "american"
        mock_contract.shares_per_contract = 100
        mock_contract.primary_exchange = "NASDAQ"
        mock_contract.created_at = "2024-01-01T00:00:00Z"
        mock_contract.updated_at = "2024-01-01T00:00:00Z"
        
        mock_response = Mock()
        mock_response.results = [mock_contract]
        mock_client.list_options_contracts.return_value = mock_response
        
        # Create client and fetch contracts
        client = PolygonClient(self.config)
        
        with patch('time.sleep'):  # Speed up test
            contracts = client.get_options_contracts("AAPL")
        
        # Verify results
        assert len(contracts) == 1
        contract = contracts[0]
        assert isinstance(contract, OptionsContract)
        assert contract.ticker == "O:AAPL240315C00150000"
        assert contract.underlying_ticker == "AAPL"
        assert contract.strike_price == 150.0
        
        # Verify API was called correctly
        mock_client.list_options_contracts.assert_called_once()
    
    @patch('trading_system.data_ingestion.polygon_client.RESTClient')
    def test_options_bars_workflow(self, mock_rest_client_class):
        """Test complete options bars workflow"""
        # Mock the REST client and response
        mock_client = Mock()
        mock_rest_client_class.return_value = mock_client
        
        # Create mock bar data
        mock_bar = Mock()
        mock_bar.t = 1640995200000
        mock_bar.o = 10.50
        mock_bar.h = 11.00
        mock_bar.l = 10.25
        mock_bar.c = 10.75
        mock_bar.v = 1000
        mock_bar.vw = 10.65
        mock_bar.n = 50
        
        mock_response = Mock()
        mock_response.results = [mock_bar]
        mock_client.get_aggs.return_value = mock_response
        
        # Create client and fetch bars
        client = PolygonClient(self.config)
        
        with patch('time.sleep'):  # Speed up test
            bars = client.get_options_bars(
                "O:AAPL240315C00150000",
                TimeFrame.DAY,
                "2024-01-01",
                "2024-01-31"
            )
        
        # Verify results
        assert len(bars) == 1
        bar = bars[0]
        assert isinstance(bar, OptionsBar)
        assert bar.ticker == "O:AAPL240315C00150000"
        assert bar.open == 10.50
        assert bar.close == 10.75
        
        # Verify API was called correctly
        mock_client.get_aggs.assert_called_once()
    
    @patch('trading_system.data_ingestion.polygon_client.RESTClient')
    def test_underlying_bars_workflow(self, mock_rest_client_class):
        """Test complete underlying bars workflow"""
        # Mock the REST client and response
        mock_client = Mock()
        mock_rest_client_class.return_value = mock_client
        
        # Create mock bar data
        mock_bar = Mock()
        mock_bar.t = 1640995200000
        mock_bar.o = 150.50
        mock_bar.h = 152.00
        mock_bar.l = 149.25
        mock_bar.c = 151.75
        mock_bar.v = 1000000
        mock_bar.vw = 151.25
        mock_bar.n = 5000
        
        mock_response = Mock()
        mock_response.results = [mock_bar]
        mock_client.get_aggs.return_value = mock_response
        
        # Create client and fetch bars
        client = PolygonClient(self.config)
        
        with patch('time.sleep'):  # Speed up test
            df = client.get_underlying_bars(
                "AAPL",
                TimeFrame.DAY,
                "2024-01-01",
                "2024-01-31"
            )
        
        # Verify results
        assert len(df) == 1
        assert 'open' in df.columns
        assert 'close' in df.columns
        assert 'volume' in df.columns
        assert df.iloc[0]['open'] == 150.50
        assert df.iloc[0]['close'] == 151.75
        
        # Verify API was called correctly
        mock_client.get_aggs.assert_called_once()
    
    @patch('trading_system.data_ingestion.polygon_client.RESTClient')
    def test_market_status_workflow(self, mock_rest_client_class):
        """Test market status workflow"""
        # Mock the REST client and response
        mock_client = Mock()
        mock_rest_client_class.return_value = mock_client
        
        # Create mock exchange data
        mock_exchange = Mock()
        mock_exchange.status = "open"
        mock_exchange.session = "regular"
        
        mock_response = Mock()
        mock_response.market = "open"
        mock_response.serverTime = "2024-01-01T15:30:00Z"
        mock_response.exchanges = {"NASDAQ": mock_exchange}
        
        mock_client.get_market_status.return_value = mock_response
        
        # Create client and get market status
        client = PolygonClient(self.config)
        
        with patch('time.sleep'):  # Speed up test
            status = client.get_market_status()
        
        # Verify results
        assert status['market'] == 'open'
        assert status['server_time'] == '2024-01-01T15:30:00Z'
        assert 'NASDAQ' in status['exchanges']
        assert status['exchanges']['NASDAQ']['status'] == 'open'
        
        # Verify API was called correctly
        mock_client.get_market_status.assert_called_once()
    
    @patch('trading_system.data_ingestion.polygon_client.RESTClient')
    def test_ticker_validation_workflow(self, mock_rest_client_class):
        """Test ticker validation workflow"""
        # Mock the REST client and response
        mock_client = Mock()
        mock_rest_client_class.return_value = mock_client
        
        # Test valid ticker
        mock_response_valid = Mock()
        mock_response_valid.results = [Mock()]  # Non-empty results
        mock_client.get_aggs.return_value = mock_response_valid
        
        client = PolygonClient(self.config)
        
        with patch('time.sleep'):  # Speed up test
            is_valid = client.validate_ticker("AAPL")
        
        assert is_valid is True
        
        # Test invalid ticker
        mock_response_invalid = Mock()
        mock_response_invalid.results = None  # Empty results
        mock_client.get_aggs.return_value = mock_response_invalid
        
        with patch('time.sleep'):  # Speed up test
            is_valid = client.validate_ticker("INVALID")
        
        assert is_valid is False
    
    @patch('trading_system.data_ingestion.polygon_client.RESTClient')
    def test_rate_limiting_behavior(self, mock_rest_client_class):
        """Test rate limiting behavior"""
        # Mock the REST client
        mock_client = Mock()
        mock_rest_client_class.return_value = mock_client
        mock_client.get_market_status.return_value = Mock()
        
        client = PolygonClient(self.config)
        
        # Test initial state
        status = client.get_rate_limit_status()
        assert status['calls_made'] == 0
        assert status['calls_remaining'] == 5
        
        # Simulate making calls
        with patch('time.sleep') as mock_sleep:
            client._make_api_call(mock_client.get_market_status)
            client._make_api_call(mock_client.get_market_status)
            client._make_api_call(mock_client.get_market_status)
        
        # Check rate limiting state
        status = client.get_rate_limit_status()
        assert status['calls_made'] == 3
        assert status['calls_remaining'] == 2
        
        # Verify sleep was called for rate limiting
        assert mock_sleep.call_count >= 2  # Should sleep for minimum delay between calls
    
    @patch('trading_system.data_ingestion.polygon_client.RESTClient')
    def test_error_handling_and_retries(self, mock_rest_client_class):
        """Test error handling and retry mechanism"""
        # Mock the REST client
        mock_client = Mock()
        mock_rest_client_class.return_value = mock_client
        
        # First two calls fail, third succeeds
        mock_client.get_market_status.side_effect = [
            Exception("Network error"),
            Exception("Server error"),
            Mock()  # Success
        ]
        
        client = PolygonClient(self.config)
        
        with patch('time.sleep'):  # Speed up test
            result = client._make_api_call(mock_client.get_market_status)
        
        # Verify retry behavior
        assert mock_client.get_market_status.call_count == 3
        assert result is not None
        
        # Test max retries exceeded
        mock_client.get_market_status.side_effect = Exception("Persistent error")
        
        with patch('time.sleep'):  # Speed up test
            with pytest.raises(PolygonAPIError, match="API call failed after 3 attempts"):
                client._make_api_call(mock_client.get_market_status)
    
    def test_config_integration(self):
        """Test integration with configuration system"""
        # Test with environment variable
        os.environ['POLYGON_API_KEY'] = 'test_api_key_from_env'
        config = Config()
        
        assert config.api.polygon_api_key == 'test_api_key_from_env'
        
        # Test that client uses the config
        with patch('trading_system.data_ingestion.polygon_client.RESTClient') as mock_rest_client:
            mock_rest_client.return_value = Mock()
            client = PolygonClient(config)
            
            # Verify client was initialized with correct API key
            mock_rest_client.assert_called_once_with(api_key='test_api_key_from_env')


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason=f"Imports not available: {import_error if not IMPORTS_AVAILABLE else ''}")
def test_module_imports():
    """Test that all required modules can be imported"""
    from trading_system.data_ingestion.polygon_client import (
        PolygonClient,
        PolygonAPIError,
        RateLimitExceededError,
        DataType,
        TimeFrame,
        OptionsContract,
        OptionsBar,
        RateLimitInfo
    )
    from trading_system.config.settings import Config
    
    # Verify classes can be instantiated
    assert DataType.TRADES.value == "trades"
    assert TimeFrame.DAY.value == "day"
    
    # Verify data classes work
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
    
    bar = OptionsBar(
        ticker="O:AAPL240315C00150000",
        timestamp=1640995200000,
        open=10.50,
        high=11.00,
        low=10.25,
        close=10.75,
        volume=1000
    )
    assert bar.volume == 1000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])