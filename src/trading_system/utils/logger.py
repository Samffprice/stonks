"""Logging utilities for the AI Options Trading System."""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional
from datetime import datetime


class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for console output."""
    
    # Color codes
    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
        'RESET': '\033[0m'       # Reset
    }
    
    def format(self, record):
        """Format log record with colors."""
        log_color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        reset_color = self.COLORS['RESET']
        
        # Add color to level name
        record.levelname = f"{log_color}{record.levelname}{reset_color}"
        
        return super().format(record)


def setup_logging(
    log_level: str = "INFO",
    log_dir: Optional[Path] = None,
    log_format: Optional[str] = None,
    max_log_files: int = 30,
    max_log_size_mb: int = 100
) -> None:
    """
    Set up logging configuration for the application.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: Directory for log files
        log_format: Custom log format string
        max_log_files: Maximum number of log files to keep
        max_log_size_mb: Maximum size of each log file in MB
    """
    # Convert string level to logging constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Default format
    if log_format is None:
        log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Create formatters
    file_formatter = logging.Formatter(log_format)
    console_formatter = ColoredFormatter(log_format)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # File handler (if log_dir provided)
    if log_dir:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Create rotating file handler
        log_file = log_dir / f"trading_system_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=max_log_size_mb * 1024 * 1024,  # Convert MB to bytes
            backupCount=max_log_files
        )
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)
    
    # Log initial setup message
    logger = logging.getLogger(__name__)
    logger.info(f"Logging initialized with level: {log_level}")
    if log_dir:
        logger.info(f"Log files will be written to: {log_dir}")


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Get a logger instance for the specified name.
    
    Args:
        name: Logger name. If None, uses the calling module's name.
        
    Returns:
        Logger instance
    """
    if name is None:
        # Get the calling module's name
        import inspect
        frame = inspect.currentframe()
        if frame and frame.f_back:
            name = frame.f_back.f_globals.get('__name__', 'trading_system')
    
    return logging.getLogger(name)


class LoggingContext:
    """Context manager for temporary logging configuration."""
    
    def __init__(self, logger_name: str, level: int):
        """
        Initialize logging context.
        
        Args:
            logger_name: Name of the logger to modify
            level: Temporary logging level
        """
        self.logger = logging.getLogger(logger_name)
        self.original_level = self.logger.level
        self.temp_level = level
    
    def __enter__(self):
        """Enter context and set temporary level."""
        self.logger.setLevel(self.temp_level)
        return self.logger
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context and restore original level."""
        self.logger.setLevel(self.original_level)


# Specialized loggers for different components
def get_data_logger() -> logging.Logger:
    """Get logger for data ingestion components."""
    return get_logger("trading_system.data")


def get_analysis_logger() -> logging.Logger:
    """Get logger for analysis components."""
    return get_logger("trading_system.analysis")


def get_decision_logger() -> logging.Logger:
    """Get logger for decision engine components."""
    return get_logger("trading_system.decision")


def get_backtest_logger() -> logging.Logger:
    """Get logger for backtesting components."""
    return get_logger("trading_system.backtest")


def get_api_logger() -> logging.Logger:
    """Get logger for API calls."""
    return get_logger("trading_system.api")