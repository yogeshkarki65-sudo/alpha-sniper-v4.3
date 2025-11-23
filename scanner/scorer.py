import json
import os

def load_weights():
    weights_file = 'data/weights.json'
    if not os.path.exists(weights_file):
        default_weights = {
            'rvol': 0.25,
            'velocity': 0.25,
            'trend': 0.25,
            'orderbook_imbalance': 0.25
        }
        os.makedirs('data', exist_ok=True)
        with open(weights_file, 'w') as f:
            json.dump(default_weights, f)
        return default_weights
    
    with open(weights_file, 'r') as f:
        return json.load(f)

def save_weights(weights):
    with open('data/weights.json', 'w') as f:
        json.dump(weights, f, indent=2)

def calculate_score(rvol, velocity, trend, orderbook_imbalance):
    weights = load_weights()
    
    rvol_norm = min(rvol * 10, 100)
    velocity_norm = min(abs(velocity) * 2, 100)
    trend_norm = min(trend * 100, 100)
    ob_norm = (orderbook_imbalance + 1) * 50
    
    score = (
        weights['rvol'] * rvol_norm +
        weights['velocity'] * velocity_norm +
        weights['trend'] * trend_norm +
        weights['orderbook_imbalance'] * ob_norm
    )
    return score
