# Component Design Document AI Options Trading System

## 1. Introduction

### 1.1. Project Purpose

This document outlines the design and specifications for a sophisticated, multi-stage algorithmic trading system. The system will leverage a hybrid AI model, combining a Large Language Model (LLM) for qualitative analysis and a traditional Machine Learning (ML) model for quantitative decision-making. The primary goal is to identify and execute high-probability options trades based on a synthesis of news sentiment, technical analysis, and options market data.

### 1.2. Scope

The project scope covers the end-to-end process from data collection to trade simulation. This document details an **End-of-Day (EOD) system** designed to run overnight, making decisions for the following trading day. It is architected to work within the limitations of the Polygon.io free tier, specifically the API rate limits and the 2-year historical data window.

## 2. System Architecture

The system is designed as a modular, batch-processing pipeline. The entire pipeline is intended to be run once per day, after market close.

_A high-level overview of the EOD data flow._

## 3. Component Specifications

### 3.1. Component 1: Data Ingestion Engine

**Purpose:** To gather all raw data required for the system from the Polygon.io API, respecting all rate limits. This component runs once per day, overnight.

- **Sub-component 1.1: EOD Data Collector** * (Revised) *
    
    - **Description:** A script responsible for gathering all necessary EOD data up to the most recent trading day. For backtesting, it will accept a historical `end_date`.
        
    - **Input:**
        
        - `ticker_list`: `List[str]` - A list of stock tickers to gather data for.
            
        - `end_date`: `datetime` - The final date for which to collect data. Defaults to the current date.
            
    - **Process:**
        
        1. For each ticker in `ticker_list`:
            
        2. **Call 1:** Fetch historical OHLCV data for the past 2 years.
            
        3. **Call 2:** Fetch relevant news articles for the past 2 years.
            
        4. **Call 3:** Fetch EOD options chain data for relevant expirations (e.g., next 45-60 days).
            
        5. **Call 4+:** Fetch pre-calculated technical indicators (RSI, MACD, etc.) as needed.
            
        6. _**CRITICAL:**_ After each API call, the script **must wait for at least 13 seconds** (`time.sleep(13)`) to stay under the 5 calls/minute limit.
            
    - **Output:** `Dict` - A dictionary where keys are tickers. Each value is another dictionary containing pandas DataFrames for `ohlcv_data`, `news_data`, and `options_data`, and a dictionary for `technicals`.
        
    - **Note:** The `Real-time Data Poller` sub-component is removed as it's not feasible.
        

### 3.2. Component 2: Analysis & Feature Engineering Engine

**Purpose:** To process the EOD data and transform it into a structured feature set for the decision engine.

- **Sub-component 2.1: Technical Feature Extractor** * (Revised) *
    
    - **Description:** Extracts pre-calculated technical indicators from the data provided by the API.
        
    - **Input:** The `technicals` dictionary for a single ticker from the Data Collector.
        
    - **Process:** Simply parse the JSON/dictionary response from the API to extract the latest values for RSI, MACD, Bollinger Bands, etc.
        
    - **Output:** A dictionary of key-value pairs, e.g., `{'RSI': 45.2, 'MACD_Signal': -0.5}`.
        
- **Sub-component 2.2: News Sentiment Analyzer (LLM-Powered)**
    
    - **Description:** The "Language Brain" of the system. It analyzes news to produce a sophisticated sentiment score.
        
    - **Input:** A pandas DataFrame of `news_data` for a single ticker.
        
    - **Process:**
        
        1. For each news article from the last trading day, construct a detailed "Chain of Thought" prompt for the LLM.
            
        2. The prompt asks for a JSON object containing `sentiment_score` and `predicted_impact_timeline`.
            
        3. Call the LLM API.
            
        4. Aggregate the scores for the day's news.
            
    - **Output:** A dictionary containing `daily_sentiment_score: float` and `dominant_timeline: str`.
        
- **Sub-component 2.3: Options Feature Extractor** * (Revised) *
    
    - **Description:** Derives key insights from the EOD options chain data.
        
    - **Input:** Raw `options_data` DataFrame for a specific ticker.
        
    - **Process:**
        
        1. The Polygon API provides IV for each contract. Calculate the average IV for contracts expiring in ~30-45 days.
            
        2. To calculate **IV Percentile**, we must store historical daily average IV values in our own database over time. For the current day, compare the average IV to the range of stored values over the last year.
            
        3. Filter for liquid contracts based on EOD volume and open interest.
            
    - **Output:** A dictionary containing: `iv_percentile: float` and `liquid_contracts: List[Dict]`.
        

### 3.3. Component 3: Decision & Strategy Engine (ML-Powered)

**Purpose:** The "Quantitative Brain." To synthesize all EOD features and select a specific options strategy for the next trading day.

- **Sub-component 3.1: ML Model Predictor** * (Revised) *
    
    - **Description:** Uses a pre-trained XGBoost model to predict the best strategy. The model is trained offline using a dataset generated by the Backtesting Engine.
        
    - **Input:** A single feature vector for a given ticker, containing all outputs from the Analysis Engine.
        
    - **Process:**
        
        1. Load the pre-trained XGBoost model.
            
        2. Use the model to predict the probability for each potential strategy in its playbook.
            
    - **Output:** A dictionary with the highest-probability strategy, e.g., `{ "strategy": "Bull Put Spread", "confidence": 0.75 }`.
        
- **Sub-component 3.2: Trade Parameterizer** * (New) *
    
    - **Description:** Translates the model's abstract strategy recommendation into a concrete, executable trade based on the latest EOD data.
        
    - **Input:** The strategy decision from the ML model and the `liquid_contracts` list from the Options Feature Extractor.
        
    - **Process:**
        
        1. Based on the strategy (e.g., "Bull Put Spread"), apply a set of rules. For a Bull Put Spread, the rule is: "Find the put contract with a delta closest to 0.30 and an expiration date between 30 and 45 days."
            
        2. Scan the `liquid_contracts` list to find the contract that best matches this rule.
            
        3. Check the bid-ask spread from the EOD data. If the spread is wider than a set threshold (e.g., > $0.50), reject the trade as too illiquid.
            
    - **Output:** A fully specified trade order. Example: `{ "orders": [ {"action": "SELL_TO_OPEN", "contract": "SPY_20250815_520P", "quantity": 1}, {"action": "BUY_TO_OPEN", "contract": "SPY_20250815_515P", "quantity": 1} ], "entry_logic": "Place at market open" }`
        

### 3.4. Component 4: Backtesting & Training Engine

**Purpose:** To validate the strategy and generate the dataset needed to train the ML model.

- **Description:** A master script that simulates the EOD trading strategy over the available 2 years of historical data.
    
- **Input:**
    
    - `start_date`: e.g., "2023-06-26"
        
    - `end_date`: e.g., "2025-06-26"
        
    - `initial_capital`: `float`
        
- **Process:**
    
    1. Call the **EOD Data Collector (1.1)** to get all 2 years of data in a batch process (this may take several hours due to rate limits).
        
    2. Once all data is collected, loop through each trading day in the historical period.
        
    3. For each day, use the data _up to that day_ to run the Analysis and Decision engines.
        
    4. **Dataset Generation:** For each decision, look forward in time to determine the outcome (e.g., did the Bull Put Spread expire worthless?). Store the feature vector and the outcome (1 for success, 0 for failure). This creates the training dataset for the ML model.
        
    5. **Backtest Simulation:** Simulate the execution of the trade in a virtual portfolio and track its performance.
        
- **Output:**
    
    1. `training_data.csv`: The complete dataset for training the ML model.
        
    2. A performance report (Sharpe Ratio, Max Drawdown, etc.) for the backtest period.