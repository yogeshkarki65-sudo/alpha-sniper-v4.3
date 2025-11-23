"""
Short Scanner Module

Generates short candidates by:
1. TOP LOSERS: Coins with largest negative 24h returns (sorted ASC)
2. BREAKDOWN: Coins breaking below support with volume

Candidates include direction='SHORT' for downstream processing.
"""

import requests
import time
import traceback
from config.config import config
from scanner.orderbook import get_orderbook_imbalance, get_spread_pct


def get_regime_detector():
    """Lazy import to avoid circular imports"""
    try:
        from shorts.regime_detector import regime_detector
        return regime_detector
    except Exception as e:
        print(f"[short_scanner] Error importing regime_detector: {e}")
        return None


def get_top_losers(limit=50):
    """
    Fetch top losing USDT pairs by 24h price change.
    Filters by min volume and max spread.
    """
    try:
        url = f"{config.MEXC_BASE_URL}/api/v3/ticker/24hr"
        print(f"[short_scanner] Fetching 24h tickers for losers...")
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        tickers = resp.json()
    except Exception as e:
        print(f"[short_scanner] Error fetching tickers: {e}")
        return []

    losers = []
    for t in tickers:
        symbol = t.get("symbol", "")
        if not symbol.endswith("USDT"):
            continue

        try:
            quote_volume = float(t.get("quoteVolume", 0) or 0)
            price_change = float(t.get("priceChangePercent", 0) or 0)
        except (ValueError, TypeError):
            continue

        if price_change >= 0:
            continue

        if quote_volume < getattr(config, 'MIN_24H_QUOTE_VOLUME', 50000):
            continue

        losers.append((price_change, quote_volume, t))

    losers.sort(key=lambda x: x[0])
    top_losers = losers[:limit]

    filtered = []
    for price_change, qvol, t in top_losers:
        symbol = t.get("symbol")
        try:
            spread = get_spread_pct(symbol)
            max_spread = getattr(config, 'MAX_ALLOWED_SPREAD_PCT', 1.1)
            if spread > max_spread:
                continue
            t["spread_pct"] = spread
            filtered.append(t)
        except Exception as e:
            continue
        time.sleep(0.02)

    print(f"[short_scanner] Found {len(filtered)} top losers after filters")
    return filtered


def get_funding_rate(symbol):
    """Get current funding rate - placeholder returning safe default"""
    return 0.0001


def compute_short_features(ticker, regime):
    """Compute features relevant for short signals."""
    if not ticker or not isinstance(ticker, dict):
        return None

    try:
        symbol = ticker.get("symbol")
        if not symbol:
            return None

        volume = float(ticker.get("volume", 0) or 0)
        quote_volume = float(ticker.get("quoteVolume", 0) or 0)
        price_change_pct = float(ticker.get("priceChangePercent", 0) or 0)
        high_price = float(ticker.get("highPrice", 1) or 1)
        low_price = float(ticker.get("lowPrice", 1) or 1)
        last_price = float(ticker.get("lastPrice", 0) or 0)

        avg_hourly_volume = quote_volume / 24 if quote_volume > 0 else 1
        rvol = volume / max(avg_hourly_volume, 1)
        velocity = price_change_pct

        price_range = high_price - low_price
        if price_range > 0:
            trend = (last_price - low_price) / price_range
        else:
            trend = 0.5

        if high_price > 0:
            drop_from_high = (high_price - last_price) / high_price
        else:
            drop_from_high = 0

        try:
            if getattr(config, 'CHECK_ORDER_BOOK_IMBALANCE', False):
                ob_imb = get_orderbook_imbalance(symbol)
            else:
                ob_imb = 0.0
        except Exception:
            ob_imb = 0.0

        funding_8h = get_funding_rate(symbol)
        spread = ticker.get("spread_pct", 0.5)

        return {
            "symbol": symbol,
            "direction": "SHORT",
            "rvol": rvol,
            "velocity": velocity,
            "trend": trend,
            "drop_from_high": drop_from_high,
            "orderbook_imbalance": ob_imb,
            "last_price": last_price,
            "quote_volume_24h": quote_volume,
            "funding_8h": funding_8h,
            "spread_pct": spread,
            "regime": regime,
        }
    except Exception as e:
        print(f"[short_scanner] Error computing features: {e}")
        return None


def filter_short_candidate(features, regime):
    """Apply regime-specific filters to short candidates."""
    if not features or not isinstance(features, dict):
        return False, "Invalid features"

    try:
        symbol = features.get("symbol", "UNKNOWN")
        velocity = features.get("velocity", 0)
        rvol = features.get("rvol", 0)
        trend = features.get("trend", 0.5)
        funding_8h = features.get("funding_8h", 0)
        spread = features.get("spread_pct", 0)
        quote_volume = features.get("quote_volume_24h", 0)

        # Universal filters
        max_funding = getattr(config, 'MAX_FUNDING_8H_SHORT', 0.00035)
        if funding_8h > max_funding:
            return False, f"Funding too high: {funding_8h:.5f}"

        max_spread = getattr(config, 'MAX_ALLOWED_SPREAD_PCT', 1.1)
        if spread > max_spread:
            return False, f"Spread too wide: {spread:.2f}%"

        min_rvol = getattr(config, 'MIN_RVOL_15M_BEAR_SHORT', 1.25)
        if rvol < min_rvol:
            return False, f"RVOL too low: {rvol:.2f}"

        # Regime-specific filters
        if regime == "SIDEWAYS":
            if velocity < -25:
                return False, f"Already dumped too much: {velocity:.1f}%"
            if velocity > -2:
                return False, f"Not weak enough: {velocity:.1f}%"
            if trend > 0.6:
                return False, f"Price too high in range: {trend:.2f}"

        elif regime == "MILD_BEAR":
            if velocity < -40:
                return False, f"Too extended: {velocity:.1f}%"
            if velocity > -5:
                return False, f"Not bearish enough: {velocity:.1f}%"
            if trend > 0.5:
                return False, f"Not breaking down: {trend:.2f}"

        elif regime == "DEEP_BEAR":
            if velocity < -50:
                return False, f"Capitulation - too risky: {velocity:.1f}%"
            if velocity > -8:
                return False, f"Not weak enough for deep bear: {velocity:.1f}%"
            min_vol = getattr(config, 'MIN_24H_QUOTE_VOLUME', 50000) * 2
            if quote_volume < min_vol:
                return False, "Insufficient liquidity for deep bear short"
            if trend > 0.4:
                return False, f"Need cleaner breakdown: {trend:.2f}"

        return True, "OK"

    except Exception as e:
        return False, f"Filter error: {e}"


def calculate_short_score(features, regime):
    """Calculate signal score for short candidates."""
    if not features or not isinstance(features, dict):
        return 0

    try:
        rvol = features.get("rvol", 0)
        velocity = features.get("velocity", 0)
        trend = features.get("trend", 0.5)
        ob_imb = features.get("orderbook_imbalance", 0)

        # RVOL score
        if rvol < 1.0:
            rvol_score = rvol * 50
        elif rvol <= 3.0:
            rvol_score = 50 + (rvol - 1.0) * 25
        else:
            rvol_score = 100 - (rvol - 3.0) * 5
        rvol_score = max(0, min(100, rvol_score))

        # Velocity score
        abs_vel = abs(velocity)
        if abs_vel < 2:
            vel_score = 20
        elif abs_vel <= 30:
            vel_score = 20 + (abs_vel - 2) * 2.86
        else:
            vel_score = 100 - (abs_vel - 30) * 2
        vel_score = max(0, min(100, vel_score))

        # Trend score (inverted for shorts)
        trend_score = (1 - trend) * 100
        trend_score = max(0, min(100, trend_score))

        # Orderbook score
        ob_score = (1 - ob_imb) * 50
        ob_score = max(0, min(100, ob_score))

        # Regime-specific weights
        if regime == "SIDEWAYS":
            weights = {"rvol": 0.25, "velocity": 0.20, "trend": 0.35, "ob": 0.20}
        elif regime == "MILD_BEAR":
            weights = {"rvol": 0.30, "velocity": 0.30, "trend": 0.25, "ob": 0.15}
        else:
            weights = {"rvol": 0.25, "velocity": 0.25, "trend": 0.30, "ob": 0.20}

        score = (
            weights["rvol"] * rvol_score +
            weights["velocity"] * vel_score +
            weights["trend"] * trend_score +
            weights["ob"] * ob_score
        )

        return round(score, 1)

    except Exception as e:
        print(f"[short_scanner] Error calculating score: {e}")
        return 0


def scan_for_shorts(regime=None):
    """Main entry point: scan for short candidates."""
    try:
        rd = get_regime_detector()
        if rd is None:
            print("[short_scanner] Regime detector not available")
            return []

        if regime is None:
            regime = rd.detect_regime()

        if not rd.should_trade_shorts(regime):
            print(f"[short_scanner] Shorts disabled in {regime} regime")
            return []

        print(f"[short_scanner] Scanning for shorts in {regime} regime...")

        losers = get_top_losers(limit=60)
        if not losers:
            print("[short_scanner] No losers found")
            return []

        candidates = []
        min_score = getattr(config, 'MIN_SIGNAL_SCORE', 80)

        for ticker in losers:
            try:
                features = compute_short_features(ticker, regime)
                if not features:
                    continue

                passed, reason = filter_short_candidate(features, regime)
                if not passed:
                    continue

                score = calculate_short_score(features, regime)

                if score >= min_score:
                    candidates.append({
                        "symbol": features.get("symbol", "UNKNOWN"),
                        "score": score,
                        "rvol": features.get("rvol", 0),
                        "velocity": features.get("velocity", 0),
                        "trend": features.get("trend", 0.5),
                        "orderbook_imbalance": features.get("orderbook_imbalance", 0),
                        "last_price": features.get("last_price", 0),
                        "direction": "SHORT",
                        "regime": regime,
                        "funding_8h": features.get("funding_8h", 0),
                    })
                    print(
                        f"[short_scanner] SHORT candidate: {features.get('symbol')} "
                        f"score={score:.1f} vel={features.get('velocity', 0):.1f}%"
                    )
            except Exception as e:
                print(f"[short_scanner] Error processing ticker: {e}")
                continue

        candidates.sort(key=lambda x: x.get("score", 0), reverse=True)
        print(f"[short_scanner] Found {len(candidates)} short candidates")
        return candidates

    except Exception as e:
        print(f"[short_scanner] Error in scan_for_shorts: {e}")
        traceback.print_exc()
        return []


if __name__ == "__main__":
    rd = get_regime_detector()
    if rd:
        regime = rd.detect_regime()
        print(f"Current regime: {regime}")
        candidates = scan_for_shorts(regime)
        print(f"Short candidates: {len(candidates)}")
