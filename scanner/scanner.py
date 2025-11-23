"""
Scanner Module - Generates both LONG and SHORT signals

Flow:
1. Detect current regime via RegimeDetector
2. Scan for LONG candidates (top gainers with momentum)
3. Scan for SHORT candidates (top losers with breakdown) if regime allows
4. Store signals in database with direction and regime
"""

import requests
import time
import traceback
from config.config import config
from database.models import db
from scanner.orderbook import get_orderbook_imbalance, get_spread_pct
from scanner.scorer import calculate_score


def get_usdt_pairs():
    """
    Fetch USDT pairs from MEXC 24h ticker endpoint, filter by liquidity + spread,
    and only keep the top N by quote volume so we don't hammer the API.
    """
    try:
        url = f"{config.MEXC_BASE_URL}/api/v3/ticker/24hr"
        print(f"[scanner] Fetching 24h tickers from: {url}")
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        tickers = resp.json()
    except Exception as e:
        print(f"[scanner] Error fetching 24h tickers: {e}")
        return []

    # Filter only USDT symbols and with quoteVolume present
    usdt = []
    for t in tickers:
        symbol = t.get("symbol", "")
        if not symbol.endswith("USDT"):
            continue

        try:
            quote_volume = float(t.get("quoteVolume", 0) or 0)
        except Exception:
            quote_volume = 0.0

        usdt.append((quote_volume, t))

    if not usdt:
        print("[scanner] No USDT tickers found from exchange")
        return []

    # Sort by quote volume (desc) and keep top N
    usdt.sort(key=lambda x: x[0], reverse=True)
    TOP_N = 60
    top = usdt[:TOP_N]

    print(f"[scanner] Got {len(usdt)} USDT pairs, using top {len(top)} by volume")

    filtered = []
    for idx, (qvol, t) in enumerate(top, start=1):
        symbol = t.get("symbol")
        try:
            # Liquidity filter
            if qvol < config.MIN_LIQUIDITY_VOLUME_24H:
                continue

            # Spread filter
            spread = get_spread_pct(symbol)
            if spread > 0.5:
                continue

            filtered.append(t)
        except Exception as e:
            print(f"[scanner] Skipping {symbol} due to error in filters: {e}")
            continue

        # Small delay to be nice to the API
        time.sleep(0.05)

    print(f"[scanner] After filters: {len(filtered)} liquid USDT pairs")
    return filtered


def compute_features(ticker):
    """
    Compute RVOL, velocity, trend, orderbook imbalance for a symbol.
    Returns None on any error.
    """
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

        # RVOL: crude approx using quote_volume / 24
        avg_hourly_volume = quote_volume / 24 if quote_volume > 0 else 1
        rvol = volume / max(avg_hourly_volume, 1)

        # Velocity: daily % move
        velocity = price_change_pct

        # Trend: where are we between low and high
        price_range = high_price - low_price
        if price_range > 0 and high_price > 0 and low_price > 0:
            trend = (last_price - low_price) / price_range
        else:
            trend = 0.5

        # Orderbook imbalance
        try:
            if config.CHECK_ORDER_BOOK_IMBALANCE:
                ob_imb = get_orderbook_imbalance(symbol)
            else:
                ob_imb = 0.0
        except Exception:
            ob_imb = 0.0

        return {
            "symbol": symbol,
            "rvol": rvol,
            "velocity": velocity,
            "trend": trend,
            "orderbook_imbalance": ob_imb,
            "last_price": last_price,
        }
    except Exception as e:
        print(f"[scanner] Error computing features for {ticker.get('symbol', 'unknown')}: {e}")
        return None


def scan_for_longs(pairs, regime):
    """
    Scan for LONG candidates.
    Uses existing scoring logic - rewards high trend (near daily high) and positive velocity.
    """
    signals_created = 0

    for t in pairs:
        try:
            f = compute_features(t)
            if not f or not isinstance(f, dict):
                continue

            # Safely get velocity with default
            velocity = f.get("velocity", 0)
            if velocity is None:
                velocity = 0

            # For longs, we want positive velocity (gainers)
            if velocity < 0:
                continue  # Skip losers for long signals

            score = calculate_score(
                f.get("rvol", 0),
                f.get("velocity", 0),
                f.get("trend", 0.5),
                f.get("orderbook_imbalance", 0),
            )

            if score >= config.MIN_SIGNAL_SCORE:
                db.create_signal(
                    f["symbol"],
                    score,
                    f.get("rvol", 0),
                    f.get("velocity", 0),
                    f.get("trend", 0.5),
                    f.get("orderbook_imbalance", 0),
                    f.get("last_price", 0),
                    direction='LONG',
                    regime=regime
                )
                signals_created += 1
                print(
                    f"[scanner] LONG: {f['symbol']} "
                    f"score={score:.1f} rvol={f.get('rvol', 0):.2f} "
                    f"vel={f.get('velocity', 0):.2f}% trend={f.get('trend', 0):.2f}"
                )
        except Exception as e:
            print(f"[scanner] Error processing long candidate: {e}")
            continue

    return signals_created


def scan_for_shorts(regime):
    """
    Scan for SHORT candidates using the short_scanner module.
    Only runs if shorts are enabled for the current regime.
    """
    try:
        from shorts.regime_detector import regime_detector
        from shorts.short_scanner import scan_for_shorts as short_scan

        if not regime_detector.should_trade_shorts(regime):
            print(f"[scanner] Shorts disabled in {regime} regime")
            return 0

        print(f"[scanner] Scanning for SHORT candidates in {regime} regime...")

        candidates = short_scan(regime)
        if not candidates:
            print("[scanner] No short candidates found")
            return 0

        signals_created = 0

        for c in candidates:
            try:
                if not isinstance(c, dict):
                    continue

                db.create_signal(
                    c.get("symbol", "UNKNOWN"),
                    c.get("score", 0),
                    c.get("rvol", 0),
                    c.get("velocity", 0),
                    c.get("trend", 0.5),
                    c.get("orderbook_imbalance", 0),
                    c.get("last_price", 0),
                    direction='SHORT',
                    regime=regime
                )
                signals_created += 1
                print(
                    f"[scanner] SHORT: {c.get('symbol', 'UNKNOWN')} "
                    f"score={c.get('score', 0):.1f} vel={c.get('velocity', 0):.1f}% "
                    f"rvol={c.get('rvol', 0):.2f} trend={c.get('trend', 0):.2f}"
                )
            except Exception as e:
                print(f"[scanner] Error creating short signal: {e}")
                continue

        return signals_created

    except Exception as e:
        print(f"[scanner] Error in short scanning: {e}")
        traceback.print_exc()
        return 0


def run_scanner():
    """
    Main scanner entry point.
    1. Detect regime
    2. Scan for LONG signals
    3. Scan for SHORT signals (if enabled)
    """
    print("Running scanner...")

    try:
        # Import and detect regime
        from shorts.regime_detector import regime_detector
        regime = regime_detector.detect_regime()
    except Exception as e:
        print(f"[scanner] Error detecting regime: {e}, defaulting to SIDEWAYS")
        regime = "SIDEWAYS"

    print(f"[scanner] Current regime: {regime}")

    try:
        print(f"[scanner] Shorts enabled: BULL={config.ENABLE_SHORTS_IN_BULL}, "
              f"SIDEWAYS={config.ENABLE_SHORTS_IN_SIDEWAYS}, "
              f"MILD_BEAR={config.ENABLE_SHORTS_IN_MILD_BEAR}, "
              f"DEEP_BEAR={config.ENABLE_SHORTS_IN_DEEP_BEAR}")
    except AttributeError as e:
        print(f"[scanner] Warning: Some config attributes missing: {e}")

    # Scan for longs
    pairs = get_usdt_pairs()
    print(f"[scanner] Final universe size: {len(pairs)} symbols")

    if not pairs:
        print("[scanner] No pairs to scan (check network / API / filters)")
        return 0

    long_signals = 0
    try:
        long_signals = scan_for_longs(pairs, regime)
        print(f"[scanner] Created {long_signals} LONG signals")
    except Exception as e:
        print(f"[scanner] Error in long scanning: {e}")
        traceback.print_exc()

    # Scan for shorts
    short_signals = 0
    try:
        short_signals = scan_for_shorts(regime)
        print(f"[scanner] Created {short_signals} SHORT signals")
    except Exception as e:
        print(f"[scanner] Error in short scanning: {e}")
        traceback.print_exc()

    total_signals = long_signals + short_signals
    print(f"[scanner] Total signals created: {total_signals}")

    return total_signals


if __name__ == "__main__":
    run_scanner()
