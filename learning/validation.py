import numpy as np
from scipy.stats import pearsonr

def split_train_test(data, train_ratio=0.7):
    n = len(data)
    if n == 0:
        return [], []
    idx = np.arange(n)
    np.random.shuffle(idx)
    split = int(n * train_ratio)
    train_idx = idx[:split]
    test_idx = idx[split:]
    train = [data[i] for i in train_idx]
    test = [data[i] for i in test_idx]
    return train, test

def calculate_ic(features, pnl):
    if len(features) != len(pnl) or len(features) == 0:
        return 0.0
    try:
        corr, _ = pearsonr(features, pnl)
        return corr if not np.isnan(corr) else 0.0
    except Exception:
        return 0.0

def validate_weights(trades_data):
    if len(trades_data) < 20:
        return None, None
    
    train_data, test_data = split_train_test(trades_data)
    
    train_rvol = [t[15] for t in train_data]
    train_velocity = [t[16] for t in train_data]
    train_trend = [t[17] for t in train_data]
    train_ob = [t[18] for t in train_data]
    train_pnl = [t[11] for t in train_data]
    
    train_ic = {
        'rvol': calculate_ic(train_rvol, train_pnl),
        'velocity': calculate_ic(train_velocity, train_pnl),
        'trend': calculate_ic(train_trend, train_pnl),
        'orderbook_imbalance': calculate_ic(train_ob, train_pnl)
    }
    
    test_rvol = [t[15] for t in test_data]
    test_velocity = [t[16] for t in test_data]
    test_trend = [t[17] for t in test_data]
    test_ob = [t[18] for t in test_data]
    test_pnl = [t[11] for t in test_data]
    
    test_ic = {
        'rvol': calculate_ic(test_rvol, test_pnl),
        'velocity': calculate_ic(test_velocity, test_pnl),
        'trend': calculate_ic(test_trend, test_pnl),
        'orderbook_imbalance': calculate_ic(test_ob, test_pnl)
    }
    
    return train_ic, test_ic
