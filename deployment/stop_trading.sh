#!/bin/bash
# Emergency kill switch

echo "🚨 EMERGENCY STOP TRIGGERED"

if [ -f ".env" ]; then
  sed -i 's/TRADING_PAUSED=false/TRADING_PAUSED=true/g' .env
fi

python3 - << 'PY'
from monitoring.telegram_alerter import send_alert
send_alert('🚨 EMERGENCY STOP ACTIVATED - All trading paused')
PY

echo "✅ Trading paused. Restart container to resume."
