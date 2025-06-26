#!/usr/bin/env python3
"""
Demonstration script for the EOD Data Collector.

This script shows how to use the EODDataCollector to collect
historical market data for multiple tickers with progress tracking.
"""

import sys
import os
from datetime import date, timedelta
from pathlib import Path

# Add src to path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from trading_system.config.settings import Config
from trading_system.data_ingestion import EODDataCollector
from trading_system.utils.logger import get_logger


def main():
    """Demonstrate EOD data collection."""
    # Set up logging
    logger = get_logger('demo')
    logger.info("Starting EOD Data Collector demonstration")
    
    try:
        # Initialize configuration
        logger.info("Initializing configuration...")
        config = Config()
        
        # Check if API key is available
        if not config.api.polygon_api_key or 'test' in config.api.polygon_api_key.lower():
            logger.warning("No valid Polygon API key found. This demo requires a real API key.")
            logger.info("Please set POLYGON_API_KEY environment variable with your API key from polygon.io")
            return
        
        # Initialize EOD collector
        logger.info("Initializing EOD Data Collector...")
        collector = EODDataCollector(config)
        
        # Define collection parameters
        tickers = ["AAPL", "MSFT", "GOOGL"]  # Small set for demo
        end_date = date.today() - timedelta(days=1)  # Yesterday
        start_date = end_date - timedelta(days=30)   # Last 30 days
        
        logger.info(f"Collecting data for {tickers} from {start_date} to {end_date}")
        
        # Check if we have any existing progress
        existing_progress = collector.get_collection_status()
        if existing_progress:
            logger.info("Found existing collection progress:")
            for ticker, status in existing_progress.items():
                logger.info(f"  {ticker}: {status['status']} ({status['progress_percentage']:.1f}%)")
        
        # Collect historical data
        logger.info("Starting data collection...")
        progress_tracker = collector.collect_historical_data(
            tickers=tickers,
            start_date=start_date,
            end_date=end_date,
            resume=True
        )
        
        # Show final status
        logger.info("Data collection completed. Final status:")
        final_status = collector.get_collection_status()
        for ticker, status in final_status.items():
            logger.info(f"  {ticker}: {status['status']} ({status['progress_percentage']:.1f}%)")
            if status['error_message']:
                logger.error(f"    Error: {status['error_message']}")
        
        # Get data summary
        summary = collector.get_data_summary()
        logger.info("Data summary:")
        logger.info(f"  Total tickers: {summary['total_tickers']}")
        logger.info(f"  Completed: {summary['completed']}")
        logger.info(f"  Failed: {summary['failed']}")
        logger.info(f"  Overall progress: {summary['overall_progress']:.1f}%")
        
        if 'total_ohlcv_records' in summary:
            logger.info(f"  Total OHLCV records: {summary['total_ohlcv_records']}")
        if 'total_news_articles' in summary:
            logger.info(f"  Total news articles: {summary['total_news_articles']}")
        if 'data_date_range' in summary:
            date_range = summary['data_date_range']
            logger.info(f"  Data date range: {date_range['start']} to {date_range['end']}")
        
        # Demonstrate resuming failed collections
        failed_tickers = collector.resume_failed_collections()
        if failed_tickers:
            logger.info(f"Resumed collection for {len(failed_tickers)} failed tickers: {failed_tickers}")
        else:
            logger.info("No failed collections to resume")
        
        logger.info("EOD Data Collector demonstration completed successfully!")
        
    except Exception as e:
        logger.error(f"Error during demonstration: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


def demo_with_mock_data():
    """Demonstrate the collector with mock data (for testing without API key)."""
    logger = get_logger('demo_mock')
    logger.info("Starting mock data demonstration")
    
    try:
        from unittest.mock import Mock, patch
        
        # Mock the config to avoid API key requirement
        mock_config = Mock()
        mock_config.api.polygon_api_key = "mock_key"
        mock_config.api.polygon_rate_limit = 5
        mock_config.api.polygon_max_retries = 3
        mock_config.data.raw_data_dir = Path("./demo_data")
        
        # Create the directory
        mock_config.data.raw_data_dir.mkdir(exist_ok=True)
        
        with patch('trading_system.data_ingestion.eod_collector.PolygonClient') as mock_client_class:
            # Set up mock client
            mock_client = Mock()
            mock_client_class.return_value = mock_client
            
            # Mock API responses
            from trading_system.data_ingestion.models import OHLCVData, NewsArticle
            from decimal import Decimal
            from datetime import datetime
            
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
                    id="mock-123",
                    title="Mock News Article",
                    published_utc=datetime(2024, 1, 15, 12, 0, 0),
                    tickers=["AAPL"]
                )
            ]
            
            mock_client.get_stock_bars.return_value = mock_ohlcv
            mock_client.get_news.return_value = mock_news
            
            # Initialize collector
            collector = EODDataCollector(mock_config)
            
            # Collect data
            tickers = ["AAPL", "MSFT"]
            start_date = date(2024, 1, 1)
            end_date = date(2024, 1, 31)
            
            logger.info(f"Mock collecting data for {tickers} from {start_date} to {end_date}")
            
            progress_tracker = collector.collect_historical_data(
                tickers=tickers,
                start_date=start_date,
                end_date=end_date
            )
            
            # Show results
            status = collector.get_collection_status()
            for ticker, ticker_status in status.items():
                logger.info(f"{ticker}: {ticker_status['status']} ({ticker_status['progress_percentage']:.1f}%)")
            
            summary = collector.get_data_summary()
            logger.info(f"Mock data summary: {summary}")
            
            logger.info("Mock demonstration completed successfully!")
            
    except Exception as e:
        logger.error(f"Error during mock demonstration: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    # Check if we should run with mock data
    if len(sys.argv) > 1 and sys.argv[1] == "--mock":
        exit_code = demo_with_mock_data()
    else:
        exit_code = main()
    
    sys.exit(exit_code)