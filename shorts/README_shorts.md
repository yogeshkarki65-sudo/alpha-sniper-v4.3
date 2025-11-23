# Short Engine - Diagnosis & Implementation

## Root Cause Analysis: Why Shorts Never Fired

After analyzing the Alpha Sniper V2.2 codebase, I identified these critical gaps:

### 1. SCANNER BIAS (Primary Issue)
- `scanner/scanner.py` sorts candidates by `quoteVolume DESC` (most liquid)
- The scorer rewards HIGH trend values (price near daily high)
- No top-losers feed or breakdown detection existed
- Result: Only bullish/momentum candidates were ever produced

### 2. NO REGIME DETECTION
- Zero regime detection code existed
- Config mentioned `ENABLE_SHORTS_IN_*` but no code honored these flags
- No BTC-based market regime analysis

### 3. NO DIRECTION FIELD
- Database tables (signals, positions, trades) had no `direction` column
- Everything was implicitly LONG - no way to differentiate

### 4. LONG-ONLY PnL CALCULATION
- `trader.py` calculated PnL as `(current - entry)` which is only correct for longs
- Stop loss was always BELOW entry (long logic)
- Take profit was always ABOVE entry (long logic)

### 5. LONG-BIASED SCORING
- `trend_norm = trend * 100` where trend = (price - low) / range
- This rewards being near daily HIGH - perfect for longs, wrong for shorts
- For shorts we need the INVERSE: favor coins near daily LOW with breakdown

## Solution Implemented

### New Components:
1. `shorts/regime_detector.py` - BTC-based market regime detection
2. `shorts/short_scanner.py` - Top losers + breakdown detection
3. `shorts/short_scorer.py` - Short-specific scoring logic

### Modified Components:
1. `config/config.py` - Added all short-related config
2. `database/models.py` - Added direction field to all tables
3. `trader/trader.py` - Direction-aware PnL, stops, exits
4. `scanner/scanner.py` - Integrated short candidates
5. `main.py` - Wire up regime detection

## Short Signal Logic by Regime

### SIDEWAYS
- Goal: Fade weak breakouts and failed pumps
- 4h trend: flat to mildly down
- Price broke below 1h support
- RVOL >= 1.25 on red candle
- Avoid coins that dumped >25% (too late)

### MILD_BEAR
- Goal: Trend-following shorts
- 4h: clear downtrend (below EMA)
- Price retesting broken support
- RVOL >= 1.25 on continuation
- 24h return between -5% and -40%

### DEEP_BEAR
- Goal: Careful continuation shorts
- Strong daily downtrend
- 1h lower-high rejection
- Extra liquidity check
- Avoid extreme capitulation (>-50%)

## Risk Parameters

All shorts use regime-specific risk from config:
- SIDEWAYS: 0.15% risk per trade
- MILD_BEAR: 0.15% risk per trade
- DEEP_BEAR: 0.12% risk per trade

Funding rate cap: 0.035% (8h) - skip shorts with crazy positive funding
