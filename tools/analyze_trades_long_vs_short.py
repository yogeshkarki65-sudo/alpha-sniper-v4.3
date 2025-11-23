#!/usr/bin/env python3
"""
Trade Analysis Script - LONG vs SHORT Comparison

Reads trade history and produces statistics for:
- LONG trades
- SHORT trades
- Combined

Run with:
    python tools/analyze_trades_long_vs_short.py
"""

import sys
import os
import sqlite3
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_db_path():
    """Get the database path"""
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'trades.db')


def analyze_trades(db_path, days=30):
    """Analyze trades from database"""
    if not os.path.exists(db_path):
        print(f"Database not found: {db_path}")
        print("Run the bot first to generate trades.")
        return None

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if direction column exists
    cursor.execute("PRAGMA table_info(trades)")
    columns = [col[1] for col in cursor.fetchall()]

    if 'direction' not in columns:
        print("Warning: 'direction' column not found in trades table.")
        print("All trades will be treated as LONG (legacy data).")
        has_direction = False
    else:
        has_direction = True

    # Fetch trades
    if has_direction:
        cursor.execute('''
            SELECT symbol, entry_price, exit_price, position_size, direction,
                   gross_pnl_usd, net_pnl_usd, pnl_pct, exit_reason, closed_at
            FROM trades
            WHERE closed_at > datetime('now', '-' || ? || ' days')
            ORDER BY closed_at DESC
        ''', (days,))
    else:
        cursor.execute('''
            SELECT symbol, entry_price, exit_price, position_size, 'LONG' as direction,
                   gross_pnl_usd, net_pnl_usd, pnl_pct, exit_reason, closed_at
            FROM trades
            WHERE closed_at > datetime('now', '-' || ? || ' days')
            ORDER BY closed_at DESC
        ''', (days,))

    trades = cursor.fetchall()
    conn.close()

    return trades


def calculate_stats(trades, direction_filter=None):
    """Calculate statistics for a set of trades"""
    if direction_filter:
        filtered = [t for t in trades if t[4] == direction_filter]
    else:
        filtered = trades

    if not filtered:
        return {
            'count': 0,
            'wins': 0,
            'losses': 0,
            'win_rate': 0,
            'total_pnl': 0,
            'avg_pnl': 0,
            'total_r': 0,
            'avg_r': 0,
            'best_trade': 0,
            'worst_trade': 0,
        }

    wins = [t for t in filtered if (t[6] or 0) > 0]  # net_pnl_usd > 0
    losses = [t for t in filtered if (t[6] or 0) <= 0]

    total_pnl = sum(t[6] or 0 for t in filtered)
    pnl_pcts = [t[7] or 0 for t in filtered]

    # Calculate R (risk-adjusted return)
    # Assuming 0.25% risk per trade baseline
    risk_per_trade_pct = 0.25
    r_values = [(pct / risk_per_trade_pct) for pct in pnl_pcts]
    total_r = sum(r_values)

    return {
        'count': len(filtered),
        'wins': len(wins),
        'losses': len(losses),
        'win_rate': (len(wins) / len(filtered) * 100) if filtered else 0,
        'total_pnl': total_pnl,
        'avg_pnl': total_pnl / len(filtered) if filtered else 0,
        'total_pnl_pct': sum(pnl_pcts),
        'avg_pnl_pct': sum(pnl_pcts) / len(filtered) if filtered else 0,
        'total_r': total_r,
        'avg_r': total_r / len(filtered) if filtered else 0,
        'best_trade': max(pnl_pcts) if pnl_pcts else 0,
        'worst_trade': min(pnl_pcts) if pnl_pcts else 0,
    }


def print_stats(name, stats):
    """Print formatted statistics"""
    print(f"\n{'=' * 40}")
    print(f"{name}")
    print(f"{'=' * 40}")

    if stats['count'] == 0:
        print("  No trades found")
        return

    print(f"  Trades:     {stats['count']}")
    print(f"  Wins:       {stats['wins']}")
    print(f"  Losses:     {stats['losses']}")
    print(f"  Win Rate:   {stats['win_rate']:.1f}%")
    print(f"  Total PnL:  ${stats['total_pnl']:.2f}")
    print(f"  Avg PnL:    ${stats['avg_pnl']:.2f}")
    print(f"  Total PnL%: {stats['total_pnl_pct']:.2f}%")
    print(f"  Avg PnL%:   {stats['avg_pnl_pct']:.2f}%")
    print(f"  Total R:    {stats['total_r']:+.2f}")
    print(f"  Avg R:      {stats['avg_r']:+.2f}")
    print(f"  Best:       {stats['best_trade']:+.2f}%")
    print(f"  Worst:      {stats['worst_trade']:+.2f}%")


def print_recent_trades(trades, limit=10):
    """Print recent trades"""
    print(f"\n{'=' * 60}")
    print(f"RECENT TRADES (last {limit})")
    print(f"{'=' * 60}")

    for t in trades[:limit]:
        symbol = t[0]
        direction = t[4]
        pnl = t[6] or 0
        pnl_pct = t[7] or 0
        exit_reason = t[8]
        closed_at = t[9]

        dir_emoji = "" if direction == 'SHORT' else ""
        pnl_emoji = "" if pnl > 0 else ""

        print(f"  {dir_emoji} {symbol:12} {direction:5} | {pnl_emoji} ${pnl:+8.2f} ({pnl_pct:+6.2f}%) | {exit_reason:15} | {closed_at}")


def main():
    print("=" * 60)
    print("ALPHA SNIPER - TRADE ANALYSIS: LONG vs SHORT")
    print("=" * 60)

    db_path = get_db_path()
    print(f"\nDatabase: {db_path}")

    days = 30
    if len(sys.argv) > 1:
        try:
            days = int(sys.argv[1])
        except ValueError:
            pass

    print(f"Analyzing trades from last {days} days...")

    trades = analyze_trades(db_path, days)

    if trades is None:
        return

    if not trades:
        print("\nNo trades found in the specified period.")
        return

    # Calculate stats
    long_stats = calculate_stats(trades, 'LONG')
    short_stats = calculate_stats(trades, 'SHORT')
    combined_stats = calculate_stats(trades)

    # Print results
    print_stats("LONGS", long_stats)
    print_stats("SHORTS", short_stats)
    print_stats("COMBINED", combined_stats)

    # Print recent trades
    print_recent_trades(trades, limit=15)

    # Summary comparison
    print(f"\n{'=' * 60}")
    print("SUMMARY COMPARISON")
    print(f"{'=' * 60}")

    if long_stats['count'] > 0 and short_stats['count'] > 0:
        print(f"\n  Direction  | Trades | Win Rate | Avg R   | Total PnL")
        print(f"  -----------|--------|----------|---------|----------")
        print(f"  LONG       | {long_stats['count']:6} | {long_stats['win_rate']:6.1f}%  | {long_stats['avg_r']:+6.2f}  | ${long_stats['total_pnl']:+8.2f}")
        print(f"  SHORT      | {short_stats['count']:6} | {short_stats['win_rate']:6.1f}%  | {short_stats['avg_r']:+6.2f}  | ${short_stats['total_pnl']:+8.2f}")
        print(f"  COMBINED   | {combined_stats['count']:6} | {combined_stats['win_rate']:6.1f}%  | {combined_stats['avg_r']:+6.2f}  | ${combined_stats['total_pnl']:+8.2f}")

        # Recommendation
        if short_stats['avg_r'] > 0:
            print(f"\n  SHORT engine is contributing positively (Avg R: {short_stats['avg_r']:+.2f})")
        else:
            print(f"\n  SHORT engine needs tuning (Avg R: {short_stats['avg_r']:+.2f})")
    elif short_stats['count'] == 0:
        print("\n  No SHORT trades yet. Check if shorts are enabled and regime allows them.")
    else:
        print("\n  No LONG trades yet.")


if __name__ == "__main__":
    main()
