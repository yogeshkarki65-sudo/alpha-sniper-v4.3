import requests
import time
from datetime import datetime, timedelta

from config.config import config
from database.models import db
from risk.risk_manager import risk_manager
from monitoring.telegram_alerter import send_alert


def get_current_price(symbol):
    try:
        url = f"{config.MEXC_BASE_URL}/api/v3/ticker/price"
        params = {'symbol': symbol}
        resp = requests.get(url, params=params, timeout=5)
        data = resp.json()
        return float(data['price'])
    except Exception as e:
        print(f"Error fetching price for {symbol}: {e}")
        return None


def check_symbol_cooldown(symbol, direction):
    """Check if symbol+direction combination is in cooldown"""
    cooldown_time = datetime.now() - timedelta(hours=config.SYMBOL_COOLDOWN_HOURS)
    conn = db.get_conn()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT COUNT(*) FROM trades
        WHERE symbol=? AND direction=? AND closed_at > ?
    ''', (symbol, direction, cooldown_time.isoformat()))
    count = cursor.fetchone()[0]
    conn.close()
    return count == 0


def calculate_position_size_for_signal(entry_price, stop_loss_pct, risk_per_trade):
    """
    Calculate position size based on risk per trade.
    size_usd = (equity * risk_pct) / stop_pct
    """
    equity = risk_manager.get_current_equity()
    if equity <= 0 or stop_loss_pct <= 0:
        return 0

    risk_usd = equity * risk_per_trade
    size_usd = risk_usd / (stop_loss_pct / 100)

    # Cap at 20% of equity per position
    max_position_usd = equity * 0.20
    size_usd = min(size_usd, max_position_usd)

    # Convert to position size (number of units)
    position_size = size_usd / entry_price if entry_price > 0 else 0

    return max(0, position_size)


def open_position_from_signal(signal):
    """
    Open a position from a signal.
    Signal tuple indices (with direction fields):
    0:id, 1:symbol, 2:score, 3:rvol, 4:velocity, 5:trend,
    6:orderbook_imbalance, 7:last_price, 8:direction, 9:regime, 10:created_at, 11:consumed
    """
    signal_id = signal[0]
    symbol = signal[1]
    score = signal[2]
    direction = signal[8] if len(signal) > 8 and signal[8] else 'LONG'
    regime = signal[9] if len(signal) > 9 else None

    # Check cooldown for this symbol+direction
    if not check_symbol_cooldown(symbol, direction):
        print(f"  {symbol} ({direction}) in cooldown period")
        db.mark_signal_consumed(signal_id)
        return False

    # Check if we already have a position in this symbol+direction
    existing = db.get_position_by_symbol_direction(symbol, direction)
    if existing:
        print(f"  {symbol} ({direction}) already has open position")
        db.mark_signal_consumed(signal_id)
        return False

    # Check general trading conditions
    can_trade, reason = risk_manager.can_trade()
    if not can_trade:
        print(f"  Cannot trade: {reason}")
        return False

    # Check portfolio heat
    current_heat = db.get_portfolio_heat()
    if current_heat >= config.MAX_PORTFOLIO_HEAT:
        print(f"  Portfolio heat too high: {current_heat:.4f} >= {config.MAX_PORTFOLIO_HEAT}")
        return False

    # Check correlation
    open_positions = db.get_open_positions()
    if not risk_manager.check_correlation(symbol, open_positions):
        print(f"  {symbol} too correlated with existing positions")
        db.mark_signal_consumed(signal_id)
        return False

    # Get current price
    current_price = get_current_price(symbol)
    if not current_price:
        return False

    # Get regime-specific risk
    from shorts.regime_detector import regime_detector
    risk_per_trade = regime_detector.get_risk_per_trade(regime, direction)
    if risk_per_trade <= 0:
        print(f"  {direction} not allowed in {regime} regime")
        db.mark_signal_consumed(signal_id)
        return False

    # Calculate entry with slippage (direction-aware)
    if direction == 'SHORT':
        # Shorting: we sell at bid, expect slightly worse fill
        entry_price = current_price * (1 - config.SLIPPAGE_PCT / 100)
    else:
        # Buying: we buy at ask, expect slightly worse fill
        entry_price = current_price * (1 + config.SLIPPAGE_PCT / 100)

    # Calculate position size
    position_size = calculate_position_size_for_signal(entry_price, config.STOP_LOSS_PCT, risk_per_trade)
    if position_size <= 0:
        print(f"  Position size <= 0 for {symbol}")
        db.mark_signal_consumed(signal_id)
        return False

    # Moon multiplier (only for longs in this version)
    if direction == 'LONG' and score >= config.MOON_SCORE:
        position_size *= config.MOON_MULT
        print(f"  MOON signal detected! Multiplying position by {config.MOON_MULT}x")

    # Calculate stop loss and take profit (direction-aware)
    if direction == 'SHORT':
        # Short: stop ABOVE entry, TP BELOW entry
        stop_loss_price = entry_price * (1 + config.STOP_LOSS_PCT / 100)
        take_profit_price = entry_price * (1 - config.TAKE_PROFIT_PCT / 100)
    else:
        # Long: stop BELOW entry, TP ABOVE entry
        stop_loss_price = entry_price * (1 - config.STOP_LOSS_PCT / 100)
        take_profit_price = entry_price * (1 + config.TAKE_PROFIT_PCT / 100)

    # Create position
    position_id = db.create_position(
        signal_id,
        symbol,
        entry_price,
        position_size,
        stop_loss_price,
        take_profit_price,
        direction=direction,
        regime=regime
    )

    db.mark_signal_consumed(signal_id)

    position_value = entry_price * position_size
    dir_emoji = "" if direction == 'SHORT' else ""

    print(f"{dir_emoji} OPENED {direction}: {symbol} @ ${entry_price:.6f} | Size: {position_size:.4f} | Value: ${position_value:.2f}")

    send_alert(
        f"{dir_emoji} {direction} Position Opened\n"
        f"Symbol: {symbol}\n"
        f"Score: {score:.1f}\n"
        f"Regime: {regime}\n"
        f"Entry: ${entry_price:.6f}\n"
        f"Value: ${position_value:.2f}\n"
        f"SL: ${stop_loss_price:.6f} | TP: ${take_profit_price:.6f}"
    )

    return True


def monitor_positions():
    """
    Monitor all open positions and handle exits.
    Direction-aware: profit calculation and stop/TP triggers work correctly for both LONG and SHORT.
    """
    positions = db.get_open_positions()
    if not positions:
        return

    print(f"Monitoring {len(positions)} positions...")

    for pos in positions:
        # Position tuple indices (with direction fields):
        # 0:id, 1:signal_id, 2:symbol, 3:entry_price, 4:position_size,
        # 5:stop_loss_price, 6:take_profit_price, 7:highest_price, 8:lowest_price,
        # 9:trailing_stop_active, 10:trailing_stop_price, 11:direction, 12:regime,
        # 13:opened_at, 14:opened_at_timestamp
        position_id = pos[0]
        symbol = pos[2]
        entry_price = pos[3]
        position_size = pos[4]
        stop_loss_price = pos[5]
        take_profit_price = pos[6]
        highest_price = pos[7] if len(pos) > 7 else entry_price
        lowest_price = pos[8] if len(pos) > 8 else entry_price
        trailing_stop_active = bool(pos[9]) if len(pos) > 9 else False
        trailing_stop_price = pos[10] if len(pos) > 10 else None
        direction = pos[11] if len(pos) > 11 else 'LONG'
        opened_at_ts = pos[14] if len(pos) > 14 else pos[10]

        current_price = get_current_price(symbol)
        if not current_price:
            continue

        # Update highest/lowest price tracking
        if current_price > highest_price:
            highest_price = current_price
        if current_price < lowest_price:
            lowest_price = current_price

        # Direction-aware profit calculation
        if direction == 'SHORT':
            # Short: profit when price goes DOWN
            current_profit_pct = ((entry_price - current_price) / entry_price) * 100
        else:
            # Long: profit when price goes UP
            current_profit_pct = ((current_price - entry_price) / entry_price) * 100

        # Time exit check
        now_ts = datetime.now().timestamp()
        hold_time_hours = (now_ts - opened_at_ts) / 3600
        if hold_time_hours >= config.MAX_HOLD_TIME_HOURS:
            exit_price = current_price * (1 - config.SLIPPAGE_PCT / 100) if direction == 'LONG' else current_price * (1 + config.SLIPPAGE_PCT / 100)
            db.close_position(position_id, exit_price, 'time_exit')
            print(f"  CLOSED (time): {symbol} {direction} @ ${exit_price:.6f} | PnL: {current_profit_pct:.2f}%")
            send_alert(f" Time Exit: {symbol} {direction} | PnL: {current_profit_pct:.2f}%")
            continue

        # Trailing stop logic (direction-aware)
        if config.USE_TRAILING_STOP:
            if current_profit_pct >= config.TRAILING_STOP_ACTIVATION_PCT and not trailing_stop_active:
                trailing_stop_active = True
                if direction == 'SHORT':
                    # Short trailing: stop moves DOWN as price falls
                    trailing_stop_price = lowest_price * (1 + config.TRAILING_STOP_DISTANCE_PCT / 100)
                else:
                    # Long trailing: stop moves UP as price rises
                    trailing_stop_price = highest_price * (1 - config.TRAILING_STOP_DISTANCE_PCT / 100)
                db.update_position_trailing(position_id, highest_price, lowest_price, trailing_stop_active, trailing_stop_price)
                print(f"  Trailing stop activated for {symbol} {direction} @ ${trailing_stop_price:.6f}")

            if trailing_stop_active:
                if direction == 'SHORT':
                    trailing_stop_price = lowest_price * (1 + config.TRAILING_STOP_DISTANCE_PCT / 100)
                    hit_trailing = current_price >= trailing_stop_price
                else:
                    trailing_stop_price = highest_price * (1 - config.TRAILING_STOP_DISTANCE_PCT / 100)
                    hit_trailing = current_price <= trailing_stop_price

                db.update_position_trailing(position_id, highest_price, lowest_price, trailing_stop_active, trailing_stop_price)

                if hit_trailing:
                    exit_price = current_price * (1 - config.SLIPPAGE_PCT / 100) if direction == 'LONG' else current_price * (1 + config.SLIPPAGE_PCT / 100)
                    db.close_position(position_id, exit_price, 'trailing_stop')
                    print(f"  CLOSED (trailing): {symbol} {direction} @ ${exit_price:.6f} | PnL: {current_profit_pct:.2f}%")
                    send_alert(f" Trailing Stop: {symbol} {direction} | PnL: {current_profit_pct:.2f}%")
                    continue

        # Stop loss check (direction-aware)
        if direction == 'SHORT':
            hit_stop = current_price >= stop_loss_price
        else:
            hit_stop = current_price <= stop_loss_price

        if hit_stop:
            exit_price = current_price * (1 - config.SLIPPAGE_PCT / 100) if direction == 'LONG' else current_price * (1 + config.SLIPPAGE_PCT / 100)
            db.close_position(position_id, exit_price, 'stop_loss')
            print(f"  CLOSED (SL): {symbol} {direction} @ ${exit_price:.6f} | PnL: {current_profit_pct:.2f}%")
            send_alert(f" Stop Loss: {symbol} {direction} | PnL: {current_profit_pct:.2f}%")
            continue

        # Take profit check (direction-aware)
        if direction == 'SHORT':
            hit_tp = current_price <= take_profit_price
        else:
            hit_tp = current_price >= take_profit_price

        if hit_tp:
            exit_price = current_price * (1 - config.SLIPPAGE_PCT / 100) if direction == 'LONG' else current_price * (1 + config.SLIPPAGE_PCT / 100)
            db.close_position(position_id, exit_price, 'take_profit')
            print(f"  CLOSED (TP): {symbol} {direction} @ ${exit_price:.6f} | PnL: {current_profit_pct:.2f}%")
            send_alert(f" Take Profit: {symbol} {direction} | PnL: {current_profit_pct:.2f}%")
            continue

        dir_indicator = "" if direction == 'SHORT' else ""
        print(f"  {dir_indicator} {symbol}: ${current_price:.6f} | PnL: {current_profit_pct:.2f}%")


def run_trader():
    """Main trader loop - processes signals and monitors positions"""
    print(" Running trader...")

    # Monitor existing positions
    monitor_positions()

    # Check if we can open new positions
    can_trade, reason = risk_manager.can_trade()
    if not can_trade:
        print(f"  Cannot open new positions: {reason}")
        return

    open_positions = db.get_open_positions()
    slots_available = config.MAX_CONCURRENT_POS - len(open_positions)

    if slots_available <= 0:
        print(" All position slots filled")
        return

    # Get all unconsumed signals (both LONG and SHORT)
    signals = db.get_unconsumed_signals(limit=slots_available * 2)  # Get more to allow for filtering
    if not signals:
        print(" No signals to process")
        return

    print(f"Found {len(signals)} signals to process")

    positions_opened = 0
    for signal in signals:
        if positions_opened >= slots_available:
            break
        if open_position_from_signal(signal):
            positions_opened += 1
            time.sleep(1)
