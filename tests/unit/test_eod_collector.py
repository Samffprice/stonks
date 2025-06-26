"""
Unit tests for EOD (End-of-Day) Data Collector.

Tests the EODDataCollector functionality including progress tracking,
data storage, and batch collection of market data.
"""

import pytest
import json
import tempfile
import sqlite3
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, date, timedelta
from pathlib import Path

try:
    from src.trading_system.data_ingestion.eod_collector import (
        EODDataCollector, DataStorage, CollectionProgress
    )
    from src.trading_system.data_ingestion.models import OHLCVData, NewsArticle
    from src.trading_system.config.settings import Config
    from decimal import Decimal
    COLLECTOR_AVAILABLE = True
except ImportError:
    COLLECTOR_AVAILABLE = False


@pytest.mark.skipif(not COLLECTOR_AVAILABLE, reason="EOD collector not available")
class TestCollectionProgress:
    """Test collection progress tracking."""
    
    def test_progress_creation(self):
        """Test creating collection progress."""
        start = date(2024, 1, 1)
        end = date(2024, 1, 31)
        
        progress = CollectionProgress(
            ticker="AAPL",
            start_date=start,
            end_date=end
        )
        
        assert progress.ticker == "AAPL"
        assert progress.start_date == start
        assert progress.end_date == end
        assert progress.status == "pending"
        assert progress.total_days == 30
        assert progress.last_updated is not None
    
    def test_progress_percentage(self):
        """Test progress percentage calculation."""
        progress = CollectionProgress(
            ticker="AAPL",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            completed_days=15
        )
        
        assert progress.progress_percentage == 50.0
    
    def test_serialization(self):
        """Test JSON serialization and deserialization."""
        original = CollectionProgress(
            ticker="AAPL",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            last_collected_date=date(2024, 1, 15),
            completed_days=15,
            status="in_progress"
        )
        
        # Serialize to dict
        data = original.to_dict()
        assert isinstance(data['start_date'], str)
        assert isinstance(data['end_date'], str)
        
        # Deserialize back
        restored = CollectionProgress.from_dict(data)
        assert restored.ticker == original.ticker
        assert restored.start_date == original.start_date
        assert restored.end_date == original.end_date
        assert restored.last_collected_date == original.last_collected_date
        assert restored.status == original.status


@pytest.mark.skipif(not COLLECTOR_AVAILABLE, reason="EOD collector not available")
class TestDataStorage:
    """Test data storage functionality."""
    
    @pytest.fixture
    def temp_config(self):
        """Create temporary configuration for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = Mock(spec=Config)
            config.data = Mock()
            config.data.raw_data_dir = Path(temp_dir) / "raw"
            yield config
    
    @pytest.fixture
    def storage(self, temp_config):
        """Create DataStorage instance with temporary config."""
        return DataStorage(temp_config)
    
    def test_database_initialization(self, storage):
        """Test database initialization."""
        assert storage.db_path.exists()
        
        # Check that tables were created
        with sqlite3.connect(storage.db_path) as conn:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            
            expected_tables = ['ohlcv_data', 'news_articles', 'options_contracts', 'technical_indicators']
            for table in expected_tables:
                assert table in tables
    
    def test_save_ohlcv_data(self, storage):
        """Test saving OHLCV data."""
        ohlcv_data = [
            OHLCVData(
                symbol="AAPL",
                timestamp=datetime(2024, 1, 15, 16, 0, 0),
                open=Decimal("150.00"),
                high=Decimal("155.00"),
                low=Decimal("149.00"),
                close=Decimal("154.00"),
                volume=1000000
            ),
            OHLCVData(
                symbol="AAPL",
                timestamp=datetime(2024, 1, 16, 16, 0, 0),
                open=Decimal("154.00"),
                high=Decimal("158.00"),
                low=Decimal("153.00"),
                close=Decimal("157.00"),
                volume=1200000
            )
        ]
        
        saved_count = storage.save_ohlcv_data(ohlcv_data)
        assert saved_count == 2
        
        # Verify data was saved
        with sqlite3.connect(storage.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM ohlcv_data WHERE symbol = 'AAPL'")
            count = cursor.fetchone()[0]
            assert count == 2
    
    def test_save_news_articles(self, storage):
        """Test saving news articles."""
        articles = [
            NewsArticle(
                id="test-123",
                title="Test Article",
                published_utc=datetime(2024, 1, 15, 12, 0, 0),
                tickers=["AAPL", "MSFT"],
                keywords=["earnings", "tech"]
            )
        ]
        
        saved_count = storage.save_news_articles(articles)
        assert saved_count == 1
        
        # Verify data was saved
        with sqlite3.connect(storage.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM news_articles")
            count = cursor.fetchone()[0]
            assert count == 1
    
    def test_get_last_collected_date(self, storage):
        """Test getting last collected date."""
        # Initially no data
        last_date = storage.get_last_collected_date("AAPL")
        assert last_date is None
        
        # Add some data
        ohlcv_data = [
            OHLCVData(
                symbol="AAPL",
                timestamp=datetime(2024, 1, 15, 16, 0, 0),
                open=Decimal("150.00"),
                high=Decimal("155.00"),
                low=Decimal("149.00"),
                close=Decimal("154.00"),
                volume=1000000
            )
        ]
        storage.save_ohlcv_data(ohlcv_data)
        
        # Should return the date
        last_date = storage.get_last_collected_date("AAPL")
        assert last_date == date(2024, 1, 15)


@pytest.mark.skipif(not COLLECTOR_AVAILABLE, reason="EOD collector not available")
class TestEODDataCollector:
    """Test EOD data collector."""
    
    @pytest.fixture
    def temp_config(self):
        """Create temporary configuration for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = Mock(spec=Config)
            config.data = Mock()
            config.data.raw_data_dir = Path(temp_dir) / "raw"
            config.api = Mock()
            config.api.polygon_api_key = "test_key"
            config.api.polygon_rate_limit = 5
            config.api.polygon_max_retries = 3
            yield config
    
    @pytest.fixture
    def mock_client(self):
        """Create mock Polygon client."""
        return Mock()
    
    @pytest.fixture
    def collector(self, temp_config):
        """Create EOD collector with temporary config."""
        with patch('src.trading_system.data_ingestion.eod_collector.PolygonClient'):
            return EODDataCollector(temp_config)
    
    def test_collector_creation(self, collector):
        """Test creating EOD collector."""
        assert collector.config is not None
        assert collector.client is not None
        assert collector.storage is not None
        assert collector.progress_tracker == {}
    
    def test_progress_persistence(self, collector):
        """Test progress saving and loading."""
        # Add some progress
        progress = CollectionProgress(
            ticker="AAPL",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            status="completed",
            completed_days=30
        )
        collector.progress_tracker["AAPL"] = progress
        
        # Save progress
        collector._save_progress()
        assert collector.progress_file.exists()
        
        # Create new collector and verify progress is loaded
        with patch('src.trading_system.data_ingestion.eod_collector.PolygonClient'):
            new_collector = EODDataCollector(collector.config)
        
        assert "AAPL" in new_collector.progress_tracker
        loaded_progress = new_collector.progress_tracker["AAPL"]
        assert loaded_progress.ticker == "AAPL"
        assert loaded_progress.status == "completed"
    
    def test_collect_historical_data_setup(self, collector):
        """Test historical data collection setup."""
        tickers = ["AAPL", "MSFT"]
        start_date = date(2024, 1, 1)
        end_date = date(2024, 1, 31)
        
        # Mock the _collect_ticker_data method to avoid actual API calls
        with patch.object(collector, '_collect_ticker_data'):
            result = collector.collect_historical_data(tickers, start_date, end_date)
        
        # Verify progress tracking was set up
        assert len(collector.progress_tracker) == 2
        assert "AAPL" in collector.progress_tracker
        assert "MSFT" in collector.progress_tracker
        
        # Verify progress objects
        aapl_progress = collector.progress_tracker["AAPL"]
        assert aapl_progress.start_date == start_date
        assert aapl_progress.end_date == end_date
    
    @patch('src.trading_system.data_ingestion.eod_collector.PolygonClient')
    def test_collect_ticker_data_success(self, mock_client_class, temp_config):
        """Test successful ticker data collection."""
        # Setup mock client
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        # Mock API responses
        mock_ohlcv = [
            OHLCVData(
                symbol="AAPL",
                timestamp=datetime(2024, 1, 15, 16, 0, 0),
                open=Decimal("150.00"),
                high=Decimal("155.00"),
                low=Decimal("149.00"),
                close=Decimal("154.00"),
                volume=1000000
            )
        ]
        mock_news = [
            NewsArticle(
                id="test-123",
                title="Test Article",
                published_utc=datetime(2024, 1, 15, 12, 0, 0),
                tickers=["AAPL"]
            )
        ]
        
        mock_client.get_stock_bars.return_value = mock_ohlcv
        mock_client.get_news.return_value = mock_news
        
        # Create collector and add progress
        collector = EODDataCollector(temp_config)
        progress = CollectionProgress(
            ticker="AAPL",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31)
        )
        collector.progress_tracker["AAPL"] = progress
        
        # Collect data
        collector._collect_ticker_data("AAPL")
        
        # Verify API calls were made
        mock_client.get_stock_bars.assert_called_once()
        mock_client.get_news.assert_called_once()
        
        # Verify progress was updated
        assert progress.status == "completed"
        assert progress.last_collected_date == date(2024, 1, 31)
    
    def test_get_collection_status(self, collector):
        """Test getting collection status."""
        # Add some progress
        progress1 = CollectionProgress(
            ticker="AAPL",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            status="completed",
            completed_days=30
        )
        progress2 = CollectionProgress(
            ticker="MSFT",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            status="failed",
            error_message="API error"
        )
        
        collector.progress_tracker["AAPL"] = progress1
        collector.progress_tracker["MSFT"] = progress2
        
        status = collector.get_collection_status()
        
        assert len(status) == 2
        assert status["AAPL"]["status"] == "completed"
        assert status["AAPL"]["progress_percentage"] == 100.0
        assert status["MSFT"]["status"] == "failed"
        assert status["MSFT"]["error_message"] == "API error"
    
    def test_resume_failed_collections(self, collector):
        """Test resuming failed collections."""
        # Add failed progress
        progress = CollectionProgress(
            ticker="AAPL",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            status="failed",
            error_message="Previous error"
        )
        collector.progress_tracker["AAPL"] = progress
        
        # Mock the _collect_ticker_data method
        with patch.object(collector, '_collect_ticker_data') as mock_collect:
            failed_tickers = collector.resume_failed_collections()
        
        assert failed_tickers == ["AAPL"]
        assert progress.status == "pending"
        assert progress.error_message is None
        mock_collect.assert_called_once_with("AAPL")
    
    def test_get_data_summary(self, collector):
        """Test getting data summary."""
        # Add some progress
        progress1 = CollectionProgress(
            ticker="AAPL",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            status="completed",
            completed_days=30
        )
        progress2 = CollectionProgress(
            ticker="MSFT",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            status="failed"
        )
        
        collector.progress_tracker["AAPL"] = progress1
        collector.progress_tracker["MSFT"] = progress2
        
        summary = collector.get_data_summary()
        
        assert summary["total_tickers"] == 2
        assert summary["completed"] == 1
        assert summary["failed"] == 1
        assert summary["in_progress"] == 0
        assert summary["overall_progress"] == 50.0


if __name__ == "__main__":
    pytest.main([__file__])