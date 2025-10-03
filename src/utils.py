import re
import time
import hashlib
import hmac
import requests
import json
# import logging
import os

# logging убран, используем print

def extract_symbol(message: str) -> str | None:
    match = re.search(r'([A-Z]+/[A-Z]+)', message)
    if match:
        return match.group(1)
    print("Символ не найден в сообщении")
    return None   

def extract_exchange(text: str):
    import re
    match = re.search(r'([A-Za-z]+):\s*([A-Za-z]+)[→\-–>]([A-Za-z]+)', text)
    if match:
        buy_exchange = match.group(2).lower()
        sell_exchange = match.group(3).lower()
        return buy_exchange, sell_exchange
    return None, None

def gen_sign(method, url, api_key, api_secret, query_string=None, payload_string=None):
    timestamp = str(time.time())
    payload_hash = hashlib.sha512((payload_string or "").encode('utf-8')).hexdigest()
    sign_string = f'{method}\n{url}\n{query_string or ""}\n{payload_hash}\n{timestamp}'
    signature = hmac.new(api_secret.encode('utf-8'), sign_string.encode('utf-8'), hashlib.sha512).hexdigest()
    return {'KEY': api_key, 'Timestamp': timestamp, 'SIGN': signature}

def get_balance(symbol, host, prefix, api_key, api_secret):
    url = f"{host}{prefix}/spot/accounts"
    headers = {'Accept': 'application/json'}
    sign_headers = gen_sign('GET', f"{prefix}/spot/accounts", api_key, api_secret)
    headers.update(sign_headers)
    response = requests.get(url, headers=headers)
    data = response.json()
    for entry in data:
        if entry['currency'] == symbol:
            balance = float(entry['available'])
            # logging.info(f"Баланс для {symbol}: {balance}")
            return balance
    # logging.info(f"Баланс для {symbol} не найден")
    return 0.0

def get_price(symbol, host, prefix):
    url = f"{host}{prefix}/spot/tickers?currency_pair={symbol}"
    headers = {'Accept': 'application/json'}
    response = requests.get(url, headers=headers)

    try:
        data = response.json()
        price = float(data[0]['lowest_ask'])
        # logging.info(f"Цена для {symbol}: {price}")
        return price
    except Exception as e:
        print(f"⚠️ Ошибка парсинга цены для {symbol}: {e}")
        print(f"🔍 Сырой ответ: {response.text}")
        return None
    
def send_order(symbol, host, prefix, api_key, api_secret, amount):
    endpoint = '/spot/orders'
    url = f"{host}{prefix}{endpoint}"
    headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}

    body = {
        "currency_pair": symbol,
        "type": "market",
        "account": "unified",
        "side": "sell",
        "amount": str(amount),
        "time_in_force": "ioc",
        "auto_borrow":'True'
    }

    body_json = json.dumps(body)
    sign_headers = gen_sign('POST', prefix + endpoint, api_key, api_secret, "", body_json)
    headers.update(sign_headers)

    response = requests.post(url, headers=headers, data=body_json)
    return response.json()    

def calculate_average_buy_price(deposit, symbol, exchange):
    try:
        orderbook = exchange.fetch_order_book(symbol)
        asks = orderbook['asks']

        total_cost = 0
        total_amount = 0
        remaining_deposit = deposit

        for item in asks:
            if len(item) < 2:
                print(f"Некорректный элемент в asks: {item}")
                continue
            price, volume = item[0], item[1]
            if remaining_deposit <= 0:
                break
            cost = price * volume
            if cost <= remaining_deposit:
                total_cost += cost
                total_amount += volume
                remaining_deposit -= cost
            else:
                affordable_volume = remaining_deposit / price
                total_cost += affordable_volume * price
                total_amount += affordable_volume
                remaining_deposit = 0

        if total_amount == 0:
            print(f"Недостаточно ликвидности для {symbol}")
            return None

        average_price = total_cost / total_amount
        print(f"💱 Средняя цена покупки для {symbol}: {average_price:.6f} USDT")
        return average_price

    except Exception as e:
        print(f"Ошибка расчета средней цены покупки для {symbol}: {e}")
        return None
    
def calculate_average_sell_price(deposit, symbol, exchange):
    try:
        ticker = exchange.fetch_ticker(symbol)
        current_price = ticker['last'] or ticker['bid']
        base_amount = deposit / current_price

        orderbook = exchange.fetch_order_book(symbol)
        bids = orderbook['bids']

        total_revenue = 0
        total_sold = 0
        remaining_amount = base_amount

        for price, volume in bids:
            if remaining_amount <= 0:
                break
            if volume <= remaining_amount:
                total_revenue += price * volume
                total_sold += volume
                remaining_amount -= volume
            else:
                total_revenue += price * remaining_amount
                total_sold += remaining_amount
                remaining_amount = 0

        if total_sold == 0:
            print(f"Недостаточно ликвидности для {symbol}")
            return None

        average_price = total_revenue / total_sold
        print(f"💱 Средняя цена продажи для {symbol}: {average_price:.6f} USDT")
        return average_price

    except Exception as e:
        print(f"Ошибка расчета средней цены продажи для {symbol}: {e}")
        return None

def get_max_borrowable_gate(symbol, host, prefix, api_key, api_secret):
    url_path = f"{prefix}/margin/cross/borrowable"
    url = f"{host}{url_path}"
    headers = {'Accept': 'application/json'}
    
    # Извлекаем базовую валюту из пары (MORE_USDT -> MORE)
    base_currency = symbol.split('_')[0]
    
    query_string = f"currency={base_currency}"
    sign_headers = gen_sign('GET', url_path, api_key, api_secret, query_string, None)
    headers.update(sign_headers)
    params = {'currency': base_currency}
    
    response = requests.get(url, headers=headers, params=params)
    data = response.json()
    try:
        # API возвращает 'amount' для доступного займа
        return float(data['amount'])
    except Exception as e:
        print(f"Ошибка получения max borrowable для {symbol}: {e}")
        print(f"Ответ: {data}")
        return 0.0

def is_borrowable_gate(symbol, host, prefix):
    """Проверяет доступность займа для валюты на Gate.io"""
    try:
        # Извлекаем базовую валюту из пары (MORE_USDT -> MORE)
        base_currency = symbol.split('_')[0]
        url = f'{host}{prefix}/margin/cross/currencies/{base_currency}'
        headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        return "name" in data
    except Exception as e:
        print(f"Ошибка проверки доступности займа для {symbol}: {e}")
        return False

# if __name__ == "__main__":
#     import ccxt
#     from dotenv import load_dotenv
#     load_dotenv()
#     # OKX тест
#     exchange_okx = ccxt.okx({
#         'apiKey': os.getenv('OKX_KEY'),
#         'secret': os.getenv('OKX_SECRET'),
#         'password': os.getenv('OKX_PASSWORD'),
#     })
#     symbol = 'PENGU/USDT'
#     deposit = 10
#     print(f"Тест: calculate_average_buy_price для OKX, symbol={symbol}, deposit={deposit}")
#     price = calculate_average_buy_price(deposit, symbol, exchange_okx)
#     print(f"Результат OKX: {price}")

#     # MEXC тест
#     exchange_mexc = ccxt.mexc({
#         'apiKey': os.getenv('MEXC_KEY'),
#         'secret': os.getenv('MEXC_SECRET'),
#     })
#     print(f"Тест: calculate_average_buy_price для MEXC, symbol={symbol}, deposit={deposit}")
#     price_mexc = calculate_average_buy_price(deposit, symbol, exchange_mexc)
#     print(f"Результат MEXC: {price_mexc}")

#     # BITGET тест
#     exchange_bitget = ccxt.bitget({
#         'apiKey': os.getenv('BITGET_KEY'),
#         'secret': os.getenv('BITGET_SECRET'),
#         'password': os.getenv('BITGET_PASSWORD'),
#     })
#     print(f"Тест: calculate_average_buy_price для BITGET, symbol={symbol}, deposit={deposit}")
#     price_bitget = calculate_average_buy_price(deposit, symbol, exchange_bitget)
#     print(f"Результат BITGET: {price_bitget}")