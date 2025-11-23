import os
import numpy as np
from database.models import db
from monitoring.telegram_alerter import send_alert
from config.config import config

def calculate_sharpe():
    trades = db.get_recent_trades(days=30)
    if len(trades) < 10:
        return 0.0
    pnl_pcts = [t[11] or 0 for t in trades]
    if np.std(pnl_pcts) == 0:
        return 0.0
    return (np.mean(pnl_pcts) / np.std(pnl_pcts)) * np.sqrt(365)

def calculate_max_drawdown():
    trades = db.get_recent_trades(days=30)
    if not trades:
        return 0.0
    equity_curve = [0]
    for t in trades:
        equity_curve.append(equity_curve[-1] + (t[10] or 0))
    max_dd = 0
    peak = equity_curve[0]
    for val in equity_curve:
        if val > peak:
            peak = val
        if peak > 0:
            dd = ((peak - val) / peak) * 100
            max_dd = max(max_dd, dd)
    return max_dd

def check_scale_up():
    conn = db.get_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM trades')
    total_trades = cursor.fetchone()[0]
    conn.close()
    
    if total_trades == 0 or total_trades % 50 != 0:
        return False
    
    recent_trades = db.get_recent_trades(days=999)[-50:]
    if not recent_trades:
        return False
    
    wins = len([t for t in recent_trades if (t[11] or 0) > 0])
    win_rate = (wins / len(recent_trades)) * 100
    
    sharpe = calculate_sharpe()
    max_dd = calculate_max_drawdown()
    
    if win_rate > 55 and sharpe > 1.0 and max_dd < 5:
        current_equity = config.SIM_EQUITY_START
        new_equity = current_equity * 1.20
        
        env_path = '.env'
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                lines = f.readlines()
            with open(env_path, 'w') as f:
                for line in lines:
                    if line.startswith('SIM_EQUITY_START='):
                        f.write(f'SIM_EQUITY_START={new_equity}\n')
                    else:
                        f.write(line)
        
        send_alert(
            f"📈 Capital Scale-Up\n"
            f"Trades: {total_trades}\n"
            f"Win Rate: {win_rate:.1f}%\n"
            f"Sharpe: {sharpe:.2f}\n"
            f"Max DD: {max_dd:.1f}%\n"
            f"Old Equity: ${current_equity:.2f}\n"
            f"New Equity: ${new_equity:.2f}"
        )
        return True
    
    return False
