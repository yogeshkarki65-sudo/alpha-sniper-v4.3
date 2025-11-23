import numpy as np
from config.config import config
from database.models import db
from scanner.scorer import load_weights, save_weights
from learning.validation import validate_weights
from monitoring.telegram_alerter import send_alert

def run_self_learning():
    if not config.LEARNING_ENABLED:
        print("📚 Learning disabled")
        return
    
    print("🧠 Running self-learning...")
    
    trades = db.get_trade_with_signal(days=config.LEARNING_LOOKBACK_DAYS)
    
    if len(trades) < config.MIN_TRADES_FOR_LEARNING:
        print(f"Need {config.MIN_TRADES_FOR_LEARNING} trades, have {len(trades)}")
        return
    
    print(f"Analyzing {len(trades)} trades...")
    
    res = validate_weights(trades)
    if res is None:
        print("❌ Validation failed")
        return
    train_ic, test_ic = res
    
    avg_test_ic = np.mean(list(test_ic.values()))
    if avg_test_ic < 0:
        print(f"⚠️  Test IC negative ({avg_test_ic:.3f}), keeping old weights")
        send_alert(f"⚠️  Learning validation failed (IC: {avg_test_ic:.3f})")
        return
    
    old_weights = load_weights()
    
    raw_new_weights = {
        'rvol': max(train_ic['rvol'], 0.01),
        'velocity': max(train_ic['velocity'], 0.01),
        'trend': max(train_ic['trend'], 0.01),
        'orderbook_imbalance': max(train_ic['orderbook_imbalance'], 0.01)
    }
    
    total = sum(raw_new_weights.values())
    normalized_new_weights = {k: v/total for k, v in raw_new_weights.items()}
    
    final_weights = {}
    max_change = config.MAX_WEIGHT_CHANGE_PCT / 100
    
    for key in old_weights:
        old_val = old_weights[key]
        new_val = normalized_new_weights[key]
        change = new_val - old_val
        if old_val == 0:
            final_weights[key] = new_val
            continue
        if abs(change / old_val) > max_change:
            capped_change = max_change * old_val * (1 if change > 0 else -1)
            final_weights[key] = old_val + capped_change
        else:
            final_weights[key] = new_val
    
    total_final = sum(final_weights.values())
    final_weights = {k: v/total_final for k, v in final_weights.items()}
    
    max_weight_change_pct = max(
        abs((final_weights[k] - old_weights[k]) / old_weights[k]) * 100 
        for k in old_weights if old_weights[k] != 0
    )
    
    save_weights(final_weights)
    
    db.log_learning_update(
        old_weights,
        final_weights,
        np.mean(list(train_ic.values())),
        avg_test_ic,
        len(trades)
    )
    
    print(f"✅ Weights updated | Train IC: {np.mean(list(train_ic.values())):.3f} | Test IC: {avg_test_ic:.3f}")
    print(f"Old weights: {old_weights}")
    print(f"New weights: {final_weights}")
    
    if max_weight_change_pct > config.ALERT_ON_WEIGHT_CHANGE_PCT:
        send_alert(
            f"📊 Weights Updated\n"
            f"Max change: {max_weight_change_pct:.1f}%\n"
            f"Test IC: {avg_test_ic:.3f}\n"
            f"rvol: {old_weights['rvol']:.3f} → {final_weights['rvol']:.3f}\n"
            f"velocity: {old_weights['velocity']:.3f} → {final_weights['velocity']:.3f}\n"
            f"trend: {old_weights['trend']:.3f} → {final_weights['trend']:.3f}\n"
            f"ob: {old_weights['orderbook_imbalance']:.3f} → {final_weights['orderbook_imbalance']:.3f}"
        )
