import requests
from config.config import config

def send_alert(message):
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        print(f"[ALERT] {message}")
        return
    
    try:
        url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            'chat_id': config.TELEGRAM_CHAT_ID,
            'text': message,
            'parse_mode': 'HTML'
        }
        requests.post(url, data=data, timeout=10)
    except Exception as e:
        print(f"Failed to send Telegram alert: {e}")
