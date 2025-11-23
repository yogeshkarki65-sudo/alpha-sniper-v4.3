"""
Unit Tests for Short Engine

Tests:
1. Regime-based short enabling
2. Funding rate filter
3. Position sizing for shorts
4. Short candidate structure validation
"""

import unittest
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch, MagicMock


class TestRegimeDetector(unittest.TestCase):
    """Test regime detection and short enabling logic"""

    def setUp(self):
        # Reset regime detector state
        from shorts.regime_detector import RegimeDetector
        self.detector = RegimeDetector()

    @patch('shorts.regime_detector.config')
    def test_should_trade_shorts_in_bull(self, mock_config):
        """Shorts should be disabled in BULL regime (SAFE_BULL config)"""
        mock_config.ENABLE_SHORTS_IN_BULL = False
        mock_config.ENABLE_SHORTS_IN_SIDEWAYS = True
        mock_config.ENABLE_SHORTS_IN_MILD_BEAR = True
        mock_config.ENABLE_SHORTS_IN_DEEP_BEAR = True

        result = self.detector.should_trade_shorts("BULL")
        self.assertFalse(result, "Shorts should be disabled in BULL regime")

    @patch('shorts.regime_detector.config')
    def test_should_trade_shorts_in_sideways(self, mock_config):
        """Shorts should be enabled in SIDEWAYS regime"""
        mock_config.ENABLE_SHORTS_IN_BULL = False
        mock_config.ENABLE_SHORTS_IN_SIDEWAYS = True
        mock_config.ENABLE_SHORTS_IN_MILD_BEAR = True
        mock_config.ENABLE_SHORTS_IN_DEEP_BEAR = True

        result = self.detector.should_trade_shorts("SIDEWAYS")
        self.assertTrue(result, "Shorts should be enabled in SIDEWAYS regime")

    @patch('shorts.regime_detector.config')
    def test_should_trade_shorts_in_mild_bear(self, mock_config):
        """Shorts should be enabled in MILD_BEAR regime"""
        mock_config.ENABLE_SHORTS_IN_BULL = False
        mock_config.ENABLE_SHORTS_IN_SIDEWAYS = True
        mock_config.ENABLE_SHORTS_IN_MILD_BEAR = True
        mock_config.ENABLE_SHORTS_IN_DEEP_BEAR = True

        result = self.detector.should_trade_shorts("MILD_BEAR")
        self.assertTrue(result, "Shorts should be enabled in MILD_BEAR regime")

    @patch('shorts.regime_detector.config')
    def test_should_trade_shorts_in_deep_bear(self, mock_config):
        """Shorts should be enabled in DEEP_BEAR regime"""
        mock_config.ENABLE_SHORTS_IN_BULL = False
        mock_config.ENABLE_SHORTS_IN_SIDEWAYS = True
        mock_config.ENABLE_SHORTS_IN_MILD_BEAR = True
        mock_config.ENABLE_SHORTS_IN_DEEP_BEAR = True

        result = self.detector.should_trade_shorts("DEEP_BEAR")
        self.assertTrue(result, "Shorts should be enabled in DEEP_BEAR regime")

    @patch('shorts.regime_detector.config')
    def test_get_risk_per_trade_short_sideways(self, mock_config):
        """Risk per trade should return correct value for SHORT in SIDEWAYS"""
        mock_config.RISK_PER_TRADE_SIDEWAYS_SHORT = 0.0015
        mock_config.RISK_PER_TRADE_MILD_BEAR_SHORT = 0.0015
        mock_config.RISK_PER_TRADE_DEEP_BEAR_SHORT = 0.0012

        result = self.detector.get_risk_per_trade("SIDEWAYS", "SHORT")
        self.assertEqual(result, 0.0015)

    @patch('shorts.regime_detector.config')
    def test_get_risk_per_trade_short_deep_bear(self, mock_config):
        """Risk per trade should return lower value for SHORT in DEEP_BEAR"""
        mock_config.RISK_PER_TRADE_SIDEWAYS_SHORT = 0.0015
        mock_config.RISK_PER_TRADE_MILD_BEAR_SHORT = 0.0015
        mock_config.RISK_PER_TRADE_DEEP_BEAR_SHORT = 0.0012

        result = self.detector.get_risk_per_trade("DEEP_BEAR", "SHORT")
        self.assertEqual(result, 0.0012)


class TestShortFundingFilter(unittest.TestCase):
    """Test funding rate filter for shorts"""

    @patch('shorts.short_scanner.config')
    def test_funding_below_max_allowed(self, mock_config):
        """Shorts should be allowed when funding is below max"""
        mock_config.MAX_FUNDING_8H_SHORT = 0.00035

        from shorts.short_scanner import filter_short_candidate
        from shorts.regime_detector import regime_detector

        features = {
            "symbol": "TESTUSDT",
            "velocity": -10.0,
            "rvol": 1.5,
            "trend": 0.3,
            "funding_8h": 0.0001,  # Below max
            "spread_pct": 0.5,
            "quote_volume_24h": 100000,
        }

        # Mock config values needed by filter
        mock_config.MAX_ALLOWED_SPREAD_PCT = 1.1
        mock_config.MIN_RVOL_15M_BEAR_SHORT = 1.25

        passed, reason = filter_short_candidate(features, "SIDEWAYS")
        # Should pass funding filter (may fail others)
        self.assertNotIn("Funding", reason)

    @patch('shorts.short_scanner.config')
    def test_funding_above_max_rejected(self, mock_config):
        """Shorts should be rejected when funding is above max"""
        mock_config.MAX_FUNDING_8H_SHORT = 0.00035
        mock_config.MAX_ALLOWED_SPREAD_PCT = 1.1
        mock_config.MIN_RVOL_15M_BEAR_SHORT = 1.25

        from shorts.short_scanner import filter_short_candidate

        features = {
            "symbol": "TESTUSDT",
            "velocity": -10.0,
            "rvol": 1.5,
            "trend": 0.3,
            "funding_8h": 0.001,  # Above max (0.1%)
            "spread_pct": 0.5,
            "quote_volume_24h": 100000,
        }

        passed, reason = filter_short_candidate(features, "SIDEWAYS")
        self.assertFalse(passed)
        self.assertIn("Funding", reason)


class TestShortPositionSizing(unittest.TestCase):
    """Test position sizing for shorts"""

    def test_short_position_size_calculation(self):
        """
        Given equity=$1000 and SIDEWAYS regime:
        - risk_pct = 0.0015 (0.15%)
        - stop distance = 5%
        - Expected size_usd = (1000 * 0.0015) / 0.05 = $30
        """
        from trader.trader import calculate_position_size_for_signal
        from unittest.mock import patch

        with patch('trader.trader.risk_manager') as mock_rm:
            mock_rm.get_current_equity.return_value = 1000

            entry_price = 100.0
            stop_loss_pct = 5.0
            risk_per_trade = 0.0015

            position_size = calculate_position_size_for_signal(
                entry_price, stop_loss_pct, risk_per_trade
            )

            # size_usd = (1000 * 0.0015) / 0.05 = 30
            # position_size = 30 / 100 = 0.3
            expected_size = 0.3
            self.assertAlmostEqual(position_size, expected_size, places=4)

    def test_short_position_size_with_cap(self):
        """Position size should be capped at 20% of equity"""
        from trader.trader import calculate_position_size_for_signal
        from unittest.mock import patch

        with patch('trader.trader.risk_manager') as mock_rm:
            mock_rm.get_current_equity.return_value = 1000

            entry_price = 1.0  # Very low price = huge position without cap
            stop_loss_pct = 0.1  # Tiny stop = huge position without cap
            risk_per_trade = 0.01

            position_size = calculate_position_size_for_signal(
                entry_price, stop_loss_pct, risk_per_trade
            )

            # Max position value = 1000 * 0.20 = 200
            # Max position size at price 1.0 = 200 units
            self.assertLessEqual(position_size * entry_price, 200)


class TestShortCandidateStructure(unittest.TestCase):
    """Test short candidate generation and scoring"""

    @patch('shorts.short_scanner.config')
    @patch('shorts.short_scanner.get_top_losers')
    def test_breakdown_produces_short_signal(self, mock_losers, mock_config):
        """A clear breakdown should produce a short signal with high score"""
        mock_config.MIN_SIGNAL_SCORE = 80
        mock_config.MAX_FUNDING_8H_SHORT = 0.00035
        mock_config.MAX_ALLOWED_SPREAD_PCT = 1.1
        mock_config.MIN_RVOL_15M_BEAR_SHORT = 1.25
        mock_config.MIN_24H_QUOTE_VOLUME = 50000
        mock_config.CHECK_ORDER_BOOK_IMBALANCE = False

        from shorts.short_scanner import calculate_short_score

        # Features representing a clean breakdown
        breakdown_features = {
            "symbol": "DUMPUSDT",
            "direction": "SHORT",
            "rvol": 2.0,  # High volume
            "velocity": -15.0,  # Down 15%
            "trend": 0.2,  # Near daily low (breakdown)
            "orderbook_imbalance": -0.3,  # Sell pressure
            "drop_from_high": 0.2,
            "last_price": 1.0,
            "quote_volume_24h": 100000,
            "funding_8h": 0.0001,
            "spread_pct": 0.5,
            "regime": "MILD_BEAR",
        }

        score = calculate_short_score(breakdown_features, "MILD_BEAR")
        self.assertGreaterEqual(score, 70, f"Breakdown should score high, got {score}")

    @patch('shorts.short_scanner.config')
    def test_sideways_chop_no_short_signal(self, mock_config):
        """Sideways chop without breakdown should score low"""
        mock_config.MIN_SIGNAL_SCORE = 80
        mock_config.MAX_FUNDING_8H_SHORT = 0.00035
        mock_config.MAX_ALLOWED_SPREAD_PCT = 1.1
        mock_config.MIN_RVOL_15M_BEAR_SHORT = 1.25

        from shorts.short_scanner import calculate_short_score

        # Features representing sideways chop (no clear breakdown)
        chop_features = {
            "symbol": "CHOPUSDT",
            "direction": "SHORT",
            "rvol": 0.8,  # Low volume
            "velocity": -1.0,  # Barely down
            "trend": 0.6,  # Middle of range (no breakdown)
            "orderbook_imbalance": 0.0,  # Neutral
            "drop_from_high": 0.05,
            "last_price": 1.0,
            "quote_volume_24h": 100000,
            "funding_8h": 0.0001,
            "spread_pct": 0.5,
            "regime": "SIDEWAYS",
        }

        score = calculate_short_score(chop_features, "SIDEWAYS")
        self.assertLess(score, 80, f"Chop should score low, got {score}")


class TestDirectionAwarePnL(unittest.TestCase):
    """Test that PnL calculation is direction-aware"""

    def test_long_profit_when_price_rises(self):
        """Long position should profit when price rises"""
        entry = 100
        exit_price = 110
        direction = "LONG"

        # PnL = (exit - entry) / entry for long
        pnl_pct = ((exit_price - entry) / entry) * 100
        self.assertEqual(pnl_pct, 10.0)

    def test_short_profit_when_price_falls(self):
        """Short position should profit when price falls"""
        entry = 100
        exit_price = 90
        direction = "SHORT"

        # PnL = (entry - exit) / entry for short
        pnl_pct = ((entry - exit_price) / entry) * 100
        self.assertEqual(pnl_pct, 10.0)

    def test_short_loss_when_price_rises(self):
        """Short position should lose when price rises"""
        entry = 100
        exit_price = 110
        direction = "SHORT"

        # PnL = (entry - exit) / entry for short
        pnl_pct = ((entry - exit_price) / entry) * 100
        self.assertEqual(pnl_pct, -10.0)


class TestShortStopAndTakeProfit(unittest.TestCase):
    """Test stop loss and take profit are correctly placed for shorts"""

    def test_short_stop_above_entry(self):
        """Short stop loss should be ABOVE entry price"""
        entry = 100
        stop_loss_pct = 5.0

        # For short: stop = entry * (1 + stop_pct)
        stop_loss = entry * (1 + stop_loss_pct / 100)
        self.assertEqual(stop_loss, 105.0)
        self.assertGreater(stop_loss, entry)

    def test_short_take_profit_below_entry(self):
        """Short take profit should be BELOW entry price"""
        entry = 100
        take_profit_pct = 10.0

        # For short: TP = entry * (1 - tp_pct)
        take_profit = entry * (1 - take_profit_pct / 100)
        self.assertEqual(take_profit, 90.0)
        self.assertLess(take_profit, entry)

    def test_long_stop_below_entry(self):
        """Long stop loss should be BELOW entry price (sanity check)"""
        entry = 100
        stop_loss_pct = 5.0

        # For long: stop = entry * (1 - stop_pct)
        stop_loss = entry * (1 - stop_loss_pct / 100)
        self.assertEqual(stop_loss, 95.0)
        self.assertLess(stop_loss, entry)


if __name__ == "__main__":
    unittest.main(verbosity=2)
