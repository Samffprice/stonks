"""Unit tests for configuration module."""

import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# This will work once we install dependencies
try:
    from trading_system.config.settings import (
        Config, APIConfig, DataConfig, TradingConfig, MLConfig, LoggingConfig
    )
except ImportError:
    # Skip tests if dependencies not installed
    pytest.skip("Dependencies not installed", allow_module_level=True)


class TestAPIConfig:
    """Test APIConfig class."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = APIConfig()
        assert config.polygon_rate_limit_delay == 13.0
        assert config.polygon_max_retries == 3
        assert config.polygon_base_url == "https://api.polygon.io"
    
    @patch.dict(os.environ, {
        'POLYGON_API_KEY': 'test_polygon_key',
        'OPENAI_API_KEY': 'test_openai_key'
    })
    def test_environment_variables(self):
        """Test that environment variables are loaded."""
        config = APIConfig()
        assert config.polygon_api_key == 'test_polygon_key'
        assert config.openai_api_key == 'test_openai_key'


class TestDataConfig:
    """Test DataConfig class."""
    
    def test_default_paths(self):
        """Test default data paths."""
        config = DataConfig()
        assert config.data_dir == Path("data")
        assert config.raw_data_dir == Path("data/raw")
        assert config.processed_data_dir == Path("data/processed")
        assert config.models_dir == Path("data/models")
    
    def test_data_settings(self):
        """Test data configuration settings."""
        config = DataConfig()
        assert config.historical_data_years == 2
        assert config.options_expiration_days_ahead == 60
        assert config.min_volume_threshold == 100
        assert config.min_open_interest_threshold == 50


class TestTradingConfig:
    """Test TradingConfig class."""
    
    def test_default_tickers(self):
        """Test default ticker list."""
        config = TradingConfig()
        expected_tickers = [
            "SPY", "QQQ", "IWM", "AAPL", "MSFT", 
            "GOOGL", "AMZN", "TSLA", "NVDA", "META"
        ]
        assert config.default_tickers == expected_tickers
    
    def test_trading_parameters(self):
        """Test trading parameter defaults."""
        config = TradingConfig()
        assert config.max_position_size == 0.10
        assert config.max_daily_trades == 5
        assert config.min_days_to_expiration == 7
        assert config.max_days_to_expiration == 45


class TestMLConfig:
    """Test MLConfig class."""
    
    def test_xgboost_params(self):
        """Test XGBoost parameter defaults."""
        config = MLConfig()
        expected_params = {
            "max_depth": 6,
            "learning_rate": 0.1,
            "n_estimators": 100,
            "random_state": 42,
            "eval_metric": "logloss"
        }
        assert config.xgboost_params == expected_params
    
    def test_training_settings(self):
        """Test training configuration."""
        config = MLConfig()
        assert config.test_size == 0.2
        assert config.validation_size == 0.2
        assert config.cv_folds == 5


class TestLoggingConfig:
    """Test LoggingConfig class."""
    
    def test_default_values(self):
        """Test logging defaults."""
        config = LoggingConfig()
        assert config.log_level == "INFO"
        assert config.log_dir == Path("logs")
        assert "%(asctime)s" in config.log_format
        assert config.max_log_files == 30
        assert config.max_log_size_mb == 100


class TestMainConfig:
    """Test main Config class."""
    
    @patch.dict(os.environ, {
        'POLYGON_API_KEY': 'test_key',
        'OPENAI_API_KEY': 'test_openai'
    })
    def test_config_initialization(self):
        """Test config initialization with valid keys."""
        config = Config()
        assert isinstance(config.api, APIConfig)
        assert isinstance(config.data, DataConfig)
        assert isinstance(config.trading, TradingConfig)
        assert isinstance(config.ml, MLConfig)
        assert isinstance(config.logging, LoggingConfig)
    
    @patch.dict(os.environ, {}, clear=True)
    def test_missing_polygon_key_validation(self):
        """Test validation fails without Polygon API key."""
        with pytest.raises(ValueError, match="POLYGON_API_KEY environment variable is required"):
            Config()
    
    @patch.dict(os.environ, {'POLYGON_API_KEY': 'test_key'}, clear=True)
    def test_missing_llm_key_validation(self):
        """Test validation fails without LLM API key."""
        with pytest.raises(ValueError, match="Either OPENAI_API_KEY or ANTHROPIC_API_KEY is required"):
            Config()
    
    @patch('pathlib.Path.mkdir')
    @patch.dict(os.environ, {
        'POLYGON_API_KEY': 'test_key',
        'OPENAI_API_KEY': 'test_openai'
    })
    def test_directory_creation(self, mock_mkdir):
        """Test that directories are created during initialization."""
        Config()
        # Should be called for each directory
        assert mock_mkdir.call_count >= 4  # data, raw, processed, models, logs