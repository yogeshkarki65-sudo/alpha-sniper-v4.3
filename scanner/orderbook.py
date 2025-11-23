import requests
from config.config import config

def get_orderbook_imbalance(symbol):
    try:
        url = f"{config.MEXC_BASE_URL}/api/v3/depth"
        params = {'symbol': symbol, 'limit': 20}
        resp = requests.get(url, params=params, timeout=5)
        data = resp.json()
        
        bid_volume = sum(float(bid[1]) for bid in data.get('bids', []))
        ask_volume = sum(float(ask[1]) for ask in data.get('asks', []))
        
        if bid_volume + ask_volume == 0:
            return 0.0
        
        imbalance = (bid_volume - ask_volume) / (bid_volume + ask_volume)
        return imbalance
    except Exception:
        return 0.0

def get_spread_pct(symbol):
    try:
        url = f"{config.MEXC_BASE_URL}/api/v3/ticker/bookTicker"
        params = {'symbol': symbol}
        resp = requests.get(url, params=params, timeout=5)
        data = resp.json()
        
        bid = float(data['bidPrice'])
        ask = float(data['askPrice'])
        
        if bid == 0:
            return 999.0
        
        spread_pct = ((ask - bid) / bid) * 100
        return spread_pct
    except Exception:
        return 999.0
