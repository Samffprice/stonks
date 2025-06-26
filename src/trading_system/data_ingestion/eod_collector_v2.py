"""
End-of-Day (EOD) Data Collector V2 - Modern Implementation

This module handles the collection of market data using the new Polygon client,
with focus on options data, underlying stock data, and comprehensive progress tracking.
"""

import json
import sqlite3
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, asdict
import pandas as pd

from ..config.settings import Config
from ..utils.logger import get_logger
from .polygon_client import (
    PolygonClient, 
    PolygonAPIError,
    TimeFrame,
    OptionsContract,
    OptionsBar,
)


@dataclass
class CollectionProgress:
    """Tracks progress of data collection for a ticker."""
    
    ticker: str
    start_date: date
    end_date: date
    last_collected_date: Optional[date] = None
    total_days: int = 0
    completed_days: int = 0
    status: str = "pending"  # pending, in_progress, completed, failed
    error_message: Optional[str] = None
    last_updated: Optional[datetime] = None
    
    # Collection counters
    underlying_bars_collected: int = 0
    options_contracts_collected: int = 0
    options_bars_collected: int = 0
    
    def __post_init__(self):
        if self.last_updated is None:
            self.last_updated = datetime.utcnow()
        
        if self.total_days == 0:
            # Calculate business days (approximate)
            delta = self.end_date - self.start_date
            self.total_days = max(1, delta.days + 1)  # +1 to include both start and end dates
    
    @property
    def progress_percentage(self) -> float:
        """Calculate completion percentage."""
        if self.total_days == 0:
            return 0.0
        return min(100.0, (self.completed_days / self.total_days) * 100)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        # Convert dates to strings for JSON serialization
        data['start_date'] = self.start_date.isoformat()
        data['end_date'] = self.end_date.isoformat()
        if self.last_collected_date:
            data['last_collected_date'] = self.last_collected_date.isoformat()
        if self.last_updated:
            data['last_updated'] = self.last_updated.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CollectionProgress':
        """Create instance from dictionary."""
        # Convert date strings back to date objects
        data['start_date'] = date.fromisoformat(data['start_date'])
        data['end_date'] = date.fromisoformat(data['end_date'])
        if data.get('last_collected_date'):
            data['last_collected_date'] = date.fromisoformat(data['last_collected_date'])
        if data.get('last_updated'):
            data['last_updated'] = datetime.fromisoformat(data['last_updated'])
        return cls(**data)


class ModernDataStorage:
    """Modern data storage system for collected market data."""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = get_logger(f"{__name__}.ModernDataStorage")
        self.db_path = config.data.raw_data_dir / "modern_market_data.db"
        self._init_database()
    
    def _init_database(self):
        """Initialize SQLite database with modern schema."""
        self.config.data.raw_data_dir.mkdir(parents=True, exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            # Underlying stock data table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS underlying_bars (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    timestamp DATETIME NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume INTEGER NOT NULL,
                    vwap REAL,
                    transactions INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(ticker, timestamp)
                )
            """)
            
            # Options contracts table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS options_contracts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    underlying_ticker TEXT NOT NULL,
                    contract_type TEXT NOT NULL,
                    expiration_date DATE NOT NULL,
                    strike_price REAL NOT NULL,
                    exercise_style TEXT,
                    shares_per_contract INTEGER DEFAULT 100,
                    primary_exchange TEXT,
                    created_at_contract DATETIME,
                    updated_at_contract DATETIME,
                    data_collected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(ticker)
                )
            """)
            
            # Options bars table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS options_bars (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    options_ticker TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume INTEGER NOT NULL,
                    vwap REAL,
                    transactions INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(options_ticker, timestamp)
                )
            """)
            
            # Collection metadata table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS collection_metadata (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    collection_date DATE NOT NULL,
                    data_type TEXT NOT NULL,
                    records_collected INTEGER NOT NULL,
                    collection_duration_seconds REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(ticker, collection_date, data_type)
                )
            """)
            
            # Create indexes for better query performance
            conn.execute("CREATE INDEX IF NOT EXISTS idx_underlying_ticker_timestamp ON underlying_bars(ticker, timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_options_contracts_underlying ON options_contracts(underlying_ticker)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_options_contracts_expiration ON options_contracts(expiration_date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_options_bars_ticker_timestamp ON options_bars(options_ticker, timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_collection_metadata_ticker ON collection_metadata(ticker, collection_date)")
            
            conn.commit()
            self.logger.info("Database initialized successfully")
    
    def save_underlying_bars(self, ticker: str, df: pd.DataFrame) -> int:
        """Save underlying stock bars from pandas DataFrame."""
        if df.empty:
            return 0
        
        saved_count = 0
        with sqlite3.connect(self.db_path) as conn:
            for timestamp, row in df.iterrows():
                try:
                    conn.execute("""
                        INSERT OR REPLACE INTO underlying_bars 
                        (ticker, timestamp, open, high, low, close, volume, vwap, transactions)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        ticker,
                        timestamp.isoformat(),
                        float(row['open']),
                        float(row['high']),
                        float(row['low']),
                        float(row['close']),
                        int(row['volume']),
                        float(row['vwap']) if pd.notna(row['vwap']) else None,
                        int(row['transactions']) if pd.notna(row['transactions']) else None
                    ))
                    saved_count += 1
                except (sqlite3.Error, ValueError, KeyError) as e:
                    self.logger.warning(f"Failed to save bar data for {ticker} at {timestamp}: {e}")
            
            conn.commit()
        
        self.logger.debug(f"Saved {saved_count} underlying bars for {ticker}")
        return saved_count
    
    def save_options_contracts(self, contracts: List[OptionsContract]) -> int:
        """Save options contracts to database."""
        if not contracts:
            return 0
        
        saved_count = 0
        with sqlite3.connect(self.db_path) as conn:
            for contract in contracts:
                try:
                    conn.execute("""
                        INSERT OR REPLACE INTO options_contracts 
                        (ticker, underlying_ticker, contract_type, expiration_date, strike_price,
                         exercise_style, shares_per_contract, primary_exchange, created_at_contract, updated_at_contract)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        contract.ticker,
                        contract.underlying_ticker,
                        contract.contract_type,
                        contract.expiration_date,
                        float(contract.strike_price),
                        contract.exercise_style,
                        contract.shares_per_contract,
                        contract.primary_exchange,
                        contract.created_at,
                        contract.updated_at
                    ))
                    saved_count += 1
                except sqlite3.Error as e:
                    self.logger.warning(f"Failed to save options contract {contract.ticker}: {e}")
            
            conn.commit()
        
        self.logger.debug(f"Saved {saved_count} options contracts")
        return saved_count
    
    def save_options_bars(self, bars: List[OptionsBar]) -> int:
        """Save options bars to database."""
        if not bars:
            return 0
        
        saved_count = 0
        with sqlite3.connect(self.db_path) as conn:
            for bar in bars:
                try:
                    conn.execute("""
                        INSERT OR REPLACE INTO options_bars 
                        (options_ticker, timestamp, open, high, low, close, volume, vwap, transactions)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        bar.ticker,
                        bar.timestamp,
                        float(bar.open),
                        float(bar.high),
                        float(bar.low),
                        float(bar.close),
                        bar.volume,
                        float(bar.vwap) if bar.vwap is not None else None,
                        bar.transactions
                    ))
                    saved_count += 1
                except sqlite3.Error as e:
                    self.logger.warning(f"Failed to save options bar for {bar.ticker}: {e}")
            
            conn.commit()
        
        self.logger.debug(f"Saved {saved_count} options bars")
        return saved_count
    
    def save_collection_metadata(self, ticker: str, collection_date: date, data_type: str, 
                                records_collected: int, duration_seconds: float):
        """Save collection metadata for tracking."""
        with sqlite3.connect(self.db_path) as conn:
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO collection_metadata 
                    (ticker, collection_date, data_type, records_collected, collection_duration_seconds)
                    VALUES (?, ?, ?, ?, ?)
                """, (ticker, collection_date.isoformat(), data_type, records_collected, duration_seconds))
                conn.commit()
            except sqlite3.Error as e:
                self.logger.warning(f"Failed to save collection metadata: {e}")
    
    def get_last_collected_date(self, ticker: str) -> Optional[date]:
        """Get the last date for which data was collected for a ticker."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT MAX(DATE(timestamp)) FROM underlying_bars WHERE ticker = ?
            """, (ticker,))
            result = cursor.fetchone()
            
            if result and result[0]:
                return date.fromisoformat(result[0])
            return None
    
    def get_data_statistics(self) -> Dict[str, Any]:
        """Get comprehensive data statistics."""
        stats = {}
        
        with sqlite3.connect(self.db_path) as conn:
            # Underlying bars statistics
            cursor = conn.execute("""
                SELECT 
                    COUNT(*) as total_bars,
                    COUNT(DISTINCT ticker) as unique_tickers,
                    MIN(DATE(timestamp)) as earliest_date,
                    MAX(DATE(timestamp)) as latest_date
                FROM underlying_bars
            """)
            result = cursor.fetchone()
            stats['underlying_bars'] = {
                'total_records': result[0],
                'unique_tickers': result[1],
                'earliest_date': result[2],
                'latest_date': result[3]
            }
            
            # Options contracts statistics
            cursor = conn.execute("""
                SELECT 
                    COUNT(*) as total_contracts,
                    COUNT(DISTINCT underlying_ticker) as unique_underlyings,
                    COUNT(DISTINCT contract_type) as contract_types
                FROM options_contracts
            """)
            result = cursor.fetchone()
            stats['options_contracts'] = {
                'total_contracts': result[0],
                'unique_underlyings': result[1],
                'contract_types': result[2]
            }
            
            # Options bars statistics
            cursor = conn.execute("""
                SELECT 
                    COUNT(*) as total_bars,
                    COUNT(DISTINCT options_ticker) as unique_options_tickers
                FROM options_bars
            """)
            result = cursor.fetchone()
            stats['options_bars'] = {
                'total_records': result[0],
                'unique_options_tickers': result[1]
            }
        
        return stats


class ModernEODDataCollector:
    """Modern End-of-Day data collector focused on options and underlying data."""
    
    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self.client = PolygonClient(self.config)
        self.storage = ModernDataStorage(self.config)
        self.logger = get_logger(f"{__name__}.ModernEODDataCollector")
        self.progress_file = self.config.data.raw_data_dir / "modern_collection_progress.json"
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
    
    def collect_market_data(
        self,
        tickers: List[str],
        start_date: date,
        end_date: Optional[date] = None,
        collect_options: bool = True,
        options_expiry_days: int = 90,
        resume: bool = True
    ) -> Dict[str, CollectionProgress]:
        """
        Collect comprehensive market data for multiple tickers.
        
        Args:
            tickers: List of ticker symbols
            start_date: Start date for data collection
            end_date: End date for data collection (defaults to yesterday)
            collect_options: Whether to collect options data
            options_expiry_days: How many days ahead to look for options expiry
            resume: Whether to resume from last collected date
        
        Returns:
            Dictionary mapping ticker to collection progress
        """
        if end_date is None:
            end_date = date.today() - timedelta(days=1)  # Yesterday
        
        self.logger.info(
            f"Starting modern data collection for {len(tickers)} tickers "
            f"from {start_date} to {end_date} (options: {collect_options})"
        )
        
        # Validate tickers first
        valid_tickers = []
        for ticker in tickers:
            if self.client.validate_ticker(ticker):
                valid_tickers.append(ticker)
                self.logger.info(f"✓ Ticker {ticker} validated")
            else:
                self.logger.warning(f"✗ Ticker {ticker} is invalid, skipping")
        
        self.logger.info(f"Proceeding with {len(valid_tickers)} valid tickers")
        
        # Initialize or update progress tracking
        for ticker in valid_tickers:
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
        for ticker in valid_tickers:
            try:
                self._collect_ticker_data(ticker, collect_options, options_expiry_days)
            except Exception as e:
                self.logger.error(f"Failed to collect data for {ticker}: {e}")
                self.progress_tracker[ticker].status = "failed"
                self.progress_tracker[ticker].error_message = str(e)
            
            # Save progress after each ticker
            self._save_progress()
        
        # Get market status for reference
        try:
            market_status = self.client.get_market_status()
            self.logger.info(f"Market status: {market_status.get('market', 'unknown')}")
        except Exception as e:
            self.logger.warning(f"Could not get market status: {e}")
        
        self.logger.info("Modern data collection completed")
        return self.progress_tracker
    
    def _collect_ticker_data(self, ticker: str, collect_options: bool, options_expiry_days: int):
        """Collect comprehensive data for a single ticker."""
        progress = self.progress_tracker[ticker]
        progress.status = "in_progress"
        progress.last_updated = datetime.utcnow()
        
        start_time = datetime.utcnow()
        
        try:
            # 1. Collect underlying stock data
            self.logger.info(f"Collecting underlying data for {ticker}")
            underlying_start_time = datetime.utcnow()
            
            df = self.client.get_underlying_bars(
                ticker=ticker,
                timespan=TimeFrame.DAY,
                from_date=progress.start_date.strftime('%Y-%m-%d'),
                to_date=progress.end_date.strftime('%Y-%m-%d'),
                limit=5000
            )
            
            if not df.empty:
                saved_count = self.storage.save_underlying_bars(ticker, df)
                progress.underlying_bars_collected = saved_count
                self.logger.info(f"✓ Collected {saved_count} underlying bars for {ticker}")
                
                # Save metadata
                duration = (datetime.utcnow() - underlying_start_time).total_seconds()
                self.storage.save_collection_metadata(
                    ticker, progress.end_date, "underlying_bars", saved_count, duration
                )
            else:
                self.logger.warning(f"No underlying data returned for {ticker}")
            
            # 2. Collect options contracts if requested
            if collect_options:
                self.logger.info(f"Collecting options contracts for {ticker}")
                options_start_time = datetime.utcnow()
                
                # Get contracts expiring within the specified days
                max_expiry = progress.end_date + timedelta(days=options_expiry_days)
                
                contracts = self.client.get_options_contracts(
                    underlying_ticker=ticker,
                    limit=1000
                )
                
                if contracts:
                    # Filter by expiration date
                    filtered_contracts = [
                        c for c in contracts 
                        if c.expiration_date and 
                        progress.start_date <= date.fromisoformat(c.expiration_date) <= max_expiry
                    ]
                    
                    if filtered_contracts:
                        saved_contracts = self.storage.save_options_contracts(filtered_contracts)
                        progress.options_contracts_collected = saved_contracts
                        self.logger.info(f"✓ Collected {saved_contracts} options contracts for {ticker}")
                        
                        # Collect bars for a sample of options contracts (limit to prevent rate limiting)
                        sample_contracts = filtered_contracts[:5]  # Limit to 5 to respect rate limits
                        total_options_bars = 0
                        
                        for contract in sample_contracts:
                            try:
                                options_bars = self.client.get_options_bars(
                                    options_ticker=contract.ticker,
                                    timespan=TimeFrame.DAY,
                                    from_date=progress.start_date.strftime('%Y-%m-%d'),
                                    to_date=progress.end_date.strftime('%Y-%m-%d'),
                                    limit=1000
                                )
                                
                                if options_bars:
                                    saved_bars = self.storage.save_options_bars(options_bars)
                                    total_options_bars += saved_bars
                            except Exception as e:
                                self.logger.warning(f"Failed to get options bars for {contract.ticker}: {e}")
                        
                        progress.options_bars_collected = total_options_bars
                        if total_options_bars > 0:
                            self.logger.info(f"✓ Collected {total_options_bars} options bars for {ticker}")
                        
                        # Save options metadata
                        duration = (datetime.utcnow() - options_start_time).total_seconds()
                        self.storage.save_collection_metadata(
                            ticker, progress.end_date, "options_data", 
                            saved_contracts + total_options_bars, duration
                        )
                    else:
                        self.logger.info(f"No options contracts in date range for {ticker}")
                else:
                    self.logger.warning(f"No options contracts returned for {ticker}")
            
            # Update progress completion
            progress.last_collected_date = progress.end_date
            progress.completed_days = (progress.end_date - progress.start_date).days + 1
            progress.status = "completed"
            
            total_duration = (datetime.utcnow() - start_time).total_seconds()
            self.logger.info(f"✓ Completed data collection for {ticker} in {total_duration:.2f} seconds")
            
        except PolygonAPIError as e:
            progress.status = "failed"
            progress.error_message = f"API error: {str(e)}"
            self.logger.error(f"API error collecting data for {ticker}: {e}")
            raise
        except Exception as e:
            progress.status = "failed" 
            progress.error_message = f"Unexpected error: {str(e)}"
            self.logger.error(f"Unexpected error collecting data for {ticker}: {e}")
            raise
        
        progress.last_updated = datetime.utcnow()
    
    def get_collection_status(self) -> Dict[str, Dict[str, Any]]:
        """Get detailed collection status for all tickers."""
        status = {}
        for ticker, progress in self.progress_tracker.items():
            status[ticker] = {
                "status": progress.status,
                "progress_percentage": progress.progress_percentage,
                "last_collected_date": progress.last_collected_date.isoformat() if progress.last_collected_date else None,
                "underlying_bars_collected": progress.underlying_bars_collected,
                "options_contracts_collected": progress.options_contracts_collected,
                "options_bars_collected": progress.options_bars_collected,
                "error_message": progress.error_message,
                "last_updated": progress.last_updated.isoformat() if progress.last_updated else None
            }
        return status
    
    def get_data_summary(self) -> Dict[str, Any]:
        """Get comprehensive summary of collected data."""
        summary = {
            "collection_summary": {
                "total_tickers": len(self.progress_tracker),
                "completed": sum(1 for p in self.progress_tracker.values() if p.status == "completed"),
                "failed": sum(1 for p in self.progress_tracker.values() if p.status == "failed"),
                "in_progress": sum(1 for p in self.progress_tracker.values() if p.status == "in_progress"),
                "overall_progress": 0.0
            }
        }
        
        if summary["collection_summary"]["total_tickers"] > 0:
            total_progress = sum(p.progress_percentage for p in self.progress_tracker.values())
            summary["collection_summary"]["overall_progress"] = total_progress / summary["collection_summary"]["total_tickers"]
        
        # Get database statistics
        try:
            db_stats = self.storage.get_data_statistics()
            summary["database_statistics"] = db_stats
        except Exception as e:
            self.logger.warning(f"Failed to get database statistics: {e}")
            summary["database_statistics"] = {}
        
        # Collection totals
        summary["collection_totals"] = {
            "total_underlying_bars": sum(p.underlying_bars_collected for p in self.progress_tracker.values()),
            "total_options_contracts": sum(p.options_contracts_collected for p in self.progress_tracker.values()),
            "total_options_bars": sum(p.options_bars_collected for p in self.progress_tracker.values())
        }
        
        return summary
    
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
                self._collect_ticker_data(ticker, collect_options=True, options_expiry_days=90)
            except Exception as e:
                self.logger.error(f"Failed to resume collection for {ticker}: {e}")
        
        self._save_progress()
        return failed_tickers