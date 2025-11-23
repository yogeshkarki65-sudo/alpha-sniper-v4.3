import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # MEXC
    MEXC_BASE_URL = os.getenv('MEXC_BASE_URL', 'https://api.mexc.com')
    VENUE = os.getenv('VENUE', 'MEXC')

    # Trading Mode
    MODE = os.getenv('MODE', 'SIM')
    SIM_EQUITY_START = float(os.getenv('SIM_EQUITY_START', 500))
    MARKET_TYPE = os.getenv('MARKET_TYPE', 'FUTURES')

    # Futures & Shorts Configuration
    ENABLE_FUTURES = os.getenv('ENABLE_FUTURES', 'true').lower() == 'true'
    ENABLE_SHORTS_IN_BULL = os.getenv('ENABLE_SHORTS_IN_BULL', 'false').lower() == 'true'
    ENABLE_SHORTS_IN_SIDEWAYS = os.getenv('ENABLE_SHORTS_IN_SIDEWAYS', 'true').lower() == 'true'
    ENABLE_SHORTS_IN_MILD_BEAR = os.getenv('ENABLE_SHORTS_IN_MILD_BEAR', 'true').lower() == 'true'
    ENABLE_SHORTS_IN_DEEP_BEAR = os.getenv('ENABLE_SHORTS_IN_DEEP_BEAR', 'true').lower() == 'true'
    MAX_FUNDING_8H_SHORT = float(os.getenv('MAX_FUNDING_8H_SHORT', 0.00035))  # 0.035%

    # Risk per trade - LONGS (by regime)
    RISK_PER_TRADE_BULL = float(os.getenv('RISK_PER_TRADE_BULL', 0.0025))
    RISK_PER_TRADE_SIDEWAYS = float(os.getenv('RISK_PER_TRADE_SIDEWAYS', 0.0025))
    RISK_PER_TRADE_MILD_BEAR = float(os.getenv('RISK_PER_TRADE_MILD_BEAR', 0.0018))
    RISK_PER_TRADE_DEEP_BEAR = float(os.getenv('RISK_PER_TRADE_DEEP_BEAR', 0.0015))
    RISK_PER_TRADE_BEAR_LONG = float(os.getenv('RISK_PER_TRADE_BEAR_LONG', 0.0010))
    ENABLE_BEAR_LONGS = os.getenv('ENABLE_BEAR_LONGS', 'true').lower() == 'true'

    # Risk per trade - SHORTS (by regime)
    RISK_PER_TRADE_SIDEWAYS_SHORT = float(os.getenv('RISK_PER_TRADE_SIDEWAYS_SHORT', 0.0015))
    RISK_PER_TRADE_MILD_BEAR_SHORT = float(os.getenv('RISK_PER_TRADE_MILD_BEAR_SHORT', 0.0015))
    RISK_PER_TRADE_DEEP_BEAR_SHORT = float(os.getenv('RISK_PER_TRADE_DEEP_BEAR_SHORT', 0.0012))

    # Portfolio Limits
    MAX_PORTFOLIO_HEAT = float(os.getenv('MAX_PORTFOLIO_HEAT', 0.015))  # 1.5%
    MAX_CONCURRENT_POSITIONS = int(os.getenv('MAX_CONCURRENT_POSITIONS', 5))

    # Signal thresholds
    MIN_24H_QUOTE_VOLUME = float(os.getenv('MIN_24H_QUOTE_VOLUME', 50000))
    MAX_ALLOWED_SPREAD_PCT = float(os.getenv('MAX_ALLOWED_SPREAD_PCT', 1.1))
    MIN_RVOL_15M_BULL = float(os.getenv('MIN_RVOL_15M_BULL', 1.15))
    MIN_RVOL_15M_BEAR_SHORT = float(os.getenv('MIN_RVOL_15M_BEAR_SHORT', 1.25))

    # Risk Management
    MAX_DAILY_DRAWDOWN_PCT = float(os.getenv('MAX_DAILY_DRAWDOWN_PCT', 2.0))
    MAX_POSITION_RISK_PCT = float(os.getenv('MAX_POSITION_RISK_PCT', 0.5))
    MIN_LIQUIDITY_VOLUME_24H = float(os.getenv('MIN_LIQUIDITY_VOLUME_24H', 100000))
    MAX_CORRELATED_POSITIONS = int(os.getenv('MAX_CORRELATED_POSITIONS', 2))
    TRADING_PAUSED = os.getenv('TRADING_PAUSED', 'false').lower() == 'true'

    # Position
    MAX_CONCURRENT_POS = int(os.getenv('MAX_CONCURRENT_POS', 5))
    STOP_LOSS_PCT = float(os.getenv('STOP_LOSS_PCT', 5.0))
    TAKE_PROFIT_PCT = float(os.getenv('TAKE_PROFIT_PCT', 10.0))

    # Exits
    USE_TRAILING_STOP = os.getenv('USE_TRAILING_STOP', 'true').lower() == 'true'
    TRAILING_STOP_ACTIVATION_PCT = float(os.getenv('TRAILING_STOP_ACTIVATION_PCT', 2.0))
    TRAILING_STOP_DISTANCE_PCT = float(os.getenv('TRAILING_STOP_DISTANCE_PCT', 1.0))
    MAX_HOLD_TIME_HOURS = float(os.getenv('MAX_HOLD_TIME_HOURS', 24))

    # Fees
    TAKER_FEE_PCT = float(os.getenv('TAKER_FEE_PCT', 0.1))
    SLIPPAGE_PCT = float(os.getenv('SLIPPAGE_PCT', 0.05))

    # Signals
    MIN_SIGNAL_SCORE = float(os.getenv('MIN_SIGNAL_SCORE', 80))
    SYMBOL_COOLDOWN_HOURS = float(os.getenv('SYMBOL_COOLDOWN_HOURS', 6))
    CHECK_ORDER_BOOK_IMBALANCE = os.getenv('CHECK_ORDER_BOOK_IMBALANCE', 'true').lower() == 'true'
    MOON_SCORE = float(os.getenv('MOON_SCORE', 90))
    MOON_MULT = float(os.getenv('MOON_MULT', 1.5))

    # Learning
    LEARNING_ENABLED = os.getenv('LEARNING_ENABLED', 'true').lower() == 'true'
    MIN_TRADES_FOR_LEARNING = int(os.getenv('MIN_TRADES_FOR_LEARNING', 30))
    MAX_WEIGHT_CHANGE_PCT = float(os.getenv('MAX_WEIGHT_CHANGE_PCT', 15))
    LEARNING_LOOKBACK_DAYS = int(os.getenv('LEARNING_LOOKBACK_DAYS', 30))

    # Telegram
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
    ALERT_ON_DRAWDOWN_PCT = float(os.getenv('ALERT_ON_DRAWDOWN_PCT', 3.0))
    ALERT_ON_WEIGHT_CHANGE_PCT = float(os.getenv('ALERT_ON_WEIGHT_CHANGE_PCT', 10.0))
    DAILY_REPORT_HOUR = int(os.getenv('DAILY_REPORT_HOUR', 9))

    # Intervals
    SCANNER_INTERVAL = int(os.getenv('SCANNER_INTERVAL', 300))
    TRADER_INTERVAL = int(os.getenv('TRADER_INTERVAL', 60))
    LEARNING_INTERVAL = int(os.getenv('LEARNING_INTERVAL', 3600))

config = Config()
