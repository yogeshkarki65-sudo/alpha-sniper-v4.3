import os
from datetime import datetime, timedelta
from risk.risk_manager import risk_manager
from monitoring.telegram_alerter import send_alert
from database.models import db

def run_daily_reset():
    print("🔄 Running daily reset...")
    
    current_equity = risk_manager.get_current_equity()
    risk_manager.daily_hwm = current_equity
    risk_manager.save_daily_hwm()
    
    env_path = '.env'
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            lines = f.readlines()
        with open(env_path, 'w') as f:
            for line in lines:
                if line.startswith('TRADING_PAUSED='):
                    f.write('TRADING_PAUSED=false\n')
                else:
                    f.write(line)
    
    yesterday = (datetime.now().date() - timedelta(days=1)).isoformat()
    conn = db.get_conn()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT COUNT(*), 
               SUM(net_pnl_usd),
               SUM(CASE WHEN pnl_pct > 0 THEN 1 ELSE 0 END),
               SUM(entry_fee_usd + exit_fee_usd)
        FROM trades
        WHERE DATE(closed_at) = ?
    ''', (yesterday,))
    result = cursor.fetchone()
    conn.close()
    
    if result and result[0]:
        num_trades = result[0]
        total_pnl = result[1] or 0
        wins = result[2] or 0
        total_fees = result[3] or 0
        win_rate = (wins / num_trades) * 100 if num_trades > 0 else 0
        
        send_alert(
            f"🌅 Daily Reset Complete\n"
            f"Date: {yesterday}\n"
            f"Trades: {num_trades}\n"
            f"P&L: ${total_pnl:.2f}\n"
            f"Win Rate: {win_rate:.1f}%\n"
            f"Fees: ${total_fees:.2f}\n"
            f"Current Equity: ${current_equity:.2f}"
        )
    
    print(f"✅ Reset complete | Equity: ${current_equity:.2f}")
