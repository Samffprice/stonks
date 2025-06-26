"""AI Options Trading System.

A sophisticated algorithmic trading system that combines LLM for qualitative analysis
and ML for quantitative decision-making in options trading.
"""

__version__ = "0.1.0"
__author__ = "AI Trading System Team"

# Import main components for easy access
from .config.settings import Config
from .utils.logger import get_logger

__all__ = ["Config", "get_logger"]