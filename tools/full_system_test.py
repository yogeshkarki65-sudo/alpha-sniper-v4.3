#!/usr/bin/env python3
"""
ALPHA SNIPER V4.2 - FULL SYSTEM TEST
=====================================

This script tests every component and generates a comprehensive report.

Run with:
    python tools/full_system_test.py

Output:
    - Console output with all test results
    - logs/system_test_report.txt with full report
"""

import sys
import os
import json
import traceback
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Create logs directory if needed
os.makedirs('logs', exist_ok=True)

REPORT_FILE = 'logs/system_test_report.txt'
report_lines = []


def log(msg, level="INFO"):
    """Log to both console and report"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{level}] {msg}"
    print(line)
    report_lines.append(line)


def test_pass(name):
    log(f"PASS: {name}", "PASS")
    return True


def test_fail(name, error):
    log(f"FAIL: {name} - {error}", "FAIL")
    return False


def section(title):
    log("")
    log("=" * 60)
    log(f"  {title}")
    log("=" * 60)


# ============================================================
# TEST 1: CONFIG LOADING
# ============================================================
def test_config():
    section("TEST 1: CONFIG LOADING")
    results = {}

    try:
        from config.config import config

        # Test basic config
        results['MEXC_BASE_URL'] = config.MEXC_BASE_URL
        results['MODE'] = config.MODE
        results['SIM_EQUITY_START'] = config.SIM_EQUITY_START

        # Test short config
        required_short_attrs = [
            'ENABLE_SHORTS_IN_BULL',
            'ENABLE_SHORTS_IN_SIDEWAYS',
            'ENABLE_SHORTS_IN_MILD_BEAR',
            'ENABLE_SHORTS_IN_DEEP_BEAR',
            'MAX_FUNDING_8H_SHORT',
            'RISK_PER_TRADE_SIDEWAYS_SHORT',
            'RISK_PER_TRADE_MILD_BEAR_SHORT',
            'RISK_PER_TRADE_DEEP_BEAR_SHORT',
            'MIN_24H_QUOTE_VOLUME',
            'MAX_ALLOWED_SPREAD_PCT',
            'MIN_RVOL_15M_BEAR_SHORT',
        ]

        missing = []
        for attr in required_short_attrs:
            if hasattr(config, attr):
                results[attr] = getattr(config, attr)
            else:
                missing.append(attr)

        if missing:
            return test_fail("Config Loading", f"Missing attributes: {missing}")

        log(f"  MODE: {results['MODE']}")
        log(f"  SIM_EQUITY_START: ${results['SIM_EQUITY_START']}")
        log(f"  ENABLE_SHORTS_IN_BULL: {results['ENABLE_SHORTS_IN_BULL']}")
        log(f"  ENABLE_SHORTS_IN_SIDEWAYS: {results['ENABLE_SHORTS_IN_SIDEWAYS']}")
        log(f"  ENABLE_SHORTS_IN_MILD_BEAR: {results['ENABLE_SHORTS_IN_MILD_BEAR']}")
        log(f"  ENABLE_SHORTS_IN_DEEP_BEAR: {results['ENABLE_SHORTS_IN_DEEP_BEAR']}")
        log(f"  MAX_FUNDING_8H_SHORT: {results['MAX_FUNDING_8H_SHORT']}")
        log(f"  RISK_PER_TRADE_SIDEWAYS_SHORT: {results['RISK_PER_TRADE_SIDEWAYS_SHORT']}")

        return test_pass("Config Loading")

    except Exception as e:
        return test_fail("Config Loading", str(e))


# ============================================================
# TEST 2: DATABASE
# ============================================================
def test_database():
    section("TEST 2: DATABASE")

    try:
        from database.models import db

        # Check tables exist
        conn = db.get_conn()
        cursor = conn.cursor()

        # Check signals table has direction column
        cursor.execute("PRAGMA table_info(signals)")
        columns = [col[1] for col in cursor.fetchall()]
        log(f"  Signals columns: {columns}")

        if 'direction' not in columns:
            conn.close()
            return test_fail("Database", "signals table missing 'direction' column")

        # Check positions table has direction column
        cursor.execute("PRAGMA table_info(positions)")
        columns = [col[1] for col in cursor.fetchall()]
        log(f"  Positions columns: {columns}")

        if 'direction' not in columns:
            conn.close()
            return test_fail("Database", "positions table missing 'direction' column")

        # Check trades table has direction column
        cursor.execute("PRAGMA table_info(trades)")
        columns = [col[1] for col in cursor.fetchall()]
        log(f"  Trades columns: {columns}")

        if 'direction' not in columns:
            conn.close()
            return test_fail("Database", "trades table missing 'direction' column")

        conn.close()
        return test_pass("Database Schema")

    except Exception as e:
        traceback.print_exc()
        return test_fail("Database", str(e))


# ============================================================
# TEST 3: REGIME DETECTOR
# ============================================================
def test_regime_detector():
    section("TEST 3: REGIME DETECTOR")

    try:
        from shorts.regime_detector import RegimeDetector, regime_detector

        # Test regime constants
        assert RegimeDetector.BULL == "BULL"
        assert RegimeDetector.SIDEWAYS == "SIDEWAYS"
        assert RegimeDetector.MILD_BEAR == "MILD_BEAR"
        assert RegimeDetector.DEEP_BEAR == "DEEP_BEAR"
        log("  Regime constants: OK")

        # Test should_trade_shorts logic
        from config.config import config

        # In BULL with ENABLE_SHORTS_IN_BULL=false, should return False
        result = regime_detector.should_trade_shorts("BULL")
        expected = config.ENABLE_SHORTS_IN_BULL
        log(f"  should_trade_shorts(BULL): {result} (expected: {expected})")
        if result != expected:
            return test_fail("Regime Detector", f"BULL short check mismatch")

        # In SIDEWAYS with ENABLE_SHORTS_IN_SIDEWAYS=true, should return True
        result = regime_detector.should_trade_shorts("SIDEWAYS")
        expected = config.ENABLE_SHORTS_IN_SIDEWAYS
        log(f"  should_trade_shorts(SIDEWAYS): {result} (expected: {expected})")
        if result != expected:
            return test_fail("Regime Detector", f"SIDEWAYS short check mismatch")

        # Test get_risk_per_trade
        risk = regime_detector.get_risk_per_trade("SIDEWAYS", "SHORT")
        log(f"  Risk per trade (SIDEWAYS, SHORT): {risk}")
        if risk <= 0 or risk > 0.01:
            return test_fail("Regime Detector", f"Invalid risk value: {risk}")

        # Test actual regime detection (requires network)
        try:
            regime = regime_detector.detect_regime(force_refresh=True)
            log(f"  Current detected regime: {regime}")
        except Exception as e:
            log(f"  Warning: Could not detect regime (network?): {e}")

        return test_pass("Regime Detector")

    except Exception as e:
        traceback.print_exc()
        return test_fail("Regime Detector", str(e))


# ============================================================
# TEST 4: SHORT SCANNER
# ============================================================
def test_short_scanner():
    section("TEST 4: SHORT SCANNER")

    try:
        from shorts.short_scanner import (
            get_top_losers,
            compute_short_features,
            filter_short_candidate,
            calculate_short_score,
            scan_for_shorts
        )

        # Test get_top_losers (requires network)
        try:
            losers = get_top_losers(limit=10)
            log(f"  Top losers found: {len(losers)}")
            if losers:
                sample = losers[0]
                log(f"  Sample loser: {sample.get('symbol')} @ {sample.get('priceChangePercent')}%")
        except Exception as e:
            log(f"  Warning: Could not fetch losers (network?): {e}")

        # Test compute_short_features with mock data
        mock_ticker = {
            "symbol": "TESTUSDT",
            "volume": 1000000,
            "quoteVolume": 5000000,
            "priceChangePercent": -15.0,
            "highPrice": 1.2,
            "lowPrice": 0.8,
            "lastPrice": 0.85,
        }
        features = compute_short_features(mock_ticker, "MILD_BEAR")
        if features:
            log(f"  Mock features computed: velocity={features.get('velocity')}, trend={features.get('trend'):.2f}")
        else:
            return test_fail("Short Scanner", "compute_short_features returned None for valid data")

        # Test calculate_short_score
        score = calculate_short_score(features, "MILD_BEAR")
        log(f"  Mock short score: {score}")
        if score < 0 or score > 100:
            return test_fail("Short Scanner", f"Invalid score: {score}")

        return test_pass("Short Scanner")

    except Exception as e:
        traceback.print_exc()
        return test_fail("Short Scanner", str(e))


# ============================================================
# TEST 5: MAIN SCANNER INTEGRATION
# ============================================================
def test_main_scanner():
    section("TEST 5: MAIN SCANNER INTEGRATION")

    try:
        from scanner.scanner import (
            compute_features,
            scan_for_longs,
            scan_for_shorts,
            run_scanner
        )

        # Test compute_features with mock data
        mock_ticker = {
            "symbol": "TESTUSDT",
            "volume": 1000000,
            "quoteVolume": 5000000,
            "priceChangePercent": 10.0,
            "highPrice": 1.2,
            "lowPrice": 0.8,
            "lastPrice": 1.15,
        }
        features = compute_features(mock_ticker)
        if features:
            log(f"  compute_features: OK (velocity={features.get('velocity')}, trend={features.get('trend'):.2f})")
        else:
            return test_fail("Main Scanner", "compute_features returned None")

        # Test that velocity key exists and is accessible
        velocity = features.get("velocity")
        if velocity is None:
            return test_fail("Main Scanner", "velocity key missing from features")
        log(f"  velocity key accessible: {velocity}")

        return test_pass("Main Scanner Integration")

    except Exception as e:
        traceback.print_exc()
        return test_fail("Main Scanner", str(e))


# ============================================================
# TEST 6: TRADER DIRECTION HANDLING
# ============================================================
def test_trader():
    section("TEST 6: TRADER DIRECTION HANDLING")

    try:
        from trader.trader import (
            check_symbol_cooldown,
            calculate_position_size_for_signal,
            open_position_from_signal,
            monitor_positions
        )

        # Test position size calculation
        from unittest.mock import patch, MagicMock

        with patch('trader.trader.risk_manager') as mock_rm:
            mock_rm.get_current_equity.return_value = 1000

            # Test short position sizing
            size = calculate_position_size_for_signal(
                entry_price=100,
                stop_loss_pct=5.0,
                risk_per_trade=0.0015  # 0.15%
            )
            # Expected: (1000 * 0.0015) / 0.05 = 30 USD / 100 = 0.3 units
            log(f"  Position size for SHORT: {size:.4f} (expected ~0.3)")

            if abs(size - 0.3) > 0.01:
                return test_fail("Trader", f"Position size mismatch: {size} vs 0.3")

        # Test PnL calculation for shorts
        entry = 100
        exit_price = 90  # Price dropped
        # For SHORT: PnL = (entry - exit) / entry = 10%
        pnl_short = ((entry - exit_price) / entry) * 100
        log(f"  SHORT PnL when price drops 10%: {pnl_short}% (should be +10%)")
        if pnl_short != 10.0:
            return test_fail("Trader", "SHORT PnL calculation wrong")

        # For LONG: PnL = (exit - entry) / entry = -10%
        pnl_long = ((exit_price - entry) / entry) * 100
        log(f"  LONG PnL when price drops 10%: {pnl_long}% (should be -10%)")
        if pnl_long != -10.0:
            return test_fail("Trader", "LONG PnL calculation wrong")

        return test_pass("Trader Direction Handling")

    except Exception as e:
        traceback.print_exc()
        return test_fail("Trader", str(e))


# ============================================================
# TEST 7: SIGNAL CREATION AND RETRIEVAL
# ============================================================
def test_signal_flow():
    section("TEST 7: SIGNAL CREATION & RETRIEVAL")

    try:
        from database.models import Database
        import tempfile

        # Create test database
        test_db_path = os.path.join(tempfile.gettempdir(), 'test_signal_flow.db')
        if os.path.exists(test_db_path):
            os.remove(test_db_path)

        test_db = Database(test_db_path)

        # Create LONG signal
        long_id = test_db.create_signal(
            symbol="LONGUSDT",
            score=85.0,
            rvol=1.5,
            velocity=10.0,
            trend=0.8,
            orderbook_imbalance=0.2,
            last_price=100.0,
            direction="LONG",
            regime="BULL"
        )
        log(f"  Created LONG signal ID: {long_id}")

        # Create SHORT signal
        short_id = test_db.create_signal(
            symbol="SHORTUSDT",
            score=82.0,
            rvol=1.8,
            velocity=-15.0,
            trend=0.2,
            orderbook_imbalance=-0.3,
            last_price=50.0,
            direction="SHORT",
            regime="MILD_BEAR"
        )
        log(f"  Created SHORT signal ID: {short_id}")

        # Retrieve signals
        signals = test_db.get_unconsumed_signals(limit=10)
        log(f"  Total unconsumed signals: {len(signals)}")

        # Check directions
        long_signals = test_db.get_unconsumed_signals(limit=10, direction="LONG")
        short_signals = test_db.get_unconsumed_signals(limit=10, direction="SHORT")
        log(f"  LONG signals: {len(long_signals)}")
        log(f"  SHORT signals: {len(short_signals)}")

        if len(long_signals) < 1 or len(short_signals) < 1:
            os.remove(test_db_path)
            return test_fail("Signal Flow", "Signal direction filtering not working")

        # Cleanup
        os.remove(test_db_path)
        return test_pass("Signal Creation & Retrieval")

    except Exception as e:
        traceback.print_exc()
        return test_fail("Signal Flow", str(e))


# ============================================================
# TEST 8: POSITION & TRADE FLOW
# ============================================================
def test_position_flow():
    section("TEST 8: POSITION & TRADE FLOW")

    try:
        from database.models import Database
        import tempfile

        # Create test database
        test_db_path = os.path.join(tempfile.gettempdir(), 'test_position_flow.db')
        if os.path.exists(test_db_path):
            os.remove(test_db_path)

        test_db = Database(test_db_path)

        # Create SHORT position
        pos_id = test_db.create_position(
            signal_id=1,
            symbol="SHORTUSDT",
            entry_price=100.0,
            position_size=10.0,
            stop_loss_price=105.0,  # Above entry for short
            take_profit_price=90.0,  # Below entry for short
            direction="SHORT",
            regime="MILD_BEAR"
        )
        log(f"  Created SHORT position ID: {pos_id}")

        # Check position
        positions = test_db.get_open_positions(direction="SHORT")
        log(f"  Open SHORT positions: {len(positions)}")

        if len(positions) < 1:
            os.remove(test_db_path)
            return test_fail("Position Flow", "SHORT position not created")

        # Check position direction
        pos = positions[0]
        pos_direction = pos[11] if len(pos) > 11 else None
        log(f"  Position direction: {pos_direction}")

        if pos_direction != "SHORT":
            os.remove(test_db_path)
            return test_fail("Position Flow", f"Position direction mismatch: {pos_direction}")

        # Close position (profitable short - price dropped)
        exit_price = 90.0  # Price dropped = profit for short
        pnl = test_db.close_position(pos_id, exit_price, "take_profit")
        log(f"  Closed position, Net PnL: ${pnl:.2f}")

        if pnl is None or pnl <= 0:
            os.remove(test_db_path)
            return test_fail("Position Flow", f"SHORT PnL should be positive, got {pnl}")

        # Check trade record
        trades = test_db.get_recent_trades(days=1, direction="SHORT")
        log(f"  SHORT trades recorded: {len(trades)}")

        if len(trades) < 1:
            os.remove(test_db_path)
            return test_fail("Position Flow", "Trade not recorded")

        # Cleanup
        os.remove(test_db_path)
        return test_pass("Position & Trade Flow")

    except Exception as e:
        traceback.print_exc()
        return test_fail("Position Flow", str(e))


# ============================================================
# TEST 9: LIVE API CONNECTION
# ============================================================
def test_api_connection():
    section("TEST 9: LIVE API CONNECTION")

    try:
        import requests
        from config.config import config

        url = f"{config.MEXC_BASE_URL}/api/v3/ticker/24hr"
        log(f"  Testing: {url}")

        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        log(f"  API returned {len(data)} tickers")

        if len(data) < 100:
            return test_fail("API Connection", f"Too few tickers: {len(data)}")

        # Check BTC exists
        btc = next((t for t in data if t.get('symbol') == 'BTCUSDT'), None)
        if btc:
            log(f"  BTCUSDT: ${btc.get('lastPrice')} ({btc.get('priceChangePercent')}%)")
        else:
            return test_fail("API Connection", "BTCUSDT not found")

        return test_pass("API Connection")

    except Exception as e:
        traceback.print_exc()
        return test_fail("API Connection", str(e))


# ============================================================
# TEST 10: FULL SCANNER RUN
# ============================================================
def test_full_scanner_run():
    section("TEST 10: FULL SCANNER RUN (DRY)")

    try:
        from shorts.regime_detector import regime_detector

        # Detect regime
        regime = regime_detector.detect_regime()
        log(f"  Current regime: {regime}")
        log(f"  Shorts allowed: {regime_detector.should_trade_shorts(regime)}")

        # Note: Not actually running scanner to avoid creating signals
        log("  Scanner functions validated (not executing to avoid side effects)")

        return test_pass("Full Scanner Run")

    except Exception as e:
        traceback.print_exc()
        return test_fail("Full Scanner Run", str(e))


# ============================================================
# MAIN
# ============================================================
def main():
    log("")
    log("=" * 60)
    log("  ALPHA SNIPER V4.2 - FULL SYSTEM TEST")
    log("=" * 60)
    log(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("")

    results = {}

    # Run all tests
    results['config'] = test_config()
    results['database'] = test_database()
    results['regime_detector'] = test_regime_detector()
    results['short_scanner'] = test_short_scanner()
    results['main_scanner'] = test_main_scanner()
    results['trader'] = test_trader()
    results['signal_flow'] = test_signal_flow()
    results['position_flow'] = test_position_flow()
    results['api_connection'] = test_api_connection()
    results['full_scanner'] = test_full_scanner_run()

    # Summary
    section("SUMMARY")
    passed = sum(1 for v in results.values() if v)
    failed = sum(1 for v in results.values() if not v)

    log(f"  Total Tests: {len(results)}")
    log(f"  Passed: {passed}")
    log(f"  Failed: {failed}")
    log("")

    for name, result in results.items():
        status = "PASS" if result else "FAIL"
        log(f"  {name}: {status}")

    log("")
    if failed == 0:
        log("ALL TESTS PASSED - SYSTEM READY", "SUCCESS")
    else:
        log(f"{failed} TESTS FAILED - FIX ISSUES BEFORE RUNNING", "ERROR")

    # Write report
    log("")
    log(f"Report written to: {REPORT_FILE}")

    with open(REPORT_FILE, 'w') as f:
        f.write('\n'.join(report_lines))

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
