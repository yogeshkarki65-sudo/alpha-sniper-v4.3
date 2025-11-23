import os
from datetime import datetime
import requests

from config.config import config
from database.models import db

class RiskManager:
    def __init__(self):
        self.daily_hwm = self.get_current_equity()
        self.load_daily_stats()
    
    def get_current_equity(self):
        conn = db.get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT SUM(net_pnl_usd) FROM trades')
        result = cursor.fetchone()[0]
        conn.close()
        total_pnl = result if result else 0
        return config.SIM_EQUITY_START + total_pnl
    
    def load_daily_stats(self):
        today = datetime.now().date().isoformat()
        conn = db.get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT high_water_mark FROM daily_stats WHERE date=?', (today,))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            self.daily_hwm = result[0]
        else:
            self.daily_hwm = self.get_current_equity()
            self.save_daily_hwm()
    
    def save_daily_hwm(self):
        today = datetime.now().date().isoformat()
        current_equity = self.get_current_equity()
        
        conn = db.get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO daily_stats (date, high_water_mark, starting_equity)
            VALUES (?, ?, ?)
        ''', (today, max(self.daily_hwm, current_equity), config.SIM_EQUITY_START))
        conn.commit()
        conn.close()
    
    def check_drawdown(self):
        current_equity = self.get_current_equity()
        if current_equity > self.daily_hwm:
            self.daily_hwm = current_equity
            self.save_daily_hwm()
        
        if self.daily_hwm <= 0:
            return True
        
        drawdown_pct = ((self.daily_hwm - current_equity) / self.daily_hwm) * 100
        
        if drawdown_pct >= config.MAX_DAILY_DRAWDOWN_PCT:
            self.pause_trading(f"Max drawdown reached: {drawdown_pct:.2f}%")
            return False
        
        return True
    
    def pause_trading(self, reason):
        env_path = '.env'
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                lines = f.readlines()
            with open(env_path, 'w') as f:
                for line in lines:
                    if line.startswith('TRADING_PAUSED='):
                        f.write('TRADING_PAUSED=true\n')
                    else:
                        f.write(line)
        try:
            from monitoring.telegram_alerter import send_alert
            send_alert(f"🚨 TRADING PAUSED: {reason}")
        except Exception:
            pass
    
    def calculate_position_size(self, entry_price, stop_loss_pct):
        current_equity = self.get_current_equity()
        max_loss_usd = current_equity * (config.MAX_POSITION_RISK_PCT / 100)
        if entry_price <= 0 or stop_loss_pct <= 0:
            return 0
        
        position_size = max_loss_usd / (entry_price * (stop_loss_pct / 100))
        
        max_position_value = current_equity * 0.20
        max_position_size = max_position_value / entry_price
        
        return max(0, min(position_size, max_position_size))
    
    def check_correlation(self, new_symbol, open_positions):
        if len(open_positions) == 0:
            return True
        
        try:
            resp = requests.get(f"{config.MEXC_BASE_URL}/api/v3/ticker/24hr", timeout=10)
            tickers = {t['symbol']: float(t.get('priceChangePercent', 0)) for t in resp.json()}
        except Exception:
            return True
        
        new_change = tickers.get(new_symbol, 0)
        correlated_count = 0
        
        for pos in open_positions:
            pos_symbol = pos[2]
            pos_change = tickers.get(pos_symbol, 0)
            if abs(new_change) > 5 and abs(pos_change) > 5:
                if (new_change > 0 and pos_change > 0) or (new_change < 0 and pos_change < 0):
                    correlated_count += 1
        
        return correlated_count < config.MAX_CORRELATED_POSITIONS
    
    def can_trade(self):
        if config.TRADING_PAUSED:
            return False, "Trading is paused"
        
        if not self.check_drawdown():
            return False, "Max drawdown exceeded"
        
        open_positions = db.get_open_positions()
        if len(open_positions) >= config.MAX_CONCURRENT_POS:
            return False, "Max concurrent positions reached"
        
        return True, "OK"

risk_manager = RiskManager()
