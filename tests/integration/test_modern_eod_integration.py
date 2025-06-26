"""
Integration tests for Modern EOD Data Collector

These tests verify the complete end-to-end data collection pipeline
works correctly with the new Polygon client and modern data storage.
"""

import pytest
import os
import tempfile
import sqlite3
from datetime import date, datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import pandas as pd

# Test if we can import the modules
try:
    import sys
    sys.path.insert(0, '/workspace/src')
    
    from trading_system.data_ingestion.eod_collector_v2 import (
        ModernEODDataCollector,
        ModernDataStorage,
        CollectionProgress
    )
    from trading_system.data_ingestion.polygon_client import (
        PolygonClient,
        OptionsContract,
        OptionsBar,
        TimeFrame
    )
    from trading_system.config.settings import Config
    IMPORTS_AVAILABLE = True
except ImportError as e:
    IMPORTS_AVAILABLE = False
    import_error = str(e)


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason=f"Imports not available: {import_error if not IMPORTS_AVAILABLE else ''}")
class TestModernDataStorage:
    """Test the modern data storage system"""
    
    def setup_method(self):
        """Set up test environment"""
        self.temp_dir = tempfile.mkdtemp()
        os.environ['RAW_DATA_DIR'] = self.temp_dir
        self.config = Config()
        self.storage = ModernDataStorage(self.config)
    
    def teardown_method(self):
        """Clean up test environment"""
        if 'RAW_DATA_DIR' in os.environ:
            del os.environ['RAW_DATA_DIR']
    
    def test_database_initialization(self):
        """Test database is initialized with correct schema"""
        assert self.storage.db_path.exists()
        
        with sqlite3.connect(self.storage.db_path) as conn:
            # Check tables exist
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            
            expected_tables = [
                'underlying_bars', 
                'options_contracts', 
                'options_bars', 
                'collection_metadata'
            ]
            for table in expected_tables:
                assert table in tables
    
    def test_save_underlying_bars(self):
        """Test saving underlying bars from DataFrame"""
        # Create test DataFrame
        data = {
            'open': [100.0, 101.0, 102.0],
            'high': [105.0, 106.0, 107.0],
            'low': [99.0, 100.0, 101.0],
            'close': [104.0, 105.0, 106.0],
            'volume': [1000000, 1100000, 1200000],
            'vwap': [102.5, 103.5, 104.5],
            'transactions': [1000, 1100, 1200]
        }
        timestamps = pd.date_range('2024-01-01', periods=3, freq='D')
        df = pd.DataFrame(data, index=timestamps)
        
        # Save data
        saved_count = self.storage.save_underlying_bars('AAPL', df)
        assert saved_count == 3
        
        # Verify data was saved
        with sqlite3.connect(self.storage.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM underlying_bars WHERE ticker = ?", ('AAPL',))
            count = cursor.fetchone()[0]
            assert count == 3
    
    def test_save_options_contracts(self):
        """Test saving options contracts"""
        contracts = [
            OptionsContract(
                ticker="O:AAPL240315C00150000",
                underlying_ticker="AAPL",
                contract_type="call",
                expiration_date="2024-03-15",
                strike_price=150.0,
                exercise_style="american",
                shares_per_contract=100,
                primary_exchange="NASDAQ"
            ),
            OptionsContract(
                ticker="O:AAPL240315P00140000",
                underlying_ticker="AAPL",
                contract_type="put",
                expiration_date="2024-03-15",
                strike_price=140.0,
                exercise_style="american",
                shares_per_contract=100,
                primary_exchange="NASDAQ"
            )
        ]
        
        saved_count = self.storage.save_options_contracts(contracts)
        assert saved_count == 2
        
        # Verify data was saved
        with sqlite3.connect(self.storage.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM options_contracts WHERE underlying_ticker = ?", ('AAPL',))
            count = cursor.fetchone()[0]
            assert count == 2
    
    def test_save_options_bars(self):
        """Test saving options bars"""
        bars = [
            OptionsBar(
                ticker="O:AAPL240315C00150000",
                timestamp=1640995200000,
                open=10.50,
                high=11.00,
                low=10.25,
                close=10.75,
                volume=1000,
                vwap=10.65,
                transactions=50
            ),
            OptionsBar(
                ticker="O:AAPL240315C00150000",
                timestamp=1641081600000,
                open=10.75,
                high=11.25,
                low=10.50,
                close=11.00,
                volume=1200,
                vwap=10.90,
                transactions=60
            )
        ]
        
        saved_count = self.storage.save_options_bars(bars)
        assert saved_count == 2
        
        # Verify data was saved
        with sqlite3.connect(self.storage.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM options_bars")
            count = cursor.fetchone()[0]
            assert count == 2
    
    def test_get_data_statistics(self):
        """Test getting comprehensive data statistics"""
        # Add some test data first
        self.test_save_underlying_bars()
        self.test_save_options_contracts()
        self.test_save_options_bars()
        
        stats = self.storage.get_data_statistics()
        
        assert 'underlying_bars' in stats
        assert 'options_contracts' in stats
        assert 'options_bars' in stats
        
        assert stats['underlying_bars']['total_records'] == 3
        assert stats['options_contracts']['total_contracts'] == 2
        assert stats['options_bars']['total_records'] == 2


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason=f"Imports not available: {import_error if not IMPORTS_AVAILABLE else ''}")
class TestCollectionProgress:
    """Test collection progress tracking"""
    
    def test_progress_creation(self):
        """Test creating collection progress"""
        start_date = date(2024, 1, 1)
        end_date = date(2024, 1, 31)
        
        progress = CollectionProgress(
            ticker="AAPL",
            start_date=start_date,
            end_date=end_date
        )
        
        assert progress.ticker == "AAPL"
        assert progress.start_date == start_date
        assert progress.end_date == end_date
        assert progress.status == "pending"
        assert progress.total_days == 31  # From Jan 1 to Jan 31 inclusive is 31 days
    
    def test_progress_percentage_calculation(self):
        """Test progress percentage calculation"""
        progress = CollectionProgress(
            ticker="AAPL",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 10),
            completed_days=5
        )
        
        assert progress.progress_percentage == 50.0
    
    def test_progress_serialization(self):
        """Test progress to/from dict conversion"""
        original = CollectionProgress(
            ticker="AAPL",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            underlying_bars_collected=100,
            options_contracts_collected=50,
            options_bars_collected=25
        )
        
        # Convert to dict and back
        data = original.to_dict()
        restored = CollectionProgress.from_dict(data)
        
        assert restored.ticker == original.ticker
        assert restored.start_date == original.start_date
        assert restored.end_date == original.end_date
        assert restored.underlying_bars_collected == original.underlying_bars_collected
        assert restored.options_contracts_collected == original.options_contracts_collected
        assert restored.options_bars_collected == original.options_bars_collected


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason=f"Imports not available: {import_error if not IMPORTS_AVAILABLE else ''}")
class TestModernEODDataCollector:
    """Test the modern EOD data collector"""
    
    def setup_method(self):
        """Set up test environment"""
        self.temp_dir = tempfile.mkdtemp()
        os.environ['POLYGON_API_KEY'] = 'test_key_12345'
        os.environ['RAW_DATA_DIR'] = self.temp_dir
        self.config = Config()
    
    def teardown_method(self):
        """Clean up test environment"""
        for env_var in ['POLYGON_API_KEY', 'RAW_DATA_DIR']:
            if env_var in os.environ:
                del os.environ[env_var]
        
        # Clean up temp directory to ensure test isolation
        import shutil
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    @patch('trading_system.data_ingestion.eod_collector_v2.PolygonClient')
    def test_collector_initialization(self, mock_polygon_client_class):
        """Test collector initialization"""
        mock_client = Mock()
        mock_polygon_client_class.return_value = mock_client
        
        collector = ModernEODDataCollector(self.config)
        
        assert collector.config == self.config
        assert collector.client == mock_client
        assert collector.storage is not None
        assert collector.progress_tracker == {}
    
    @patch('trading_system.data_ingestion.eod_collector_v2.PolygonClient')
    def test_single_ticker_data_collection(self, mock_polygon_client_class):
        """Test complete data collection for a single ticker"""
        # Mock the Polygon client
        mock_client = Mock()
        mock_polygon_client_class.return_value = mock_client
        
        # Mock underlying bars data
        underlying_data = {
            'open': [150.0, 151.0],
            'high': [155.0, 156.0],
            'low': [149.0, 150.0],
            'close': [154.0, 155.0],
            'volume': [1000000, 1100000],
            'vwap': [152.5, 153.5],
            'transactions': [1000, 1100]
        }
        timestamps = pd.date_range('2024-01-01', periods=2, freq='D')
        mock_df = pd.DataFrame(underlying_data, index=timestamps)
        mock_client.get_underlying_bars.return_value = mock_df
        
        # Mock options contracts
        mock_contracts = [
            OptionsContract(
                ticker="O:AAPL240315C00150000",
                underlying_ticker="AAPL",
                contract_type="call",
                expiration_date="2024-03-15",
                strike_price=150.0,
                exercise_style="american",
                shares_per_contract=100,
                primary_exchange="NASDAQ"
            )
        ]
        mock_client.get_options_contracts.return_value = mock_contracts
        
        # Mock options bars
        mock_options_bars = [
            OptionsBar(
                ticker="O:AAPL240315C00150000",
                timestamp=1640995200000,
                open=10.50,
                high=11.00,
                low=10.25,
                close=10.75,
                volume=1000
            )
        ]
        mock_client.get_options_bars.return_value = mock_options_bars
        
        # Mock ticker validation
        mock_client.validate_ticker.return_value = True
        
        # Mock market status
        mock_client.get_market_status.return_value = {"market": "open"}
        
        # Create collector and collect data
        collector = ModernEODDataCollector(self.config)
        
        with patch('time.sleep'):  # Speed up test
            results = collector.collect_market_data(
                tickers=["AAPL"],
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 2),
                collect_options=True
            )
        
        # Verify results
        assert "AAPL" in results
        progress = results["AAPL"]
        assert progress.status == "completed"
        assert progress.underlying_bars_collected == 2
        assert progress.options_contracts_collected == 1
        assert progress.options_bars_collected == 1
        
        # Verify API calls were made
        mock_client.validate_ticker.assert_called_with("AAPL")
        mock_client.get_underlying_bars.assert_called_once()
        mock_client.get_options_contracts.assert_called_once()
        mock_client.get_options_bars.assert_called_once()
        mock_client.get_market_status.assert_called_once()
    
    @patch('trading_system.data_ingestion.eod_collector_v2.PolygonClient')
    def test_multiple_tickers_collection(self, mock_polygon_client_class):
        """Test data collection for multiple tickers"""
        mock_client = Mock()
        mock_polygon_client_class.return_value = mock_client
        
        # Mock empty underlying data (simulate no data available)
        mock_client.get_underlying_bars.return_value = pd.DataFrame()
        mock_client.get_options_contracts.return_value = []
        mock_client.validate_ticker.return_value = True
        mock_client.get_market_status.return_value = {"market": "closed"}
        
        collector = ModernEODDataCollector(self.config)
        
        with patch('time.sleep'):
            results = collector.collect_market_data(
                tickers=["AAPL", "GOOGL", "MSFT"],
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 1),
                collect_options=False
            )
        
        # Verify all tickers were processed
        assert len(results) == 3
        for ticker in ["AAPL", "GOOGL", "MSFT"]:
            assert ticker in results
            assert results[ticker].status == "completed"
        
        # Verify validation was called for each ticker
        assert mock_client.validate_ticker.call_count == 3
    
    @patch('trading_system.data_ingestion.eod_collector_v2.PolygonClient')
    def test_invalid_ticker_handling(self, mock_polygon_client_class):
        """Test handling of invalid tickers"""
        # Create fresh temp directory for this test
        temp_dir = tempfile.mkdtemp()
        os.environ['RAW_DATA_DIR'] = temp_dir
        config = Config()
        
        mock_client = Mock()
        mock_polygon_client_class.return_value = mock_client
        
        # Mock ticker validation - some valid, some invalid
        def mock_validate_ticker(ticker):
            return ticker in ["AAPL", "GOOGL"]  # INVALID_TICKER returns False
        
        mock_client.validate_ticker.side_effect = mock_validate_ticker
        mock_client.get_underlying_bars.return_value = pd.DataFrame()
        mock_client.get_options_contracts.return_value = []
        mock_client.get_market_status.return_value = {"market": "open"}
        
        collector = ModernEODDataCollector(config)
        
        with patch('time.sleep'):
            results = collector.collect_market_data(
                tickers=["AAPL", "INVALID_TICKER", "GOOGL"],
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 1),
                collect_options=False
            )
        
        # Only valid tickers should be in results
        assert len(results) == 2
        assert "AAPL" in results
        assert "GOOGL" in results
        assert "INVALID_TICKER" not in results
        
        # Clean up
        import shutil
        shutil.rmtree(temp_dir)
    
    @patch('trading_system.data_ingestion.eod_collector_v2.PolygonClient')
    def test_api_error_handling(self, mock_polygon_client_class):
        """Test handling of API errors during collection"""
        mock_client = Mock()
        mock_polygon_client_class.return_value = mock_client
        
        mock_client.validate_ticker.return_value = True
        mock_client.get_underlying_bars.side_effect = Exception("API Error")
        
        collector = ModernEODDataCollector(self.config)
        
        with patch('time.sleep'):
            results = collector.collect_market_data(
                tickers=["AAPL"],
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 1),
                collect_options=False
            )
        
        # Ticker should be marked as failed
        assert "AAPL" in results
        assert results["AAPL"].status == "failed"
        assert "API Error" in results["AAPL"].error_message
    
    @patch('trading_system.data_ingestion.eod_collector_v2.PolygonClient')
    def test_progress_persistence(self, mock_polygon_client_class):
        """Test that progress is saved and can be resumed"""
        mock_client = Mock()
        mock_polygon_client_class.return_value = mock_client
        
        mock_client.validate_ticker.return_value = True
        mock_client.get_underlying_bars.return_value = pd.DataFrame()
        mock_client.get_options_contracts.return_value = []
        mock_client.get_market_status.return_value = {"market": "open"}
        
        # First collection
        collector1 = ModernEODDataCollector(self.config)
        
        with patch('time.sleep'):
            results1 = collector1.collect_market_data(
                tickers=["AAPL"],
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 1)
            )
        
        # Create new collector instance (simulates restart)
        collector2 = ModernEODDataCollector(self.config)
        
        # Progress should be loaded
        assert "AAPL" in collector2.progress_tracker
        assert collector2.progress_tracker["AAPL"].status == "completed"
    
    @patch('trading_system.data_ingestion.eod_collector_v2.PolygonClient')
    def test_collection_status_reporting(self, mock_polygon_client_class):
        """Test collection status reporting"""
        mock_client = Mock()
        mock_polygon_client_class.return_value = mock_client
        
        mock_client.validate_ticker.return_value = True
        mock_client.get_underlying_bars.return_value = pd.DataFrame()
        mock_client.get_options_contracts.return_value = []
        mock_client.get_market_status.return_value = {"market": "open"}
        
        collector = ModernEODDataCollector(self.config)
        
        with patch('time.sleep'):
            collector.collect_market_data(
                tickers=["AAPL", "GOOGL"],
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 1)
            )
        
        # Test status reporting
        status = collector.get_collection_status()
        assert len(status) == 2
        assert "AAPL" in status
        assert "GOOGL" in status
        
        for ticker_status in status.values():
            assert "status" in ticker_status
            assert "progress_percentage" in ticker_status
            assert "underlying_bars_collected" in ticker_status
            assert "options_contracts_collected" in ticker_status
            assert "options_bars_collected" in ticker_status
    
    @patch('trading_system.data_ingestion.eod_collector_v2.PolygonClient')
    def test_data_summary_reporting(self, mock_polygon_client_class):
        """Test comprehensive data summary reporting"""
        mock_client = Mock()
        mock_polygon_client_class.return_value = mock_client
        
        mock_client.validate_ticker.return_value = True
        mock_client.get_underlying_bars.return_value = pd.DataFrame()
        mock_client.get_options_contracts.return_value = []
        mock_client.get_market_status.return_value = {"market": "open"}
        
        collector = ModernEODDataCollector(self.config)
        
        with patch('time.sleep'):
            collector.collect_market_data(
                tickers=["AAPL"],
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 1)
            )
        
        summary = collector.get_data_summary()
        
        assert "collection_summary" in summary
        assert "database_statistics" in summary
        assert "collection_totals" in summary
        
        assert summary["collection_summary"]["total_tickers"] == 1
        assert summary["collection_summary"]["completed"] == 1
        assert summary["collection_summary"]["failed"] == 0
    
    @patch('trading_system.data_ingestion.eod_collector_v2.PolygonClient')
    def test_failed_collection_resume(self, mock_polygon_client_class):
        """Test resuming failed collections"""
        mock_client = Mock()
        mock_polygon_client_class.return_value = mock_client
        
        mock_client.validate_ticker.return_value = True
        
        # First call fails, second succeeds
        mock_client.get_underlying_bars.side_effect = [
            Exception("Network error"),  # Fails first time
            pd.DataFrame()               # Succeeds on resume
        ]
        mock_client.get_options_contracts.return_value = []
        mock_client.get_market_status.return_value = {"market": "open"}
        
        collector = ModernEODDataCollector(self.config)
        
        # Initial collection (should fail)
        with patch('time.sleep'):
            results = collector.collect_market_data(
                tickers=["AAPL"],
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 1)
            )
        
        assert results["AAPL"].status == "failed"
        
        # Resume failed collections
        with patch('time.sleep'):
            resumed_tickers = collector.resume_failed_collections()
        
        assert "AAPL" in resumed_tickers
        assert collector.progress_tracker["AAPL"].status == "completed"


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason=f"Imports not available: {import_error if not IMPORTS_AVAILABLE else ''}")
def test_end_to_end_data_pipeline():
    """Test complete end-to-end data collection pipeline"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Use unique environment variable to avoid conflicts
        test_env_key = f'RAW_DATA_DIR_{id(temp_dir)}'
        os.environ[test_env_key] = temp_dir
        os.environ['POLYGON_API_KEY'] = 'test_key'
        os.environ['RAW_DATA_DIR'] = temp_dir
        
        try:
            config = Config()
            
            with patch('trading_system.data_ingestion.eod_collector_v2.PolygonClient') as mock_client_class:
                mock_client = Mock()
                mock_client_class.return_value = mock_client
                
                # Mock complete data pipeline
                mock_client.validate_ticker.return_value = True
                
                # Mock underlying data
                underlying_data = pd.DataFrame({
                    'open': [100.0], 'high': [105.0], 'low': [99.0], 
                    'close': [104.0], 'volume': [1000000], 'vwap': [102.5], 'transactions': [1000]
                }, index=pd.date_range('2024-01-01', periods=1))
                mock_client.get_underlying_bars.return_value = underlying_data
                
                # Mock options data
                mock_client.get_options_contracts.return_value = [
                    OptionsContract(
                        ticker="O:AAPL240315C00100000",
                        underlying_ticker="AAPL",
                        contract_type="call",
                        expiration_date="2024-03-15",
                        strike_price=100.0,
                        exercise_style="american",
                        shares_per_contract=100,
                        primary_exchange="NASDAQ"
                    )
                ]
                
                mock_client.get_options_bars.return_value = [
                    OptionsBar(
                        ticker="O:AAPL240315C00100000",
                        timestamp=1640995200000,
                        open=5.0, high=5.5, low=4.5, close=5.25, volume=500
                    )
                ]
                
                mock_client.get_market_status.return_value = {"market": "open"}
                
                # Run the pipeline
                collector = ModernEODDataCollector(config)
                
                with patch('time.sleep'):
                    results = collector.collect_market_data(
                        tickers=["AAPL"],
                        start_date=date(2024, 1, 1),
                        end_date=date(2024, 1, 1),
                        collect_options=True
                    )
                
                # Verify complete pipeline
                assert len(results) == 1
                assert "AAPL" in results
                assert results["AAPL"].status == "completed"
                assert results["AAPL"].underlying_bars_collected == 1
                assert results["AAPL"].options_contracts_collected == 1
                assert results["AAPL"].options_bars_collected == 1
                
                # Verify data was persisted
                summary = collector.get_data_summary()
                assert summary["collection_totals"]["total_underlying_bars"] == 1
                assert summary["collection_totals"]["total_options_contracts"] == 1
                assert summary["collection_totals"]["total_options_bars"] == 1
        
        finally:
            # Clean up environment
            for env_var in ['POLYGON_API_KEY', 'RAW_DATA_DIR', test_env_key]:
                if env_var in os.environ:
                    del os.environ[env_var]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])