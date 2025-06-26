"""
End-of-Day (EOD) Data Collector.

This module handles the collection of market data for multiple tickers,
including historical data fetching, progress tracking, and resumable downloads.
"""

import json
import sqlite3
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, asdict

from ..config.settings import Config
from ..utils.logger import get_logger
from .polygon_client import PolygonClient, PolygonAPIError
from .models import OHLCVData, NewsArticle, OptionsContract, TechnicalIndicator, MarketData


@dataclass
class CollectionProgress:
    """Tracks progress of data collection."""
    
    ticker: str
    start_date: date
    end_date: date
    last_collected_date: Optional[date] = None
    total_days: int = 0
    completed_days: int = 0
    status: str = "pending"  # pending, in_progress, completed, failed
    error_message: Optional[str] = None
    last_updated: Optional[datetime] = None
    
    def __post_init__(self):
        if self.last_updated is None:
            self.last_updated = datetime.utcnow()
        
        if self.total_days == 0:
            # Calculate business days (approximate)
            delta = self.end_date - self.start_date
            self.total_days = delta.days
    
    @property
    def progress_percentage(self) -> float:
        """Calculate completion percentage."""
        if self.total_days == 0:
            return 0.0
        return (self.completed_days / self.total_days) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        # Convert dates to strings for JSON serialization
        data['start_date'] = self.start_date.isoformat()
        data['end_date'] = self.end_date.isoformat()
        if self.last_collected_date:
            data['last_collected_date'] = self.last_collected_date.isoformat()
        data['last_updated'] = self.last_updated.isoformat() if self.last_updated else None
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CollectionProgress':
        """Create instance from dictionary."""
        # Convert date strings back to date objects
        data['start_date'] = date.fromisoformat(data['start_date'])
        data['end_date'] = date.fromisoformat(data['end_date'])
        if data.get('last_collected_date'):
            data['last_collected_date'] = date.fromisoformat(data['last_collected_date'])
        data['last_updated'] = datetime.fromisoformat(data['last_updated'])
        return cls(**data)


class DataStorage:
    """Handles storage of collected market data."""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = get_logger('data.storage')
        self.db_path = config.data.raw_data_dir / "market_data.db"
        self._init_database()
    
    def _init_database(self):
        """Initialize SQLite database with required tables."""
        self.config.data.raw_data_dir.mkdir(parents=True, exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ohlcv_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timestamp DATETIME NOT NULL,
                    open_price DECIMAL(10,2) NOT NULL,
                    high_price DECIMAL(10,2) NOT NULL,
                    low_price DECIMAL(10,2) NOT NULL,
                    close_price DECIMAL(10,2) NOT NULL,
                    volume INTEGER NOT NULL,
                    vwap DECIMAL(10,2),
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(symbol, timestamp)
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS news_articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    article_id TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    author TEXT,
                    published_utc DATETIME NOT NULL,
                    article_url TEXT,
                    tickers TEXT,  -- JSON array
                    keywords TEXT,  -- JSON array
                    sentiment_score REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS options_contracts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contract_symbol TEXT UNIQUE NOT NULL,
                    underlying_ticker TEXT NOT NULL,
                    strike_price DECIMAL(10,2) NOT NULL,
                    expiration_date DATE NOT NULL,
                    option_type TEXT NOT NULL,
                    last_price DECIMAL(10,2),
                    bid DECIMAL(10,2),
                    ask DECIMAL(10,2),
                    volume INTEGER,
                    open_interest INTEGER,
                    implied_volatility REAL,
                    delta REAL,
                    gamma REAL,
                    theta REAL,
                    vega REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS technical_indicators (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timestamp DATETIME NOT NULL,
                    indicator_name TEXT NOT NULL,
                    value REAL NOT NULL,
                    period INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(symbol, timestamp, indicator_name, period)
                )
            """)
            
            # Create indexes for better query performance
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ohlcv_symbol_timestamp ON ohlcv_data(symbol, timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_news_published ON news_articles(published_utc)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_options_underlying ON options_contracts(underlying_ticker)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_indicators_symbol ON technical_indicators(symbol, indicator_name)")
            
            conn.commit()
    
    def save_ohlcv_data(self, ohlcv_list: List[OHLCVData]) -> int:
        """Save OHLCV data to database."""
        if not ohlcv_list:
            return 0
        
        saved_count = 0
        with sqlite3.connect(self.db_path) as conn:
            for ohlcv in ohlcv_list:
                try:
                    conn.execute("""
                        INSERT OR REPLACE INTO ohlcv_data 
                        (symbol, timestamp, open_price, high_price, low_price, close_price, volume, vwap)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        ohlcv.symbol,
                        ohlcv.timestamp,
                        float(ohlcv.open),
                        float(ohlcv.high),
                        float(ohlcv.low),
                        float(ohlcv.close),
                        ohlcv.volume,
                        float(ohlcv.vwap) if ohlcv.vwap else None
                    ))
                    saved_count += 1
                except sqlite3.Error as e:
                    self.logger.warning(f"Failed to save OHLCV data for {ohlcv.symbol}: {e}")
            
            conn.commit()
        
        self.logger.debug(f"Saved {saved_count} OHLCV records")
        return saved_count
    
    def save_news_articles(self, articles: List[NewsArticle]) -> int:
        """Save news articles to database."""
        if not articles:
            return 0
        
        saved_count = 0
        with sqlite3.connect(self.db_path) as conn:
            for article in articles:
                try:
                    conn.execute("""
                        INSERT OR REPLACE INTO news_articles 
                        (article_id, title, description, author, published_utc, article_url, tickers, keywords, sentiment_score)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        article.id,
                        article.title,
                        article.description,
                        article.author,
                        article.published_utc,
                        article.article_url,
                        json.dumps(article.tickers),
                        json.dumps(article.keywords),
                        article.sentiment_score
                    ))
                    saved_count += 1
                except sqlite3.Error as e:
                    self.logger.warning(f"Failed to save news article {article.id}: {e}")
            
            conn.commit()
        
        self.logger.debug(f"Saved {saved_count} news articles")
        return saved_count
    
    def get_last_collected_date(self, symbol: str) -> Optional[date]:
        """Get the last date for which data was collected for a symbol."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT MAX(DATE(timestamp)) FROM ohlcv_data WHERE symbol = ?
            """, (symbol,))
            result = cursor.fetchone()
            
            if result and result[0]:
                return date.fromisoformat(result[0])
            return None


class EODDataCollector:
    """End-of-Day data collector for market data."""
    
    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self.client = PolygonClient(self.config)
        self.storage = DataStorage(self.config)
        self.logger = get_logger('data.collector')
        self.progress_file = self.config.data.raw_data_dir / "collection_progress.json"
        self._load_progress()
    
    def _load_progress(self):
        """Load collection progress from file."""
        self.progress_tracker: Dict[str, CollectionProgress] = {}
        
        if self.progress_file.exists():
            try:
                with open(self.progress_file, 'r') as f:
                    data = json.load(f)
                    for ticker, progress_data in data.items():
                        self.progress_tracker[ticker] = CollectionProgress.from_dict(progress_data)
                self.logger.info(f"Loaded progress for {len(self.progress_tracker)} tickers")
            except Exception as e:
                self.logger.warning(f"Failed to load progress file: {e}")
    
    def _save_progress(self):
        """Save collection progress to file."""
        try:
            self.config.data.raw_data_dir.mkdir(parents=True, exist_ok=True)
            data = {ticker: progress.to_dict() for ticker, progress in self.progress_tracker.items()}
            with open(self.progress_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            self.logger.error(f"Failed to save progress file: {e}")
    
    def collect_historical_data(
        self,
        tickers: List[str],
        start_date: date,
        end_date: Optional[date] = None,
        resume: bool = True
    ) -> Dict[str, CollectionProgress]:
        """
        Collect historical data for multiple tickers.
        
        Args:
            tickers: List of ticker symbols
            start_date: Start date for data collection
            end_date: End date for data collection (defaults to yesterday)
            resume: Whether to resume from last collected date
        
        Returns:
            Dictionary mapping ticker to collection progress
        """
        if end_date is None:
            end_date = date.today() - timedelta(days=1)  # Yesterday
        
        self.logger.info(f"Starting data collection for {len(tickers)} tickers from {start_date} to {end_date}")
        
        # Initialize or update progress tracking
        for ticker in tickers:
            if ticker not in self.progress_tracker or not resume:
                self.progress_tracker[ticker] = CollectionProgress(
                    ticker=ticker,
                    start_date=start_date,
                    end_date=end_date
                )
            else:
                # Update end date if needed
                self.progress_tracker[ticker].end_date = end_date
        
        # Collect data for each ticker
        for ticker in tickers:
            try:
                self._collect_ticker_data(ticker)
            except Exception as e:
                self.logger.error(f"Failed to collect data for {ticker}: {e}")
                self.progress_tracker[ticker].status = "failed"
                self.progress_tracker[ticker].error_message = str(e)
            
            # Save progress after each ticker
            self._save_progress()
        
        self.logger.info("Data collection completed")
        return self.progress_tracker
    
    def _collect_ticker_data(self, ticker: str):
        """Collect data for a single ticker."""
        progress = self.progress_tracker[ticker]
        progress.status = "in_progress"
        progress.last_updated = datetime.utcnow()
        
        # Determine collection start date
        collection_start = progress.start_date
        if progress.last_collected_date:
            collection_start = progress.last_collected_date + timedelta(days=1)
        
        # Check if already completed
        if collection_start > progress.end_date:
            progress.status = "completed"
            self.logger.info(f"Data collection for {ticker} already completed")
            return
        
        self.logger.info(f"Collecting data for {ticker} from {collection_start} to {progress.end_date}")
        
        try:
            # Collect OHLCV data
            ohlcv_data = self.client.get_stock_bars(
                symbol=ticker,
                start_date=collection_start,
                end_date=progress.end_date,
                timespan="day",
                limit=5000
            )
            
            if ohlcv_data:
                saved_count = self.storage.save_ohlcv_data(ohlcv_data)
                self.logger.info(f"Saved {saved_count} OHLCV records for {ticker}")
                
                # Update progress
                progress.last_collected_date = progress.end_date
                progress.completed_days = (progress.end_date - progress.start_date).days
                progress.status = "completed"
            else:
                self.logger.warning(f"No OHLCV data returned for {ticker}")
            
            # Collect recent news (last 30 days)
            news_start = max(collection_start, progress.end_date - timedelta(days=30))
            news_articles = self.client.get_news(
                symbol=ticker,
                start_date=news_start,
                end_date=progress.end_date,
                limit=100
            )
            
            if news_articles:
                saved_news = self.storage.save_news_articles(news_articles)
                self.logger.info(f"Saved {saved_news} news articles for {ticker}")
            
        except PolygonAPIError as e:
            progress.status = "failed"
            progress.error_message = str(e)
            self.logger.error(f"API error collecting data for {ticker}: {e}")
            raise
        except Exception as e:
            progress.status = "failed" 
            progress.error_message = str(e)
            self.logger.error(f"Unexpected error collecting data for {ticker}: {e}")
            raise
        
        progress.last_updated = datetime.utcnow()
    
    def get_collection_status(self) -> Dict[str, Dict[str, Any]]:
        """Get current collection status for all tickers."""
        status = {}
        for ticker, progress in self.progress_tracker.items():
            status[ticker] = {
                "status": progress.status,
                "progress_percentage": progress.progress_percentage,
                "last_collected_date": progress.last_collected_date.isoformat() if progress.last_collected_date else None,
                "error_message": progress.error_message,
                "last_updated": progress.last_updated.isoformat() if progress.last_updated else None
            }
        return status
    
    def resume_failed_collections(self) -> List[str]:
        """Resume collections that failed previously."""
        failed_tickers = [
            ticker for ticker, progress in self.progress_tracker.items()
            if progress.status == "failed"
        ]
        
        if not failed_tickers:
            self.logger.info("No failed collections to resume")
            return []
        
        self.logger.info(f"Resuming collection for {len(failed_tickers)} failed tickers")
        
        for ticker in failed_tickers:
            # Reset error state
            self.progress_tracker[ticker].status = "pending"
            self.progress_tracker[ticker].error_message = None
            
            try:
                self._collect_ticker_data(ticker)
            except Exception as e:
                self.logger.error(f"Failed to resume collection for {ticker}: {e}")
        
        self._save_progress()
        return failed_tickers
    
    def get_data_summary(self) -> Dict[str, Any]:
        """Get summary of collected data."""
        summary = {
            "total_tickers": len(self.progress_tracker),
            "completed": sum(1 for p in self.progress_tracker.values() if p.status == "completed"),
            "failed": sum(1 for p in self.progress_tracker.values() if p.status == "failed"),
            "in_progress": sum(1 for p in self.progress_tracker.values() if p.status == "in_progress"),
            "overall_progress": 0.0
        }
        
        if summary["total_tickers"] > 0:
            total_progress = sum(p.progress_percentage for p in self.progress_tracker.values())
            summary["overall_progress"] = total_progress / summary["total_tickers"]
        
        # Get database statistics
        try:
            with sqlite3.connect(self.storage.db_path) as conn:
                # Count OHLCV records
                cursor = conn.execute("SELECT COUNT(*) FROM ohlcv_data")
                summary["total_ohlcv_records"] = cursor.fetchone()[0]
                
                # Count news articles
                cursor = conn.execute("SELECT COUNT(*) FROM news_articles")
                summary["total_news_articles"] = cursor.fetchone()[0]
                
                # Get date range
                cursor = conn.execute("SELECT MIN(DATE(timestamp)), MAX(DATE(timestamp)) FROM ohlcv_data")
                result = cursor.fetchone()
                if result[0] and result[1]:
                    summary["data_date_range"] = {
                        "start": result[0],
                        "end": result[1]
                    }
        except Exception as e:
            self.logger.warning(f"Failed to get data summary from database: {e}")
        
        return summary