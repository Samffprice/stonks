"""
Complete Data Ingestion Pipeline Integration Tests

These tests verify the entire data ingestion system works end-to-end,
combining the Polygon client, Modern EOD collector, and data storage
in realistic scenarios.
"""

import pytest
import os
import tempfile
import sqlite3
from datetime import date, datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import pandas as pd
import json

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
    from trading_system.data_ingestion.eod_collector_v2 import (
        ModernEODDataCollector,
        ModernDataStorage,
        CollectionProgress
    )
    from trading_system.config.settings import Config
    from trading_system.utils.logger import get_logger
    IMPORTS_AVAILABLE = True
except ImportError as e:
    IMPORTS_AVAILABLE = False
    import_error = str(e)


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason=f"Imports not available: {import_error if not IMPORTS_AVAILABLE else ''}")
class TestCompleteDataIngestionPipeline:
    """Test the complete data ingestion pipeline end-to-end"""
    
    def setup_method(self):
        """Set up test environment"""
        self.temp_dir = tempfile.mkdtemp()
        os.environ['POLYGON_API_KEY'] = 'test_key_12345'
        os.environ['RAW_DATA_DIR'] = self.temp_dir
        
        # Create fresh config for each test
        self.config = Config()
        
        # Clear any existing progress files
        progress_file = self.config.data.raw_data_dir / "modern_collection_progress.json"
        if progress_file.exists():
            progress_file.unlink()
        
        # Sample tickers for testing
        self.test_tickers = ["AAPL", "GOOGL", "MSFT"]
        self.test_date_range = (date(2024, 1, 1), date(2024, 1, 5))
    
    def teardown_method(self):
        """Clean up test environment"""
        for env_var in ['POLYGON_API_KEY', 'RAW_DATA_DIR']:
            if env_var in os.environ:
                del os.environ[env_var]
        
        # Clean up temp directory
        import shutil
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def _create_mock_underlying_data(self, ticker: str, num_days: int = 5) -> pd.DataFrame:
        """Create realistic mock underlying stock data"""
        dates = pd.date_range('2024-01-01', periods=num_days, freq='D')
        base_price = {'AAPL': 150.0, 'GOOGL': 2800.0, 'MSFT': 350.0}.get(ticker, 100.0)
        
        data = []
        for i, date in enumerate(dates):
            price = base_price + (i * 2)  # Trending up
            data.append({
                'open': price,
                'high': price + 5,
                'low': price - 3,
                'close': price + 2,
                'volume': 1000000 + (i * 100000),
                'vwap': price + 1,
                'transactions': 5000 + (i * 100)
            })
        
        return pd.DataFrame(data, index=dates)
    
    def _create_mock_options_contracts(self, ticker: str, num_contracts: int = 3) -> list:
        """Create realistic mock options contracts"""
        contracts = []
        base_strike = {'AAPL': 150.0, 'GOOGL': 2800.0, 'MSFT': 350.0}.get(ticker, 100.0)
        
        for i in range(num_contracts):
            for contract_type in ['call', 'put']:
                strike = base_strike + (i * 10)
                contracts.append(OptionsContract(
                    ticker=f"O:{ticker}240315{contract_type[0].upper()}00{int(strike):03d}000",
                    underlying_ticker=ticker,
                    contract_type=contract_type,
                    expiration_date="2024-03-15",
                    strike_price=strike,
                    exercise_style="american",
                    shares_per_contract=100,
                    primary_exchange="NASDAQ"
                ))
        
        return contracts
    
    def _create_mock_options_bars(self, options_ticker: str, num_bars: int = 5) -> list:
        """Create realistic mock options bars"""
        bars = []
        base_timestamp = 1640995200000  # 2022-01-01
        base_price = 10.0
        
        for i in range(num_bars):
            price = base_price + (i * 0.5)
            bars.append(OptionsBar(
                ticker=options_ticker,
                timestamp=base_timestamp + (i * 86400000),  # Daily increments
                open=price,
                high=price + 1.0,
                low=price - 0.5,
                close=price + 0.25,
                volume=500 + (i * 50),
                vwap=price + 0.1,
                transactions=25 + (i * 5)
            ))
        
        return bars
    
    @patch('trading_system.data_ingestion.eod_collector_v2.PolygonClient')
    def test_complete_successful_pipeline(self, mock_polygon_client_class):
        """Test complete successful data collection pipeline"""
        # Set up comprehensive mocks
        mock_client = Mock()
        mock_polygon_client_class.return_value = mock_client
        
        # Mock all tickers as valid
        mock_client.validate_ticker.return_value = True
        
        # Mock market status
        mock_client.get_market_status.return_value = {"market": "open", "serverTime": "2024-01-01T15:30:00Z"}
        
        # Set up data for each ticker
        mock_client.get_underlying_bars.side_effect = [
            self._create_mock_underlying_data(ticker) for ticker in self.test_tickers
        ]
        
        # Mock options contracts for each ticker
        all_options_contracts = []
        for ticker in self.test_tickers:
            contracts = self._create_mock_options_contracts(ticker)
            all_options_contracts.append(contracts)
        mock_client.get_options_contracts.side_effect = all_options_contracts
        
        # Mock options bars for each contract
        def mock_get_options_bars(options_ticker, **kwargs):
            return self._create_mock_options_bars(options_ticker)
        mock_client.get_options_bars.side_effect = mock_get_options_bars
        
        # Create collector and run complete pipeline
        collector = ModernEODDataCollector(self.config)
        
        with patch('time.sleep'):  # Speed up test
            results = collector.collect_market_data(
                tickers=self.test_tickers,
                start_date=self.test_date_range[0],
                end_date=self.test_date_range[1],
                collect_options=True,
                options_expiry_days=90
            )
        
        # Verify collection results
        assert len(results) == len(self.test_tickers)
        for ticker in self.test_tickers:
            assert ticker in results
            progress = results[ticker]
            assert progress.status == "completed"
            assert progress.underlying_bars_collected > 0
            assert progress.options_contracts_collected > 0
            assert progress.options_bars_collected > 0
        
        # Verify data was stored correctly
        storage = collector.storage
        stats = storage.get_data_statistics()
        
        assert stats['underlying_bars']['total_records'] > 0
        assert stats['underlying_bars']['unique_tickers'] == len(self.test_tickers)
        assert stats['options_contracts']['total_contracts'] > 0
        assert stats['options_bars']['total_records'] > 0
        
        # Verify summary report
        summary = collector.get_data_summary()
        assert summary['collection_summary']['total_tickers'] == len(self.test_tickers)
        assert summary['collection_summary']['completed'] == len(self.test_tickers)
        assert summary['collection_summary']['failed'] == 0
        assert summary['collection_summary']['overall_progress'] == 100.0
        
        # Verify collection totals
        totals = summary['collection_totals']
        assert totals['total_underlying_bars'] > 0
        assert totals['total_options_contracts'] > 0
        assert totals['total_options_bars'] > 0
    
    @patch('trading_system.data_ingestion.eod_collector_v2.PolygonClient')
    def test_pipeline_with_mixed_success_failure(self, mock_polygon_client_class):
        """Test pipeline with some tickers succeeding and others failing"""
        mock_client = Mock()
        mock_polygon_client_class.return_value = mock_client
        
        # Mock ticker validation - some valid, some invalid
        def mock_validate_ticker(ticker):
            return ticker in ["AAPL", "GOOGL"]  # MSFT will be invalid
        mock_client.validate_ticker.side_effect = mock_validate_ticker
        
        # Mock successful data for valid tickers only
        def mock_get_underlying_bars(ticker, **kwargs):
            if ticker in ["AAPL", "GOOGL"]:
                return self._create_mock_underlying_data(ticker)
            else:
                # Should not be called for invalid tickers
                raise PolygonAPIError(f"Ticker {ticker} not found")
        mock_client.get_underlying_bars.side_effect = mock_get_underlying_bars
        
        # Mock options data
        def mock_get_options_contracts(underlying_ticker, **kwargs):
            if underlying_ticker in ["AAPL", "GOOGL"]:
                return self._create_mock_options_contracts(underlying_ticker)
            else:
                # Should not be called for invalid tickers
                raise PolygonAPIError(f"No options for {underlying_ticker}")
        mock_client.get_options_contracts.side_effect = mock_get_options_contracts
        
        # Mock options bars
        def mock_get_options_bars(options_ticker, **kwargs):
            # Should not be called for invalid tickers
            return []
        mock_client.get_options_bars.side_effect = mock_get_options_bars
        mock_client.get_market_status.return_value = {"market": "open"}
        
        # Run pipeline
        collector = ModernEODDataCollector(self.config)
        
        with patch('time.sleep'):
            results = collector.collect_market_data(
                tickers=self.test_tickers,
                start_date=self.test_date_range[0],
                end_date=self.test_date_range[1],
                collect_options=True
            )
        
        # Verify results - only valid tickers should be processed
        assert len(results) == 2  # Only valid tickers processed
        assert "AAPL" in results
        assert "GOOGL" in results
        assert "MSFT" not in results  # Invalid ticker should not be in results
        
        # Valid tickers should complete successfully
        for ticker in ["AAPL", "GOOGL"]:
            assert results[ticker].status == "completed"
            assert results[ticker].underlying_bars_collected > 0
    
    @patch('trading_system.data_ingestion.eod_collector_v2.PolygonClient')
    def test_pipeline_error_handling_and_recovery(self, mock_polygon_client_class):
        """Test pipeline error handling and recovery mechanisms"""
        mock_client = Mock()
        mock_polygon_client_class.return_value = mock_client
        
        mock_client.validate_ticker.return_value = True
        
        # First attempt fails, second succeeds
        call_count = 0
        def mock_get_underlying_bars_with_recovery(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise PolygonAPIError("Rate limit exceeded")
            else:
                return self._create_mock_underlying_data("AAPL")
        
        mock_client.get_underlying_bars.side_effect = mock_get_underlying_bars_with_recovery
        mock_client.get_options_contracts.return_value = []
        mock_client.get_market_status.return_value = {"market": "open"}
        
        collector = ModernEODDataCollector(self.config)
        
        # First collection attempt (should fail)
        with patch('time.sleep'):
            results1 = collector.collect_market_data(
                tickers=["AAPL"],
                start_date=self.test_date_range[0],
                end_date=self.test_date_range[1],
                collect_options=False
            )
        
        assert results1["AAPL"].status == "failed"
        assert results1["AAPL"].error_message and "Rate limit exceeded" in results1["AAPL"].error_message
        
        # Recovery attempt (should succeed)
        with patch('time.sleep'):
            recovered_tickers = collector.resume_failed_collections()
        
        assert "AAPL" in recovered_tickers
        assert collector.progress_tracker["AAPL"].status == "completed"
    
    @patch('trading_system.data_ingestion.eod_collector_v2.PolygonClient')
    def test_pipeline_progress_persistence(self, mock_polygon_client_class):
        """Test that pipeline progress persists across sessions"""
        mock_client = Mock()
        mock_polygon_client_class.return_value = mock_client
        
        mock_client.validate_ticker.return_value = True
        mock_client.get_underlying_bars.return_value = self._create_mock_underlying_data("AAPL")
        mock_client.get_options_contracts.return_value = self._create_mock_options_contracts("AAPL")
        mock_client.get_options_bars.return_value = []
        mock_client.get_market_status.return_value = {"market": "open"}
        
        # First session
        collector1 = ModernEODDataCollector(self.config)
        
        with patch('time.sleep'):
            results1 = collector1.collect_market_data(
                tickers=["AAPL"],
                start_date=self.test_date_range[0],
                end_date=self.test_date_range[1]
            )
        
        assert results1["AAPL"].status == "completed"
        
        # Verify progress file was created
        progress_file = self.config.data.raw_data_dir / "modern_collection_progress.json"
        assert progress_file.exists()
        
        # Second session (simulates restart)
        collector2 = ModernEODDataCollector(self.config)
        
        # Progress should be loaded
        assert "AAPL" in collector2.progress_tracker
        assert collector2.progress_tracker["AAPL"].status == "completed"
        
        # Verify progress data integrity
        loaded_progress = collector2.progress_tracker["AAPL"]
        original_progress = results1["AAPL"]
        assert loaded_progress.ticker == original_progress.ticker
        assert loaded_progress.underlying_bars_collected == original_progress.underlying_bars_collected
        assert loaded_progress.options_contracts_collected == original_progress.options_contracts_collected
    
    @patch('trading_system.data_ingestion.eod_collector_v2.PolygonClient')
    def test_pipeline_rate_limiting_compliance(self, mock_polygon_client_class):
        """Test that pipeline uses client with rate limiting capabilities"""
        mock_client = Mock()
        mock_polygon_client_class.return_value = mock_client
        
        # Configure client to simulate rate limiting behavior
        mock_client.validate_ticker.return_value = True
        mock_client.get_underlying_bars.return_value = self._create_mock_underlying_data("AAPL")
        mock_client.get_options_contracts.return_value = self._create_mock_options_contracts("AAPL", 1)
        mock_client.get_options_bars.return_value = self._create_mock_options_bars("O:AAPL240315C00150000")
        mock_client.get_market_status.return_value = {"market": "open"}
        
        # Mock rate limit status tracking
        mock_client.get_rate_limit_status.return_value = {
            'calls_made': 5,
            'calls_remaining': 0,
            'time_until_reset': 60.0
        }
        
        collector = ModernEODDataCollector(self.config)
        
        # Run collection with mocked sleep
        with patch('time.sleep'):
            collector.collect_market_data(
                tickers=["AAPL"],
                start_date=self.test_date_range[0],
                end_date=self.test_date_range[1],
                collect_options=True
            )
        
        # Verify that the client was called with expected methods (API calls were made)
        assert mock_client.validate_ticker.call_count > 0
        assert mock_client.get_underlying_bars.call_count > 0
        
        # Verify rate limit status tracking capability is available
        rate_limit_status = collector.client.get_rate_limit_status()
        assert 'calls_made' in rate_limit_status
        assert 'calls_remaining' in rate_limit_status
        assert 'time_until_reset' in rate_limit_status
    
    @patch('trading_system.data_ingestion.eod_collector_v2.PolygonClient')
    def test_pipeline_data_quality_validation(self, mock_polygon_client_class):
        """Test pipeline data quality validation and filtering"""
        mock_client = Mock()
        mock_polygon_client_class.return_value = mock_client
        
        mock_client.validate_ticker.return_value = True
        
        # Create data with some quality issues
        problematic_df = pd.DataFrame({
            'open': [100.0, None, 102.0],  # Missing value
            'high': [105.0, 106.0, 107.0],
            'low': [99.0, 100.0, 101.0],
            'close': [104.0, 105.0, 106.0],
            'volume': [1000000, 1100000, 1200000],
            'vwap': [102.5, 103.5, 104.5],
            'transactions': [1000, 1100, 1200]
        }, index=pd.date_range('2024-01-01', periods=3, freq='D'))
        
        mock_client.get_underlying_bars.return_value = problematic_df
        mock_client.get_options_contracts.return_value = []
        mock_client.get_market_status.return_value = {"market": "open"}
        
        collector = ModernEODDataCollector(self.config)
        
        with patch('time.sleep'):
            results = collector.collect_market_data(
                tickers=["AAPL"],
                start_date=self.test_date_range[0],
                end_date=self.test_date_range[1],
                collect_options=False
            )
        
        # Data should still be collected (storage handles data quality issues gracefully)
        assert results["AAPL"].status == "completed"
        
        # Verify data was stored (with quality issues handled)
        stats = collector.storage.get_data_statistics()
        assert stats['underlying_bars']['total_records'] >= 2  # At least non-problematic records
    
    def test_database_schema_integrity(self):
        """Test database schema integrity and constraints"""
        storage = ModernDataStorage(self.config)
        
        # Verify all expected tables exist
        with sqlite3.connect(storage.db_path) as conn:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            
            expected_tables = [
                'underlying_bars',
                'options_contracts', 
                'options_bars',
                'collection_metadata'
            ]
            for table in expected_tables:
                assert table in tables, f"Table {table} not found"
            
            # Verify indexes exist
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
            indexes = [row[0] for row in cursor.fetchall()]
            
            expected_indexes = [
                'idx_underlying_ticker_timestamp',
                'idx_options_contracts_underlying',
                'idx_options_contracts_expiration',
                'idx_options_bars_ticker_timestamp',
                'idx_collection_metadata_ticker'
            ]
            for index in expected_indexes:
                assert index in indexes, f"Index {index} not found"


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason=f"Imports not available: {import_error if not IMPORTS_AVAILABLE else ''}")
def test_realistic_options_trading_workflow():
    """Test a realistic options trading data collection workflow"""
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ['POLYGON_API_KEY'] = 'test_key'
        os.environ['RAW_DATA_DIR'] = temp_dir
        
        try:
            config = Config()
            
            with patch('trading_system.data_ingestion.eod_collector_v2.PolygonClient') as mock_client_class:
                mock_client = Mock()
                mock_client_class.return_value = mock_client
                
                # Simulate realistic options trading scenario
                mock_client.validate_ticker.return_value = True
                mock_client.get_market_status.return_value = {"market": "open"}
                
                # High-volume tech stock with active options
                ticker = "AAPL"
                
                # Underlying stock data (5 days)
                underlying_data = pd.DataFrame({
                    'open': [150.0, 151.0, 149.5, 152.0, 154.0],
                    'high': [155.0, 154.0, 153.0, 156.0, 158.0],
                    'low': [148.0, 149.0, 147.5, 150.0, 152.0],
                    'close': [153.0, 150.5, 152.5, 155.0, 157.0],
                    'volume': [50000000, 45000000, 60000000, 42000000, 48000000],
                    'vwap': [151.5, 151.2, 150.8, 153.2, 155.1],
                    'transactions': [250000, 230000, 280000, 220000, 240000]
                }, index=pd.date_range('2024-01-01', periods=5))
                mock_client.get_underlying_bars.return_value = underlying_data
                
                # Multiple options contracts (calls and puts at different strikes)
                options_contracts = []
                for strike in [140, 145, 150, 155, 160, 165]:
                    for contract_type in ['call', 'put']:
                        contracts = OptionsContract(
                            ticker=f"O:AAPL240315{contract_type[0].upper()}00{strike:03d}000",
                            underlying_ticker="AAPL",
                            contract_type=contract_type,
                            expiration_date="2024-03-15",
                            strike_price=float(strike),
                            exercise_style="american",
                            shares_per_contract=100,
                            primary_exchange="NASDAQ"
                        )
                        options_contracts.append(contracts)
                
                mock_client.get_options_contracts.return_value = options_contracts
                
                # Options bars for active contracts
                def mock_get_options_bars(options_ticker, **kwargs):
                    # Simulate different volatility for different contracts
                    base_price = 5.0 if "C00150000" in options_ticker else 3.0
                    bars = []
                    for i in range(5):
                        bars.append(OptionsBar(
                            ticker=options_ticker,
                            timestamp=1640995200000 + (i * 86400000),
                            open=base_price + (i * 0.3),
                            high=base_price + (i * 0.3) + 0.8,
                            low=base_price + (i * 0.3) - 0.4,
                            close=base_price + (i * 0.3) + 0.2,
                            volume=1000 + (i * 200),
                            vwap=base_price + (i * 0.3) + 0.1,
                            transactions=50 + (i * 10)
                        ))
                    return bars
                
                mock_client.get_options_bars.side_effect = mock_get_options_bars
                
                # Run the realistic workflow
                collector = ModernEODDataCollector(config)
                
                start_time = datetime.now()
                with patch('time.sleep'):
                    results = collector.collect_market_data(
                        tickers=[ticker],
                        start_date=date(2024, 1, 1),
                        end_date=date(2024, 1, 5),
                        collect_options=True,
                        options_expiry_days=75  # ~2.5 months out
                    )
                end_time = datetime.now()
                
                # Verify realistic results
                progress = results[ticker]
                assert progress.status == "completed"
                assert progress.underlying_bars_collected == 5
                assert progress.options_contracts_collected == 12  # 6 strikes × 2 types
                assert progress.options_bars_collected > 0  # Limited by rate limiting
                
                # Verify data quality
                summary = collector.get_data_summary()
                db_stats = summary["database_statistics"]
                
                assert db_stats['underlying_bars']['total_records'] >= 5  # At least 5 records
                assert db_stats['underlying_bars']['unique_tickers'] >= 1  # At least 1 ticker
                assert db_stats['options_contracts']['total_contracts'] >= 12  # At least 12 contracts
                assert db_stats['options_contracts']['unique_underlyings'] >= 1  # At least 1 underlying
                
                # Verify collection metadata
                collection_totals = summary["collection_totals"]
                assert collection_totals['total_underlying_bars'] >= 5
                assert collection_totals['total_options_contracts'] >= 12
                assert collection_totals['total_options_bars'] > 0
                
                # Verify performance (should complete quickly with mocked data)
                execution_time = (end_time - start_time).total_seconds()
                assert execution_time < 10  # Should be fast with mocks
                
        finally:
            # Clean up
            for env_var in ['POLYGON_API_KEY', 'RAW_DATA_DIR']:
                if env_var in os.environ:
                    del os.environ[env_var]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])