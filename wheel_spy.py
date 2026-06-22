import os
import time
import datetime
import math
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest, GetOptionContractsRequest
from alpaca.trading.enums import OrderSide, TimeInForce, AssetClass
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest, OptionLatestQuoteRequest
from dotenv import load_dotenv
import requests

# Load variables from .env
load_dotenv()

# Alpaca API credentials should be set in environment variables
API_KEY = os.environ.get("ALPACA_API_KEY", "your_api_key_here")
SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY", "your_secret_key_here")
PAPER = os.environ.get("ALPACA_PAPER_TRADE", "true").lower() == "true"
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

trading_client = TradingClient(API_KEY, SECRET_KEY, paper=PAPER)
stock_data_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
option_data_client = OptionHistoricalDataClient(API_KEY, SECRET_KEY)

SYMBOL = "SPY"
CONTRACT_MULTIPLIER = 100
DTE_TARGET = 7
PROFIT_TARGET = 0.75
MIN_ROLL_PREMIUM = 0.10 # $10 per contract = $0.10 per share

def get_current_price(symbol):
    request = StockLatestQuoteRequest(symbol_or_symbols=[symbol])
    quote = stock_data_client.get_stock_latest_quote(request)
    return quote[symbol].ask_price

def get_option_contract(symbol, target_dte, strike_price, option_type):
    # Find the target expiration date
    target_date = datetime.date.today() + datetime.timedelta(days=target_dte)
    target_date_str = target_date.strftime('%Y-%m-%d')
    
    # Options might not expire exactly on target_date
    req = GetOptionContractsRequest(
        underlying_symbols=[symbol],
        status="active",
        expiration_date_gte=target_date_str,
        type=option_type,
        limit=1000
    )
    
    contracts = trading_client.get_option_contracts(req)
        
    if not contracts or not contracts.option_contracts:
        return None

    # Filter to exact date if available, or closest date
    available_dates = sorted(list(set(c.expiration_date for c in contracts.option_contracts)))
    if not available_dates:
        return None
    
    closest_date = min(available_dates, key=lambda d: abs((d - target_date).days))
    
    # Find the contract with strike closest to strike_price on the chosen date
    best_contract = None
    min_diff = float('inf')
    for contract in contracts.option_contracts:
        if contract.expiration_date == closest_date:
            diff = abs(float(contract.strike_price) - strike_price)
            if diff < min_diff:
                min_diff = diff
                best_contract = contract

    return best_contract

def parse_occ_symbol(symbol):
    # Example: SPY241220P00500000 -> SPY, 241220, P, 00500000
    import re
    match = re.match(r'^([A-Z]+)(\d{6})([CP])(\d{8})$', symbol)
    if not match:
        return None
    root, date_str, cp, strike_str = match.groups()
    strike = float(strike_str) / 1000.0
    exp_date = datetime.datetime.strptime(date_str, "%y%m%d").date()
    return {"root": root, "expiration": exp_date, "type": cp, "strike": strike}

def get_option_price(symbol):
    # Fetch option mid price
    req = OptionLatestQuoteRequest(symbol_or_symbols=[symbol])
    try:
        quote = option_data_client.get_option_latest_quote(req)
        ask = quote[symbol].ask_price
        bid = quote[symbol].bid_price
        return (ask + bid) / 2.0
    except Exception:
        return 0.0

def send_telegram_message(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")

def place_order(symbol, qty, side, reason=""):
    req = MarketOrderRequest(
        symbol=symbol,
        qty=abs(qty),
        side=side,
        time_in_force=TimeInForce.DAY
    )
    res = trading_client.submit_order(order_data=req)
    msg = f"🟢 <b>TRADE EXECUTED</b>\nSide: {side.name}\nQty: {abs(qty)}\nSymbol: {symbol}\nReason: {reason}\nOrder ID: {res.id}"
    print(msg.replace('<b>', '').replace('</b>', ''))
    send_telegram_message(msg)

def check_positions_and_wheel():
    positions = trading_client.get_all_positions()
    
    spy_shares = 0
    spy_avg_price = 0.0
    short_put = None
    short_call = None
    
    for pos in positions:
        if pos.symbol == SYMBOL:
            spy_shares = int(pos.qty)
            spy_avg_price = float(pos.avg_entry_price)
        elif pos.asset_class == AssetClass.US_OPTION and pos.symbol.startswith(SYMBOL):
            if int(pos.qty) < 0:
                parsed = parse_occ_symbol(pos.symbol)
                if parsed:
                    if parsed["type"] == "P":
                        short_put = pos
                    elif parsed["type"] == "C":
                        short_call = pos

    current_price = get_current_price(SYMBOL)
    
    if spy_shares >= 100:
        # We are assigned, need to sell calls
        if not short_call:
            print("Holding shares, selling Covered Call.")
            target_strike = max(spy_avg_price, current_price * 1.02)
            contract = get_option_contract(SYMBOL, DTE_TARGET, target_strike, "call")
            if contract:
                place_order(contract.symbol, 1, OrderSide.SELL, "Selling Covered Call")
            else:
                print("Could not find suitable call contract to sell.")
        else:
            # Check call profit target or ITM
            print("Managing existing Covered Call.")
            avg_entry = float(short_call.avg_entry_price)
            current_value = float(short_call.current_price)
            
            # Profit hit 75%?
            if current_value <= avg_entry * (1 - PROFIT_TARGET):
                print("Call hit 75% profit! Rolling...")
                place_order(short_call.symbol, 1, OrderSide.BUY, "Closing Covered Call (75% Profit)") # Buy to close
                
                target_strike = max(spy_avg_price, current_price * 1.02)
                contract = get_option_contract(SYMBOL, DTE_TARGET, target_strike, "call")
                if contract:
                    place_order(contract.symbol, 1, OrderSide.SELL, "Rolling Covered Call (75% Profit)")
            else:
                parsed = parse_occ_symbol(short_call.symbol)
                strike = parsed["strike"]
                if current_price > strike: # ITM
                    print("Call is ITM. Attempting to roll out and up.")
                    target_strike = current_price * 1.02
                    new_contract = get_option_contract(SYMBOL, DTE_TARGET, target_strike, "call")
                    if new_contract:
                        new_price = get_option_price(new_contract.symbol)
                        current_close_price = get_option_price(short_call.symbol)
                        
                        if (new_price - current_close_price) >= MIN_ROLL_PREMIUM:
                            print("Rolling call for a credit.")
                            place_order(short_call.symbol, 1, OrderSide.BUY, "Rolling Call ITM (Buy to Close)")
                            place_order(new_contract.symbol, 1, OrderSide.SELL, "Rolling Call ITM (Sell to Open)")
                        else:
                            print("Cannot roll for target credit. Accepting assignment (letting it get called away).")
                else:
                    print(f"Call is OTM (Strike: {strike}, Current: {current_price}). Holding.")
    else:
        # We are not assigned, we should be selling puts
        if not short_put:
            print("No shares, selling Cash Secured Put.")
            target_strike = current_price * 0.98
            contract = get_option_contract(SYMBOL, DTE_TARGET, target_strike, "put")
            if contract:
                place_order(contract.symbol, 1, OrderSide.SELL, "Selling Cash Secured Put")
            else:
                print("Could not find suitable put contract to sell.")
        else:
            # Check put profit target or ITM
            print("Managing existing Cash Secured Put.")
            avg_entry = float(short_put.avg_entry_price)
            current_value = float(short_put.current_price)
            
            # Profit hit 75%?
            if current_value <= avg_entry * (1 - PROFIT_TARGET):
                print("Put hit 75% profit! Rolling...")
                place_order(short_put.symbol, 1, OrderSide.BUY, "Closing Put (75% Profit)") # Buy to close
                
                target_strike = current_price * 0.98
                contract = get_option_contract(SYMBOL, DTE_TARGET, target_strike, "put")
                if contract:
                    place_order(contract.symbol, 1, OrderSide.SELL, "Rolling Put (75% Profit)")
            else:
                parsed = parse_occ_symbol(short_put.symbol)
                strike = parsed["strike"]
                if current_price < strike: # ITM
                    print("Put is ITM. Attempting to roll down and out.")
                    target_strike = strike * 0.98 # roll down
                    new_contract = get_option_contract(SYMBOL, DTE_TARGET, target_strike, "put")
                    if new_contract:
                        new_price = get_option_price(new_contract.symbol)
                        current_close_price = get_option_price(short_put.symbol)
                        
                        if (new_price - current_close_price) >= MIN_ROLL_PREMIUM:
                            print("Rolling put for a credit.")
                            place_order(short_put.symbol, 1, OrderSide.BUY, "Rolling Put ITM (Buy to Close)")
                            place_order(new_contract.symbol, 1, OrderSide.SELL, "Rolling Put ITM (Sell to Open)")
                        else:
                            print("Cannot roll for target credit. Accepting assignment.")
                else:
                    print(f"Put is OTM (Strike: {strike}, Current: {current_price}). Holding.")

def main():
    print(f"Starting Wheel Strategy for {SYMBOL} on Alpaca Paper: {PAPER}")
    while True:
        try:
            clock = trading_client.get_clock()
            if clock.is_open:
                check_positions_and_wheel()
            else:
                print("Market is closed. Waiting...")
        except Exception as e:
            print(f"Error: {e}")
            
        time.sleep(360) # Check every 10 mins

if __name__ == "__main__":
    main()
