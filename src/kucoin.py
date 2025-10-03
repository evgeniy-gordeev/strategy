import time
import base64
import hmac
import hashlib
import requests
import sys
import uuid
import os
import json
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv('KUCOIN_KEY')
API_SECRET = os.getenv('KUCOIN_SECRET')
API_PASSPHRASE = os.getenv('KUCOIN_PASSWORD')

symbol = sys.argv[1] if len(sys.argv) > 1 else None
symbol = symbol.replace("/", "-") #особенность kucoin формат символа PENGU-USDT

deposit_limit = int(sys.argv[2]) if len(sys.argv) > 2 else None

BASE_URL = 'https://api.kucoin.com'

import sys
sys.stdout.reconfigure(encoding='utf-8')


def sign(method, endpoint, body=''):
    now = str(int(time.time() * 1000))
    str_to_sign = now + method.upper() + endpoint + body
    signature = base64.b64encode(
        hmac.new(API_SECRET.encode('utf-8'), str_to_sign.encode('utf-8'), hashlib.sha256).digest()
    ).decode()
    passphrase = base64.b64encode(
        hmac.new(API_SECRET.encode('utf-8'), API_PASSPHRASE.encode('utf-8'), hashlib.sha256).digest()
    ).decode()
    return {
        "KC-API-KEY": API_KEY,
        "KC-API-SIGN": signature,
        "KC-API-TIMESTAMP": now,
        "KC-API-PASSPHRASE": passphrase,
        "KC-API-KEY-VERSION": "2",
        "Content-Type": "application/json"
    }


def get_price(symbol):
    """Получить текущую цену символа"""
    url = f"{BASE_URL}/api/v1/market/orderbook/level1?symbol={symbol}"
    r = requests.get(url).json()
    data = r.get("data")
    if r.get("code") != "200000" or not data:
        print(f"KUCOIN - ❌ Ошибка получения цены: {r}")
        sys.exit(1)
    return {
        'bid': float(data.get('bestBid', 0)),
        'ask': float(data.get('bestAsk', 0)),
        'price': float(data.get('price', 0))
    }


def get_margin_account():
    """Получить информацию о маржинальном аккаунте"""
    endpoint = '/api/v1/margin/account'
    url = BASE_URL + endpoint
    headers = sign("GET", endpoint)
    r = requests.get(url, headers=headers).json()
    if r.get("code") != "200000":
        print(f"KUCOIN - ❌ Ошибка получения маржинального аккаунта: {r}")
        sys.exit(1)
    return r['data']


def get_usdt_balance():
    """Получить доступный USDT баланс в маржинальном аккаунте"""
    account_data = get_margin_account()
    accounts = account_data['accounts']
    for asset in accounts:
        if asset['currency'] == 'USDT':
            return float(asset['availableBalance'])
    
    print("KUCOIN - ❌ USDT не найден в cross margin аккаунте")
    sys.exit(1)


def get_margin_position(currency):
    """Получить текущую маржинальную позицию для валюты"""
    account_data = get_margin_account()
    accounts = account_data['accounts']
    for asset in accounts:
        if asset['currency'] == currency:
            return {
                'currency': currency,
                'total': float(asset.get('totalBalance', 0)),
                'available': float(asset.get('availableBalance', 0)),
                'liability': float(asset.get('liability', 0)),
                'interest': float(asset.get('interest', 0))
            }
    return None


def place_margin_sell_order(symbol, base_amount, symbol_info):
    """Разместить маржинальный ордер на продажу (шорт)"""
    endpoint = '/api/v1/margin/order'
    url = BASE_URL + endpoint
    
    # Форматируем количество правильно для API
    formatted_amount = format_amount_for_api(base_amount, symbol_info['baseIncrement'])
    
    body = {
        "symbol": symbol,
        "side": "sell",
        "type": "market",
        "size": formatted_amount,
        "autoBorrow": True,
        "clientOid": str(uuid.uuid4())
    }
    body_str = json.dumps(body)
    headers = sign("POST", endpoint, body_str)
    response = requests.post(url, headers=headers, data=body_str)
    return response.json()


def place_margin_buy_order(symbol, base_amount):
    """Разместить маржинальный ордер на покупку (закрыть шорт или лонг)"""
    endpoint = '/api/v1/margin/order'
    url = BASE_URL + endpoint
    body = {
        "symbol": symbol,
        "side": "buy",
        "type": "market",
        "size": str(base_amount),
        "autoBorrow": True,
        "clientOid": str(uuid.uuid4())
    }
    body_str = json.dumps(body)
    headers = sign("POST", endpoint, body_str)
    response = requests.post(url, headers=headers, data=body_str)
    return response.json()


def get_margin_limits():
    """Получить лимиты маржинального заимствования"""
    endpoint = '/api/v1/margin/config'
    url = BASE_URL + endpoint
    headers = sign("GET", endpoint)
    r = requests.get(url, headers=headers).json()
    return r


def print_margin_status():
    """Показать текущий статус маржинального аккаунта"""
    # Получаем цены
    prices = get_price(symbol)
    print(f"KUCOIN - 💱 Цена {symbol}: {prices['price']}")
    
    # Получаем баланс USDT
    usdt_balance = get_usdt_balance()
    print(f"KUCOIN - Доступно USDT: {usdt_balance}")
    
    # Получаем позицию по TON
    base_currency = symbol.split('-')[0]  # TON
    ton_position = get_margin_position(base_currency)
    if ton_position:
        print(f"KUCOIN - Позиция {base_currency}: {ton_position['total']} (заем: {ton_position['liability']})")


def get_symbol_info(symbol):
    """Получить информацию о торговой паре"""
    url = f"{BASE_URL}/api/v1/symbols"
    r = requests.get(url).json()
    if r.get("code") != "200000":
        print(f"KUCOIN - ❌ Ошибка получения информации о символе: {r}")
        return None
    
    data = r.get("data", [])
    for item in data:
        if item['symbol'] == symbol:
            return {
                'symbol': symbol,
                'baseCurrency': item['baseCurrency'],
                'quoteCurrency': item['quoteCurrency'],
                'baseIncrement': float(item['baseIncrement']),
                'quoteIncrement': float(item['quoteIncrement']),
                'baseMinSize': float(item['baseMinSize']),
                'quoteMinSize': float(item['quoteMinSize'])
            }
    return None


def round_to_increment(amount, increment):
    """Округлить количество до минимального шага"""
    if increment == 0:
        return amount
    
    # Находим количество знаков после запятой для increment
    decimal_places = len(str(increment).split('.')[-1]) if '.' in str(increment) else 0
    
    # Округляем до ближайшего кратного increment
    rounded = round(amount / increment) * increment
    
    # Форматируем с правильным количеством знаков
    return round(rounded, decimal_places)


def format_amount_for_api(amount, increment):
    """Форматировать количество для API с правильным количеством знаков"""
    if increment == 0:
        return str(amount)
    
    # Находим количество знаков после запятой для increment
    decimal_places = len(str(increment).split('.')[-1]) if '.' in str(increment) else 0
    
    # Округляем и форматируем
    rounded = round(amount / increment) * increment
    formatted = round(rounded, decimal_places)
    
    # Преобразуем в строку с правильным количеством знаков
    return f"{formatted:.{decimal_places}f}".rstrip('0').rstrip('.')


def main():
    # Получаем информацию о торговой паре
    symbol_info = get_symbol_info(symbol)
    if not symbol_info:
        print("KUCOIN - ❌ Не удалось получить информацию о торговой паре")
        sys.exit(1)
    
    # Получаем количество монет через аргумент командной строки
    filled_amount = float(sys.argv[3]) if len(sys.argv) > 3 else None
    
    # Получаем текущие цены
    prices = get_price(symbol)
    usdt_available = get_usdt_balance()
    usdt_to_use = min(usdt_available, deposit_limit)
    
    if usdt_to_use <= 0:
        print("KUCOIN - ❌ Недостаточно USDT для торговли")
        sys.exit(1)
    
    if filled_amount and filled_amount > 0:
        base_amount = filled_amount
    else:
        base_amount = usdt_to_use / prices['bid']
        base_amount = round_to_increment(base_amount, symbol_info['baseIncrement'])
    
    # Проверяем минимальный размер
    if base_amount < symbol_info['baseMinSize']:
        print(f"KUCOIN - ❌ Количество {base_amount} меньше минимального {symbol_info['baseMinSize']}")
        sys.exit(1)
    
    # Проверяем минимальный размер в USDT
    order_value = base_amount * prices['bid']
    if order_value < symbol_info['quoteMinSize']:
        print(f"KUCOIN - ❌ Стоимость ордера {order_value:.2f} USDT меньше минимальной {symbol_info['quoteMinSize']} USDT")
        sys.exit(1)
    
    print(f"KUCOIN - 💰 Доступно {usdt_to_use} USDT — продаем {base_amount} {symbol.split('-')[0]}")
    
    result = place_margin_sell_order(symbol, base_amount, symbol_info)
    
    if result.get("code") == "200000":
        print(f"KUCOIN - ✅ Ордер выполнен: {base_amount} {symbol.split('-')[0]}")
        
        # Показываем обновленный статус
        time.sleep(2)  # Ждем обновления баланса
        print_margin_status()
        
    else:
        print(f"KUCOIN - ❌ Ошибка при создании ордера: {result}")
        print("KUCOIN - ❌ Уменьшите сумму ордера или проверьте баланс")
        sys.exit(1)


if __name__ == "__main__":
    main()
