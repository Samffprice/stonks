"""
Unit tests for Polygon API client.

Tests the PolygonClient functionality including rate limiting,
error handling, and data retrieval methods.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, date, timedelta
import time

try:
    from src.trading_system.data_ingestion.polygon_client import (
        PolygonClient, PolygonAPIError, RateLimiter
    )
    from src.trading_system.data_ingestion.models import (
        APIResponse, OHLCVData, NewsArticle, OptionsContract, TechnicalIndicator
    )
    from src.trading_system.config.settings import Config
    CLIENT_AVAILABLE = True
except ImportError:
    CLIENT_AVAILABLE = False


@pytest.mark.skipif(not CLIENT_AVAILABLE, reason="Polygon client not available")
class TestRateLimiter:
    """Test rate limiter functionality."""
    
    def test_rate_limiter_creation(self):
        """Test creating rate limiter."""
        limiter = RateLimiter(calls_per_minute=5)
        assert limiter.calls_per_minute == 5
        assert len(limiter.call_times) == 0
    
    def test_rate_limiter_under_limit(self):
        """Test rate limiter when under limit."""
        limiter = RateLimiter(calls_per_minute=5)
        
        # Should not wait when under limit
        start_time = time.time()
        limiter.wait_if_needed()
        end_time = time.time()
        
        # Should complete quickly
        assert end_time - start_time < 0.1
        
        # Record call
        limiter.record_call()
        assert len(limiter.call_times) == 1
    
    def test_rate_limiter_at_limit(self):
        """Test rate limiter when at limit."""
        limiter = RateLimiter(calls_per_minute=2)  # Low limit for testing
        
        # Fill up the rate limit
        for _ in range(2):
            limiter.record_call()
        
        # Mock time to avoid actually waiting
        with patch('time.sleep') as mock_sleep:
            with patch('time.time', side_effect=[60, 60, 120]):  # Simulate time passage
                limiter.wait_if_needed()
                mock_sleep.assert_called()
    
    def test_rate_limit_info(self):
        """Test rate limit information."""
        limiter = RateLimiter(calls_per_minute=5)
        
        # No calls made yet
        info = limiter.get_info()
        assert info.calls_remaining == 5
        
        # Make some calls
        limiter.record_call()
        limiter.record_call()
        
        info = limiter.get_info()
        assert info.calls_remaining == 3


@pytest.mark.skipif(not CLIENT_AVAILABLE, reason="Polygon client not available")
class TestPolygonClient:
    """Test Polygon API client."""
    
    @pytest.fixture
    def mock_config(self):
        """Create mock configuration."""
        config = Mock(spec=Config)
        config.api = Mock()
        config.api.polygon_api_key = "test_api_key"
        config.api.polygon_rate_limit = 5
        config.api.polygon_max_retries = 3
        return config
    
    @pytest.fixture
    def client(self, mock_config):
        """Create Polygon client with mock config."""
        return PolygonClient(mock_config)
    
    def test_client_creation(self, mock_config):
        """Test creating Polygon client."""
        client = PolygonClient(mock_config)
        assert client.api_key == "test_api_key"
        assert client.base_url == "https://api.polygon.io"
        assert client.rate_limiter.calls_per_minute == 5
    
    def test_client_requires_api_key(self, mock_config):
        """Test that client requires API key."""
        mock_config.api.polygon_api_key = ""
        
        with pytest.raises(ValueError, match="Polygon API key is required"):
            PolygonClient(mock_config)
    
    @patch('requests.Session.get')
    def test_successful_request(self, mock_get, client):
        """Test successful API request."""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "OK",
            "results": [{"test": "data"}],
            "count": 1
        }
        mock_get.return_value = mock_response
        
        # Make request
        response = client._make_request("/test/endpoint", {"param": "value"})
        
        # Verify response
        assert response.status == "OK"
        assert len(response.results) == 1
        assert response.count == 1
        
        # Verify request was made correctly
        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        assert "apikey" in kwargs["params"]
        assert kwargs["params"]["apikey"] == "test_api_key"
        assert kwargs["params"]["param"] == "value"
    
    @patch('requests.Session.get')
    def test_api_error_handling(self, mock_get, client):
        """Test API error handling."""
        # Mock error response
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"error": "Bad request"}
        mock_get.return_value = mock_response
        
        # Should raise PolygonAPIError
        with pytest.raises(PolygonAPIError, match="API request failed with status 400"):
            client._make_request("/test/endpoint")
    
    @patch('requests.Session.get')
    def test_network_error_handling(self, mock_get, client):
        """Test network error handling."""
        # Mock network error
        import requests
        mock_get.side_effect = requests.exceptions.ConnectionError("Network error")
        
        # Should raise PolygonAPIError
        with pytest.raises(PolygonAPIError, match="Request failed"):
            client._make_request("/test/endpoint")
    
    @patch('requests.Session.get')
    def test_retry_mechanism(self, mock_get, client):
        """Test retry mechanism for transient errors."""
        # Mock responses: first two fail with 500, third succeeds
        responses = [
            Mock(status_code=500),
            Mock(status_code=500),
            Mock(status_code=200, **{'json.return_value': {"status": "OK", "results": []}})
        ]
        mock_get.side_effect = responses
        
        # Mock time.sleep to speed up test
        with patch('time.sleep'):
            response = client._make_request("/test/endpoint")
        
        # Should eventually succeed
        assert response.status == "OK"
        assert mock_get.call_count == 3
    
    @patch('requests.Session.get')
    def test_get_stock_bars(self, mock_get, client):
        """Test getting stock bars."""
        # Mock API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "OK",
            "results": [
                {
                    "t": 1642204800000,  # Timestamp in milliseconds
                    "o": 150.0,
                    "h": 155.0,
                    "l": 149.0,
                    "c": 154.0,
                    "v": 1000000,
                    "vw": 152.5
                }
            ]
        }
        mock_get.return_value = mock_response
        
        # Get stock bars
        bars = client.get_stock_bars(
            symbol="AAPL",
            start_date=date(2022, 1, 15),
            end_date=date(2022, 1, 15)
        )
        
        # Verify results
        assert len(bars) == 1
        bar = bars[0]
        assert isinstance(bar, OHLCVData)
        assert bar.symbol == "AAPL"
        assert bar.volume == 1000000
    
    @patch('requests.Session.get')
    def test_get_news(self, mock_get, client):
        """Test getting news articles."""
        # Mock API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "OK",
            "results": [
                {
                    "id": "test-123",
                    "title": "Test News",
                    "published_utc": "2022-01-15T12:00:00Z",
                    "tickers": ["AAPL"],
                    "keywords": ["earnings"]
                }
            ]
        }
        mock_get.return_value = mock_response
        
        # Get news
        articles = client.get_news(symbol="AAPL", limit=10)
        
        # Verify results
        assert len(articles) == 1
        article = articles[0]
        assert isinstance(article, NewsArticle)
        assert article.id == "test-123"
        assert article.title == "Test News"
        assert "AAPL" in article.tickers
    
    @patch('requests.Session.get')
    def test_get_options_contracts(self, mock_get, client):
        """Test getting options contracts."""
        # Mock API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "OK",
            "results": [
                {
                    "ticker": "AAPL240119C00150000",
                    "underlying_ticker": "AAPL",
                    "strike_price": 150.0,
                    "expiration_date": "2024-01-19",
                    "contract_type": "call"
                }
            ]
        }
        mock_get.return_value = mock_response
        
        # Get options contracts
        contracts = client.get_options_contracts(underlying_symbol="AAPL")
        
        # Verify results
        assert len(contracts) == 1
        contract = contracts[0]
        assert isinstance(contract, OptionsContract)
        assert contract.underlying_ticker == "AAPL"
        assert contract.option_type == "call"
    
    @patch('requests.Session.get')
    def test_get_technical_indicators(self, mock_get, client):
        """Test getting technical indicators."""
        # Mock API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "OK",
            "results": [
                {
                    "timestamp": 1642204800000,
                    "value": 50.25
                }
            ]
        }
        mock_get.return_value = mock_response
        
        # Get technical indicators
        indicators = client.get_technical_indicators(
            symbol="AAPL",
            indicator_name="sma",
            start_date=date(2022, 1, 15),
            end_date=date(2022, 1, 15)
        )
        
        # Verify results
        assert len(indicators) == 1
        indicator = indicators[0]
        assert isinstance(indicator, TechnicalIndicator)
        assert indicator.symbol == "AAPL"
        assert indicator.indicator_name == "sma"
        assert indicator.value == 50.25
    
    def test_health_check_success(self, client):
        """Test successful health check."""
        with patch.object(client, '_make_request') as mock_request:
            mock_request.return_value = APIResponse(
                status="OK",
                results=[]
            )
            
            assert client.health_check() is True
            mock_request.assert_called_once()
    
    def test_health_check_failure(self, client):
        """Test failed health check."""
        with patch.object(client, '_make_request') as mock_request:
            mock_request.side_effect = PolygonAPIError("Connection failed")
            
            assert client.health_check() is False
    
    def test_rate_limit_info(self, client):
        """Test getting rate limit info."""
        info = client.get_rate_limit_info()
        assert info.calls_per_minute == 5
        assert info.calls_remaining <= 5


@pytest.mark.skipif(not CLIENT_AVAILABLE, reason="Polygon client not available")
class TestPolygonAPIError:
    """Test Polygon API error class."""
    
    def test_basic_error(self):
        """Test basic error creation."""
        error = PolygonAPIError("Test error")
        assert str(error) == "Test error"
        assert error.status_code is None
        assert error.response_data is None
    
    def test_error_with_details(self):
        """Test error with status code and response data."""
        error = PolygonAPIError(
            "API error",
            status_code=400,
            response_data={"error": "bad request"}
        )
        assert str(error) == "API error"
        assert error.status_code == 400
        assert error.response_data["error"] == "bad request"


if __name__ == "__main__":
    pytest.main([__file__])