"""Unit tests for logger module."""

import logging
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# This will work once we install dependencies
try:
    from trading_system.utils.logger import (
        get_logger, setup_logging, LoggingContext, ColoredFormatter,
        get_data_logger, get_analysis_logger, get_decision_logger,
        get_backtest_logger, get_api_logger
    )
except ImportError:
    # Skip tests if dependencies not installed
    pytest.skip("Dependencies not installed", allow_module_level=True)


class TestColoredFormatter:
    """Test ColoredFormatter class."""
    
    def test_format_with_colors(self):
        """Test that formatter adds colors to log records."""
        formatter = ColoredFormatter("%(levelname)s - %(message)s")
        
        # Create a log record
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Test message", args=(), exc_info=None
        )
        
        formatted = formatter.format(record)
        assert "\033[32m" in formatted  # Green color for INFO
        assert "\033[0m" in formatted   # Reset color


class TestLoggingSetup:
    """Test setup_logging function."""
    
    @patch('logging.getLogger')
    def test_setup_logging_basic(self, mock_get_logger):
        """Test basic logging setup."""
        mock_root_logger = MagicMock()
        mock_get_logger.return_value = mock_root_logger
        
        setup_logging(log_level="DEBUG")
        
        # Verify root logger was configured
        mock_root_logger.setLevel.assert_called()
        mock_root_logger.addHandler.assert_called()
    
    @patch('logging.getLogger')
    @patch('pathlib.Path.mkdir')
    def test_setup_logging_with_file(self, mock_mkdir, mock_get_logger):
        """Test logging setup with file output."""
        mock_root_logger = MagicMock()
        mock_get_logger.return_value = mock_root_logger
        
        log_dir = Path("test_logs")
        setup_logging(log_level="INFO", log_dir=log_dir)
        
        # Verify directory creation
        mock_mkdir.assert_called()
        
        # Verify handlers were added
        assert mock_root_logger.addHandler.call_count >= 2  # Console + File


class TestGetLogger:
    """Test get_logger function."""
    
    def test_get_logger_with_name(self):
        """Test getting logger with specific name."""
        logger = get_logger("test_logger")
        assert logger.name == "test_logger"
    
    def test_get_logger_without_name(self):
        """Test getting logger without name."""
        logger = get_logger()
        assert logger.name == "trading_system"  # Default fallback


class TestLoggingContext:
    """Test LoggingContext class."""
    
    def test_logging_context(self):
        """Test logging context manager."""
        logger = logging.getLogger("test_context")
        original_level = logger.level
        
        with LoggingContext("test_context", logging.DEBUG) as context_logger:
            assert context_logger.level == logging.DEBUG
        
        # Level should be restored
        assert logger.level == original_level


class TestSpecializedLoggers:
    """Test specialized logger functions."""
    
    def test_get_data_logger(self):
        """Test data logger."""
        logger = get_data_logger()
        assert "trading_system.data" in logger.name
    
    def test_get_analysis_logger(self):
        """Test analysis logger."""
        logger = get_analysis_logger()
        assert "trading_system.analysis" in logger.name
    
    def test_get_decision_logger(self):
        """Test decision logger."""
        logger = get_decision_logger()
        assert "trading_system.decision" in logger.name
    
    def test_get_backtest_logger(self):
        """Test backtest logger."""
        logger = get_backtest_logger()
        assert "trading_system.backtest" in logger.name
    
    def test_get_api_logger(self):
        """Test API logger."""
        logger = get_api_logger()
        assert "trading_system.api" in logger.name