# Critical Issues & Risk Review

1. Exchange/API Risk
   - If MEXC API returns bad or stale data, prices and 24h stats may be wrong.
   - Mitigation: basic try/except, but no secondary validation or fallback.

2. Slippage & Fees
   - Slippage and fees are modeled as fixed percentages, but real-world values vary.
   - Bot could be over-optimistic in SIM vs live.
   - Mitigation: keep SIM conservative, validate vs real fills before scaling.

3. Daily Reset Logic
   - Daily stats / high-watermark rely on local time of the container.
   - If timezone mismatches your mental “day”, daily drawdown behavior might surprise you.

4. Trailing Stop Behavior
   - trailing_stop_price is updated based on highest_price; short-term price spikes can tighten stops aggressively.
   - In very volatile markets this may lead to many small exits.

5. Correlation Check (Simplistic)
   - Uses 24h percent change only; it's a crude proxy.
   - Highly correlated coins might sneak through in short windows.

6. Database Schema Changes
   - This version assumes fresh DB.
   - If you reuse an old trades.db, schema mismatches can cause errors or wrong stats.

7. Capital Scaling
   - Auto-scale uses last 50 trades; if regime changes fast, it may scale up right before conditions worsen.
   - Always manually review before letting capital manager change real allocations.

8. Learning Module
   - Self-learning only adjusts weights if IC is positive on test, but feature indices are hard-coded.
   - If schema of get_trade_with_signal changes, learning could break silently or use wrong columns.

9. Emergency Stop Script
   - stop_trading.sh edits .env and sends a Telegram alert, but does not kill Docker container.
   - You must still `docker compose down` to be 100% sure.

10. No Backtest Harness
   - Tests/backtest.py is a placeholder.
   - True historical replay is not implemented; forward SIM must be treated as live experiment.

High-level recommendation:
- Run this for at least 7–14 days in SIM mode.
- Watch daily reports + /health + logs.
- Only move to real money with tiny size and strict manual supervision.
