import numpy as np
from datetime import datetime
from database.models import db
from risk.risk_manager import risk_manager
from monitoring.telegram_alerter import send_alert

def generate_daily_report():
    print("📊 Generating daily report...")
    
    today = datetime.now().date().isoformat()
    conn = db.get_conn()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM trades 
        WHERE DATE(closed_at) = ?
    ''', (today,))
    today_trades = cursor.fetchall()
    
    cursor.execute('''
        SELECT * FROM trades 
        WHERE closed_at > datetime('now', '-7 days')
        ORDER BY closed_at DESC
    ''')
    recent_trades = cursor.fetchall()
    
    conn.close()
    
    current_equity = risk_manager.get_current_equity()
    
    if today_trades:
        today_pnl = sum(t[10] for t in today_trades)
        today_fees = sum((t[7] or 0) + (t[8] or 0) for t in today_trades)
        today_wins = len([t for t in today_trades if (t[11] or 0) > 0])
        today_win_rate = (today_wins / len(today_trades)) * 100
    else:
        today_pnl = 0
        today_fees = 0
        today_win_rate = 0
    
    if recent_trades:
        week_pnl = sum(t[10] for t in recent_trades)
        week_wins = len([t for t in recent_trades if (t[11] or 0) > 0])
        week_win_rate = (week_wins / len(recent_trades)) * 100
        best_trade = max(recent_trades, key=lambda t: t[11] or 0)
        worst_trade = min(recent_trades, key=lambda t: t[11] or 0)
        pnl_pcts = [t[11] or 0 for t in recent_trades]
        if len(pnl_pcts) > 1 and np.std(pnl_pcts) > 0:
            sharpe = (np.mean(pnl_pcts) / np.std(pnl_pcts)) * np.sqrt(365)
        else:
            sharpe = 0
    else:
        week_pnl = 0
        week_win_rate = 0
        best_trade = None
        worst_trade = None
        sharpe = 0
    
    open_positions = db.get_open_positions()
    
    report = f"""
📊 <b>Daily Trading Report</b>
━━━━━━━━━━━━━━━━━━━━━━━
💰 <b>Equity:</b> ${current_equity:.2f}
📈 <b>Today P&L:</b> ${today_pnl:.2f}
📅 <b>Week P&L:</b> ${week_pnl:.2f}

<b>Today Stats:</b>
  Trades: {len(today_trades)}
  Win Rate: {today_win_rate:.1f}%
  Fees Paid: ${today_fees:.2f}

<b>7-Day Stats:</b>
  Trades: {len(recent_trades)}
  Win Rate: {week_win_rate:.1f}%
  Sharpe Ratio: {sharpe:.2f}

<b>Open Positions:</b> {len(open_positions)}
"""
    if best_trade:
        report += f"\n🏆 <b>Best:</b> {best_trade[2]} (+{best_trade[11]:.2f}%)"
    if worst_trade:
        report += f"\n📉 <b>Worst:</b> {worst_trade[2]} ({worst_trade[11]:.2f}%)"
    
    print(report)
    send_alert(report)
    return report
