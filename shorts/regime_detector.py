"""
Regime Detector Module

Detects market regime based on BTC price action:
- BULL: BTC uptrend, strong momentum
- SIDEWAYS: BTC ranging, no clear direction
- MILD_BEAR: BTC downtrend but orderly
- DEEP_BEAR: BTC capitulating, high volatility down

Used to control which trade directions are allowed.
"""

import requests
from datetime import datetime, timedelta
from config.config import config


class RegimeDetector:
    """
    Simple regime detector based on BTC metrics:
    - 24h price change
    - 7d price change (approximated from 24h data over time)
    - Position relative to recent range
    """

    # Regime constants
    BULL = "BULL"
    SIDEWAYS = "SIDEWAYS"
    MILD_BEAR = "MILD_BEAR"
    DEEP_BEAR = "DEEP_BEAR"

    def __init__(self):
        self.btc_symbol = "BTCUSDT"
        self.last_regime = self.SIDEWAYS
        self.last_check_time = None
        self.cache_duration_seconds = 300  # 5 min cache

    def _fetch_btc_ticker(self):
        """Fetch BTC 24h ticker data from MEXC"""
        try:
            url = f"{config.MEXC_BASE_URL}/api/v3/ticker/24hr"
            params = {"symbol": self.btc_symbol}
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"[RegimeDetector] Error fetching BTC ticker: {e}")
            return None

    def _fetch_btc_klines(self, interval="4h", limit=50):
        """Fetch BTC klines for trend analysis"""
        try:
            url = f"{config.MEXC_BASE_URL}/api/v3/klines"
            params = {
                "symbol": self.btc_symbol,
                "interval": interval,
                "limit": limit
            }
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"[RegimeDetector] Error fetching BTC klines: {e}")
            return None

    def _calculate_ema(self, closes, period):
        """Calculate EMA from close prices"""
        if len(closes) < period:
            return closes[-1] if closes else 0

        multiplier = 2 / (period + 1)
        ema = sum(closes[:period]) / period

        for close in closes[period:]:
            ema = (close - ema) * multiplier + ema

        return ema

    def detect_regime(self, force_refresh=False):
        """
        Detect current market regime.

        Returns one of: BULL, SIDEWAYS, MILD_BEAR, DEEP_BEAR
        """
        # Use cached value if recent
        now = datetime.now()
        if not force_refresh and self.last_check_time:
            elapsed = (now - self.last_check_time).total_seconds()
            if elapsed < self.cache_duration_seconds:
                return self.last_regime

        ticker = self._fetch_btc_ticker()
        if not ticker:
            print(f"[RegimeDetector] Using cached regime: {self.last_regime}")
            return self.last_regime

        try:
            price_change_24h = float(ticker.get("priceChangePercent", 0) or 0)
            current_price = float(ticker.get("lastPrice", 0) or 0)
            high_24h = float(ticker.get("highPrice", 0) or 0)
            low_24h = float(ticker.get("lowPrice", 0) or 0)
        except (ValueError, TypeError):
            return self.last_regime

        # Get 4h klines for trend
        klines = self._fetch_btc_klines("4h", 50)
        trend_score = 0

        if klines and len(klines) >= 20:
            closes = [float(k[4]) for k in klines]  # Close price is index 4
            ema_20 = self._calculate_ema(closes, 20)

            # Trend score: positive = above EMA, negative = below
            if current_price > 0 and ema_20 > 0:
                trend_score = (current_price - ema_20) / ema_20 * 100

        # Position in range (0 = at low, 1 = at high)
        range_pos = 0.5
        if high_24h > low_24h:
            range_pos = (current_price - low_24h) / (high_24h - low_24h)

        # Regime detection logic
        regime = self.SIDEWAYS  # Default

        if price_change_24h >= 3.0 and trend_score >= 1.5:
            # Strong bull: >3% up and clearly above 4h EMA
            regime = self.BULL
        elif price_change_24h >= 1.0 and trend_score >= 0.5:
            # Mild bull counts as BULL too
            regime = self.BULL
        elif price_change_24h <= -8.0 or trend_score <= -5.0:
            # Deep bear: major dump or far below EMA
            regime = self.DEEP_BEAR
        elif price_change_24h <= -3.0 or trend_score <= -1.5:
            # Mild bear: moderate weakness
            regime = self.MILD_BEAR
        else:
            # Everything else is sideways
            regime = self.SIDEWAYS

        self.last_regime = regime
        self.last_check_time = now

        print(f"[RegimeDetector] Regime: {regime} | BTC 24h: {price_change_24h:+.2f}% | Trend: {trend_score:+.2f}% | Range: {range_pos:.2f}")

        return regime

    def should_trade_shorts(self, regime=None):
        """
        Check if shorts are allowed in current/given regime.
        Respects ENABLE_SHORTS_IN_* config flags.
        """
        if regime is None:
            regime = self.detect_regime()

        if regime == self.BULL:
            return config.ENABLE_SHORTS_IN_BULL
        elif regime == self.SIDEWAYS:
            return config.ENABLE_SHORTS_IN_SIDEWAYS
        elif regime == self.MILD_BEAR:
            return config.ENABLE_SHORTS_IN_MILD_BEAR
        elif regime == self.DEEP_BEAR:
            return config.ENABLE_SHORTS_IN_DEEP_BEAR

        return False

    def should_trade_longs(self, regime=None):
        """
        Check if longs are allowed in current/given regime.
        For SAFE_BULL, longs are always allowed but with adjusted risk in bear.
        """
        if regime is None:
            regime = self.detect_regime()

        # For this version: longs always allowed, just with different risk
        return True

    def get_risk_per_trade(self, regime=None, direction="LONG"):
        """
        Get risk per trade based on regime and direction.
        Returns decimal (e.g., 0.0025 for 0.25%)
        """
        if regime is None:
            regime = self.detect_regime()

        if direction == "SHORT":
            if regime == self.SIDEWAYS:
                return config.RISK_PER_TRADE_SIDEWAYS_SHORT
            elif regime == self.MILD_BEAR:
                return config.RISK_PER_TRADE_MILD_BEAR_SHORT
            elif regime == self.DEEP_BEAR:
                return config.RISK_PER_TRADE_DEEP_BEAR_SHORT
            else:
                return 0  # No shorts in BULL
        else:  # LONG
            if regime == self.BULL:
                return config.RISK_PER_TRADE_BULL
            elif regime == self.SIDEWAYS:
                return config.RISK_PER_TRADE_SIDEWAYS
            elif regime == self.MILD_BEAR:
                if config.ENABLE_BEAR_LONGS:
                    return config.RISK_PER_TRADE_BEAR_LONG
                return 0
            elif regime == self.DEEP_BEAR:
                if config.ENABLE_BEAR_LONGS:
                    return config.RISK_PER_TRADE_BEAR_LONG
                return 0

        return config.RISK_PER_TRADE_BULL  # Default fallback


# Singleton instance
regime_detector = RegimeDetector()
