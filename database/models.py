import sqlite3
import json
from datetime import datetime

class Database:
    def __init__(self, db_path='data/trades.db'):
        self.db_path = db_path
        self.init_db()

    def get_conn(self):
        return sqlite3.connect(self.db_path)

    def init_db(self):
        conn = self.get_conn()
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                score REAL NOT NULL,
                rvol REAL,
                velocity REAL,
                trend REAL,
                orderbook_imbalance REAL,
                last_price REAL,
                direction TEXT DEFAULT 'LONG',
                regime TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                consumed INTEGER DEFAULT 0
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id INTEGER,
                symbol TEXT NOT NULL,
                entry_price REAL NOT NULL,
                position_size REAL NOT NULL,
                stop_loss_price REAL NOT NULL,
                take_profit_price REAL NOT NULL,
                highest_price REAL,
                lowest_price REAL,
                trailing_stop_active INTEGER DEFAULT 0,
                trailing_stop_price REAL,
                direction TEXT DEFAULT 'LONG',
                regime TEXT,
                opened_at TEXT DEFAULT CURRENT_TIMESTAMP,
                opened_at_timestamp REAL,
                FOREIGN KEY(signal_id) REFERENCES signals(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id INTEGER,
                symbol TEXT NOT NULL,
                entry_price REAL NOT NULL,
                exit_price REAL NOT NULL,
                position_size REAL NOT NULL,
                direction TEXT DEFAULT 'LONG',
                regime TEXT,
                gross_pnl_usd REAL,
                entry_fee_usd REAL,
                exit_fee_usd REAL,
                slippage_cost_usd REAL,
                net_pnl_usd REAL,
                pnl_pct REAL,
                exit_reason TEXT,
                opened_at TEXT,
                closed_at TEXT DEFAULT CURRENT_TIMESTAMP,
                hold_time_hours REAL,
                FOREIGN KEY(signal_id) REFERENCES signals(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS learning_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                weights_before TEXT,
                weights_after TEXT,
                train_ic REAL,
                test_ic REAL,
                num_trades_used INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL UNIQUE,
                starting_equity REAL,
                ending_equity REAL,
                high_water_mark REAL,
                max_drawdown_pct REAL,
                num_trades INTEGER,
                win_rate REAL,
                total_fees REAL
            )
        ''')

        # Migration: add direction column if it doesn't exist (for existing DBs)
        self._migrate_add_column(cursor, 'signals', 'direction', "TEXT DEFAULT 'LONG'")
        self._migrate_add_column(cursor, 'signals', 'regime', "TEXT")
        self._migrate_add_column(cursor, 'positions', 'direction', "TEXT DEFAULT 'LONG'")
        self._migrate_add_column(cursor, 'positions', 'regime', "TEXT")
        self._migrate_add_column(cursor, 'positions', 'lowest_price', "REAL")
        self._migrate_add_column(cursor, 'trades', 'direction', "TEXT DEFAULT 'LONG'")
        self._migrate_add_column(cursor, 'trades', 'regime', "TEXT")

        conn.commit()
        conn.close()

    def _migrate_add_column(self, cursor, table, column, column_type):
        """Add column if it doesn't exist (safe migration)"""
        try:
            cursor.execute(f"SELECT {column} FROM {table} LIMIT 1")
        except sqlite3.OperationalError:
            print(f"[DB Migration] Adding column {column} to {table}")
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")

    def create_signal(self, symbol, score, rvol, velocity, trend, orderbook_imbalance,
                      last_price, direction='LONG', regime=None):
        conn = self.get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO signals (symbol, score, rvol, velocity, trend, orderbook_imbalance,
                                 last_price, direction, regime)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (symbol, score, rvol, velocity, trend, orderbook_imbalance, last_price,
              direction, regime))
        signal_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return signal_id

    def get_unconsumed_signals(self, limit=10, direction=None):
        conn = self.get_conn()
        cursor = conn.cursor()
        if direction:
            cursor.execute(
                'SELECT * FROM signals WHERE consumed=0 AND direction=? ORDER BY score DESC LIMIT ?',
                (direction, limit)
            )
        else:
            cursor.execute(
                'SELECT * FROM signals WHERE consumed=0 ORDER BY score DESC LIMIT ?',
                (limit,)
            )
        rows = cursor.fetchall()
        conn.close()
        return rows

    def mark_signal_consumed(self, signal_id):
        conn = self.get_conn()
        cursor = conn.cursor()
        cursor.execute('UPDATE signals SET consumed=1 WHERE id=?', (signal_id,))
        conn.commit()
        conn.close()

    def create_position(self, signal_id, symbol, entry_price, position_size,
                        stop_loss_price, take_profit_price, direction='LONG', regime=None):
        conn = self.get_conn()
        cursor = conn.cursor()
        now_ts = datetime.now().timestamp()
        cursor.execute('''
            INSERT INTO positions
            (signal_id, symbol, entry_price, position_size, stop_loss_price, take_profit_price,
             highest_price, lowest_price, direction, regime, opened_at_timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (signal_id, symbol, entry_price, position_size, stop_loss_price, take_profit_price,
              entry_price, entry_price, direction, regime, now_ts))
        position_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return position_id

    def get_open_positions(self, direction=None):
        conn = self.get_conn()
        cursor = conn.cursor()
        if direction:
            cursor.execute('SELECT * FROM positions WHERE direction=?', (direction,))
        else:
            cursor.execute('SELECT * FROM positions')
        rows = cursor.fetchall()
        conn.close()
        return rows

    def update_position_trailing(self, position_id, highest_price, lowest_price,
                                  trailing_active, trailing_price):
        conn = self.get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE positions
            SET highest_price=?, lowest_price=?, trailing_stop_active=?, trailing_stop_price=?
            WHERE id=?
        ''', (highest_price, lowest_price, 1 if trailing_active else 0, trailing_price, position_id))
        conn.commit()
        conn.close()

    def close_position(self, position_id, exit_price, exit_reason):
        """
        Close a position and record the trade.
        PnL calculation is direction-aware:
        - LONG: profit when exit > entry
        - SHORT: profit when exit < entry
        """
        conn = self.get_conn()
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM positions WHERE id=?', (position_id,))
        pos = cursor.fetchone()
        if not pos:
            conn.close()
            return None

        from config.config import config

        # Position tuple indices (after adding direction fields):
        # 0:id, 1:signal_id, 2:symbol, 3:entry_price, 4:position_size,
        # 5:stop_loss_price, 6:take_profit_price, 7:highest_price, 8:lowest_price,
        # 9:trailing_stop_active, 10:trailing_stop_price, 11:direction, 12:regime,
        # 13:opened_at, 14:opened_at_timestamp
        signal_id = pos[1]
        symbol = pos[2]
        entry_price = pos[3]
        position_size = pos[4]
        direction = pos[11] if len(pos) > 11 else 'LONG'
        regime = pos[12] if len(pos) > 12 else None
        opened_at_ts = pos[14] if len(pos) > 14 else pos[10]  # Fallback for old schema

        entry_value = entry_price * position_size
        exit_value = exit_price * position_size

        entry_fee = entry_value * (config.TAKER_FEE_PCT / 100)
        exit_fee = exit_value * (config.TAKER_FEE_PCT / 100)
        slippage_cost = (entry_value * config.SLIPPAGE_PCT / 100) + (exit_value * config.SLIPPAGE_PCT / 100)

        # Direction-aware PnL
        if direction == 'SHORT':
            # Short: profit when price goes DOWN (entry - exit)
            gross_pnl = entry_value - exit_value
        else:
            # Long: profit when price goes UP (exit - entry)
            gross_pnl = exit_value - entry_value

        net_pnl = gross_pnl - entry_fee - exit_fee - slippage_cost
        pnl_pct = (net_pnl / entry_value) * 100 if entry_value != 0 else 0

        closed_at_ts = datetime.now().timestamp()
        hold_time_hours = (closed_at_ts - opened_at_ts) / 3600

        cursor.execute('''
            INSERT INTO trades
            (signal_id, symbol, entry_price, exit_price, position_size, direction, regime,
             gross_pnl_usd, entry_fee_usd, exit_fee_usd, slippage_cost_usd, net_pnl_usd,
             pnl_pct, exit_reason, opened_at, hold_time_hours)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (signal_id, symbol, entry_price, exit_price, position_size, direction, regime,
              gross_pnl, entry_fee, exit_fee, slippage_cost, net_pnl, pnl_pct,
              exit_reason, datetime.fromtimestamp(opened_at_ts).isoformat(), hold_time_hours))

        cursor.execute('DELETE FROM positions WHERE id=?', (position_id,))

        conn.commit()
        conn.close()
        return net_pnl

    def get_recent_trades(self, days=30, direction=None):
        conn = self.get_conn()
        cursor = conn.cursor()
        if direction:
            cursor.execute('''
                SELECT * FROM trades
                WHERE closed_at > datetime('now', '-' || ? || ' days')
                AND direction = ?
                ORDER BY closed_at DESC
            ''', (days, direction))
        else:
            cursor.execute('''
                SELECT * FROM trades
                WHERE closed_at > datetime('now', '-' || ? || ' days')
                ORDER BY closed_at DESC
            ''', (days,))
        rows = cursor.fetchall()
        conn.close()
        return rows

    def get_trade_with_signal(self, days=30):
        conn = self.get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT t.*, s.rvol, s.velocity, s.trend, s.orderbook_imbalance
            FROM trades t
            JOIN signals s ON t.signal_id = s.id
            WHERE t.closed_at > datetime('now', '-' || ? || ' days')
        ''', (days,))
        rows = cursor.fetchall()
        conn.close()
        return rows

    def log_learning_update(self, weights_before, weights_after, train_ic, test_ic, num_trades):
        conn = self.get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO learning_log
            (weights_before, weights_after, train_ic, test_ic, num_trades_used)
            VALUES (?, ?, ?, ?, ?)
        ''', (json.dumps(weights_before), json.dumps(weights_after), train_ic, test_ic, num_trades))
        conn.commit()
        conn.close()

    def get_position_by_symbol_direction(self, symbol, direction):
        """Check if we already have a position in this symbol+direction"""
        conn = self.get_conn()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT * FROM positions WHERE symbol=? AND direction=?',
            (symbol, direction)
        )
        row = cursor.fetchone()
        conn.close()
        return row

    def get_portfolio_heat(self):
        """
        Calculate current portfolio heat (total risk across open positions).
        Returns decimal fraction of equity at risk.
        """
        from config.config import config

        conn = self.get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT SUM(net_pnl_usd) FROM trades')
        result = cursor.fetchone()[0]
        conn.close()
        total_pnl = result if result else 0
        equity = config.SIM_EQUITY_START + total_pnl

        positions = self.get_open_positions()
        total_risk = 0

        for pos in positions:
            entry_price = pos[3]
            position_size = pos[4]
            stop_loss_price = pos[5]
            direction = pos[11] if len(pos) > 11 else 'LONG'

            position_value = entry_price * position_size

            if direction == 'SHORT':
                # Short: risk = (stop - entry) / entry
                stop_distance_pct = (stop_loss_price - entry_price) / entry_price
            else:
                # Long: risk = (entry - stop) / entry
                stop_distance_pct = (entry_price - stop_loss_price) / entry_price

            risk_usd = position_value * stop_distance_pct
            total_risk += risk_usd

        heat = total_risk / equity if equity > 0 else 0
        return heat


db = Database()
