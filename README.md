# AI Options Trading System

A sophisticated algorithmic trading system that combines Large Language Models (LLM) for qualitative analysis and traditional Machine Learning (ML) for quantitative decision-making in options trading.

## 🚀 Features

- **Hybrid AI Architecture**: Combines LLM sentiment analysis with ML-based strategy prediction
- **End-of-Day Processing**: Designed for overnight execution with next-day decisions
- **Modular Design**: Clean, testable, and maintainable codebase
- **Comprehensive Backtesting**: Full historical simulation with performance metrics
- **Risk Management**: Built-in position sizing and risk controls
- **Rate Limit Compliance**: Respects Polygon.io free tier limitations

## 🏗️ Architecture

The system consists of four main components:

1. **Data Ingestion Engine**: Collects OHLCV, news, and options data from Polygon.io
2. **Analysis & Feature Engineering**: Processes data using technical indicators, LLM sentiment analysis, and options metrics
3. **Decision & Strategy Engine**: Uses XGBoost ML model to predict optimal trading strategies
4. **Backtesting & Training Engine**: Validates strategies and generates training data

## 📋 Prerequisites

- Python 3.8+
- API keys for:
  - [Polygon.io](https://polygon.io/) (required)
  - [OpenAI](https://openai.com/) or [Anthropic](https://www.anthropic.com/) (required)

## 🛠️ Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd ai-options-trading
   ```

2. **Create virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   pip install -e .
   ```

4. **Set up environment variables**:
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

## ⚙️ Configuration

The system uses environment variables for configuration. Key variables:

```bash
# Required
POLYGON_API_KEY=your_polygon_api_key
OPENAI_API_KEY=your_openai_api_key

# Optional
LOG_LEVEL=INFO
ENVIRONMENT=development
```

## 🧪 Testing

Run the test suite:

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src/trading_system

# Run specific test categories
pytest -m unit
pytest -m integration
pytest -m "not slow"
```

## 🚀 Usage

### Basic Usage

```python
from trading_system import Config, get_logger
from trading_system.data_ingestion import EODDataCollector
from trading_system.analysis import AnalysisEngine
from trading_system.decision_engine import DecisionEngine

# Initialize components
config = Config()
logger = get_logger()

# Collect data
collector = EODDataCollector(config)
data = collector.collect_data(['SPY', 'QQQ'])

# Analyze data
analyzer = AnalysisEngine(config)
features = analyzer.extract_features(data)

# Make decisions
decision_engine = DecisionEngine(config)
trades = decision_engine.generate_trades(features)
```

### Running Backtests

```bash
# Run backtest
backtest --start-date 2023-01-01 --end-date 2024-12-31 --initial-capital 100000
```

## 📊 Project Structure

```
src/trading_system/
├── config/                 # Configuration management
├── data_ingestion/         # Data collection from APIs
├── analysis/               # Feature engineering and analysis
├── decision_engine/        # ML models and strategy generation
├── backtesting/           # Backtesting framework
└── utils/                 # Shared utilities

tests/
├── unit/                  # Unit tests
├── integration/           # Integration tests
└── fixtures/              # Test data and mocks

data/
├── raw/                   # Raw API data
├── processed/             # Processed features
└── models/                # Trained ML models

docs/                      # Documentation
logs/                      # Application logs
```

## 🔄 Development Workflow

1. **Phase 1**: Project Setup & Foundation ✅
2. **Phase 2**: Data Ingestion Engine (In Progress)
3. **Phase 3**: Analysis & Feature Engineering
4. **Phase 4**: Decision & Strategy Engine
5. **Phase 5**: Backtesting & Training Engine
6. **Phase 6**: System Integration & Production

## 📈 Performance Metrics

The system tracks multiple performance metrics:
- Sharpe Ratio
- Maximum Drawdown
- Win Rate
- Average Return per Trade
- Total Return

## ⚠️ Risk Disclosure

This software is for educational and research purposes only. Trading options involves substantial risk and is not suitable for all investors. Past performance does not guarantee future results.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 📞 Support

For questions and support, please open an issue on GitHub.