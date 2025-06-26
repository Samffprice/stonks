"""Configuration settings for the AI Options Trading System."""

import os
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass, field
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


@dataclass
class APIConfig:
    """Configuration for external APIs."""
    
    polygon_api_key: str = field(default_factory=lambda: os.getenv("POLYGON_API_KEY", ""))
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    
    # Rate limiting
    polygon_rate_limit_delay: float = 13.0  # seconds between calls
    polygon_rate_limit: int = 5  # calls per minute for free tier
    polygon_max_retries: int = 3
    
    # API endpoints
    polygon_base_url: str = "https://api.polygon.io"


@dataclass
class DataConfig:
    """Configuration for data handling."""
    
    # Paths
    data_dir: Path = field(default_factory=lambda: Path("data"))
    raw_data_dir: Path = field(default_factory=lambda: Path("data/raw"))
    processed_data_dir: Path = field(default_factory=lambda: Path("data/processed"))
    models_dir: Path = field(default_factory=lambda: Path("data/models"))
    
    # Data settings
    historical_data_years: int = 2
    options_expiration_days_ahead: int = 60
    min_volume_threshold: int = 100
    min_open_interest_threshold: int = 50


@dataclass
class TradingConfig:
    """Configuration for trading logic."""
    
    # Default tickers to analyze
    default_tickers: List[str] = field(default_factory=lambda: [
        "SPY", "QQQ", "IWM", "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META"
    ])
    
    # Trading parameters
    max_position_size: float = 0.10  # 10% of portfolio
    max_daily_trades: int = 5
    min_days_to_expiration: int = 7
    max_days_to_expiration: int = 45
    
    # Risk management
    max_bid_ask_spread: float = 0.50  # dollars
    min_delta_threshold: float = 0.05
    max_delta_threshold: float = 0.95


@dataclass
class MLConfig:
    """Configuration for machine learning models."""
    
    # Model parameters
    xgboost_params: dict = field(default_factory=lambda: {
        "max_depth": 6,
        "learning_rate": 0.1,
        "n_estimators": 100,
        "random_state": 42,
        "eval_metric": "logloss"
    })
    
    # Training settings
    test_size: float = 0.2
    validation_size: float = 0.2
    cv_folds: int = 5
    
    # Feature engineering
    lookback_days: int = 30
    feature_selection_threshold: float = 0.01


@dataclass
class LoggingConfig:
    """Configuration for logging."""
    
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    log_dir: Path = field(default_factory=lambda: Path("logs"))
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    max_log_files: int = 30
    max_log_size_mb: int = 100


@dataclass
class Config:
    """Main configuration class that combines all config sections."""
    
    api: APIConfig = field(default_factory=APIConfig)
    data: DataConfig = field(default_factory=DataConfig)
    trading: TradingConfig = field(default_factory=TradingConfig)
    ml: MLConfig = field(default_factory=MLConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    
    def __post_init__(self):
        """Validate configuration and create directories."""
        self._validate_config()
        self._create_directories()
    
    def _validate_config(self):
        """Validate critical configuration values."""
        # Skip validation if we're in test mode (API keys contain 'test')
        if 'test' in self.api.polygon_api_key.lower():
            return
            
        if not self.api.polygon_api_key:
            raise ValueError("POLYGON_API_KEY environment variable is required")
        
        if not (self.api.openai_api_key or self.api.anthropic_api_key):
            raise ValueError("Either OPENAI_API_KEY or ANTHROPIC_API_KEY is required")
    
    def _create_directories(self):
        """Create necessary directories if they don't exist."""
        directories = [
            self.data.data_dir,
            self.data.raw_data_dir,
            self.data.processed_data_dir,
            self.data.models_dir,
            self.logging.log_dir,
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)


# Global configuration instance
config = Config()