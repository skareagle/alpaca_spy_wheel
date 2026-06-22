import os
from alpaca.trading.client import TradingClient
from dotenv import load_dotenv
import requests

def test_connections():
    print("Testing connections...")
    load_dotenv()
    
    # 1. Test Alpaca
    api_key = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")
    paper = os.environ.get("ALPACA_PAPER_TRADE", "true").lower() == "true"
    
    if not api_key or api_key == "your_api_key_here":
        print("❌ Alpaca API Key is not set or still default.")
        return
        
    try:
        trading_client = TradingClient(api_key, secret_key, paper=paper)
        account = trading_client.get_account()
        print(f"✅ Alpaca connected successfully! Account Status: {account.status}, Equity: ${account.equity}")
    except Exception as e:
        print(f"❌ Failed to connect to Alpaca: {e}")
        return
        
    # 2. Test Telegram
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not bot_token or bot_token == "your_telegram_bot_token_here":
        print("❌ Telegram Bot Token is not set or still default.")
        return
        
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": f"✅ <b>Alpaca SPY Wheel Bot Test</b>\nConnections successful! Account Equity: ${account.equity}",
            "parse_mode": "HTML"
        }
        res = requests.post(url, json=payload, timeout=5)
        if res.status_code == 200:
            print("✅ Telegram message sent successfully!")
        else:
            print(f"❌ Failed to send Telegram message. Status code: {res.status_code}, Response: {res.text}")
    except Exception as e:
        print(f"❌ Failed to send Telegram message: {e}")

if __name__ == "__main__":
    test_connections()
