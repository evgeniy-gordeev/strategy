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

symbol = 'TON-USDT'
BASE_URL = 'https://api.kucoin.com'


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
        print(f"❌ Ошибка получения цены: {r}")
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
        print(f"❌ Ошибка получения маржинального аккаунта: {r}")
        sys.exit(1)
    return r['data']


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


def place_margin_buy_order(symbol, base_amount, symbol_info):
    """Разместить маржинальный ордер на покупку (закрыть шорт)"""
    endpoint = '/api/v1/margin/order'
    url = BASE_URL + endpoint
    
    # Форматируем количество правильно для API
    formatted_amount = format_amount_for_api(base_amount, symbol_info['baseIncrement'])
    
    body = {
        "symbol": symbol,
        "side": "buy",
        "type": "market",
        "size": formatted_amount,
        "autoBorrow": True,
        "clientOid": str(uuid.uuid4())
    }
    body_str = json.dumps(body)
    headers = sign("POST", endpoint, body_str)
    response = requests.post(url, headers=headers, data=body_str)
    return response.json()


def repay_margin_debt(currency, size):
    """Погасить маржинальный долг"""
    endpoint = '/api/v1/margin/repay/single'
    url = BASE_URL + endpoint
    body = {
        "currency": currency,
        "size": str(size)
    }
    body_str = json.dumps(body)
    headers = sign("POST", endpoint, body_str)
    response = requests.post(url, headers=headers, data=body_str)
    return response.json()


def print_margin_status():
    """Показать текущий статус маржинального аккаунта"""
    print("📊 Статус маржинального аккаунта:")
    
    # Получаем цены
    prices = get_price(symbol)
    print(f"💱 Цена {symbol}: Bid={prices['bid']}, Ask={prices['ask']}")
    
    # Получаем позицию по TON
    base_currency = symbol.split('-')[0]  # TON
    ton_position = get_margin_position(base_currency)
    if ton_position:
        print(f"🪙 Позиция {base_currency}:")
        print(f"   Всего: {ton_position['total']}")
        print(f"   Доступно: {ton_position['available']}")
        print(f"   Заем: {ton_position['liability']}")
        print(f"   Проценты: {ton_position['interest']}")
        
        if ton_position['liability'] > 0:
            print(f"⚠️  У вас есть долг по {base_currency}: {ton_position['liability']}")
    else:
        print(f"ℹ️  Нет позиции по {base_currency}")
    
    # Получаем позицию по USDT
    usdt_position = get_margin_position('USDT')
    if usdt_position:
        print(f"💰 Позиция USDT:")
        print(f"   Всего: {usdt_position['total']}")
        print(f"   Доступно: {usdt_position['available']}")
        print(f"   Заем: {usdt_position['liability']}")
        print(f"   Проценты: {usdt_position['interest']}")


def get_symbol_info(symbol):
    """Получить информацию о торговой паре"""
    url = f"{BASE_URL}/api/v1/symbols"
    r = requests.get(url).json()
    if r.get("code") != "200000":
        print(f"❌ Ошибка получения информации о символе: {r}")
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


def check_usdt_balance():
    """Проверить баланс USDT"""
    usdt_position = get_margin_position('USDT')
    if usdt_position:
        return usdt_position['available']
    return 0


def calculate_required_usdt(ton_debt, price):
    """Рассчитать необходимое количество USDT для погашения долга"""
    # Добавляем небольшой запас для комиссий (1%)
    required_usdt = ton_debt * price * 1.01
    return required_usdt


def main():
    print("🔄 Закрытие маржинальных позиций KuCoin")
    print("=" * 45)
    
    # Получаем информацию о торговой паре
    symbol_info = get_symbol_info(symbol)
    if not symbol_info:
        print("❌ Не удалось получить информацию о торговой паре")
        sys.exit(1)
    
    # Показываем текущий статус
    print_margin_status()
    print()
    
    base_currency = symbol.split('-')[0]  # TON
    ton_position = get_margin_position(base_currency)
    
    if not ton_position or ton_position['liability'] <= 0:
        print("ℹ️  Нет открытых шорт-позиций для закрытия")
        return
    
    # Получаем текущие цены
    prices = get_price(symbol)
    debt_amount = ton_position['liability']
    total_debt_with_interest = debt_amount + ton_position['interest']
    
    # Проверяем баланс USDT
    usdt_balance = check_usdt_balance()
    required_usdt = calculate_required_usdt(total_debt_with_interest, prices['ask'])
    
    print(f"💰 Баланс USDT: {usdt_balance:.2f}")
    print(f"💸 Требуется USDT: {required_usdt:.2f}")
    
    if usdt_balance < required_usdt:
        print(f"❌ Недостаточно USDT для погашения долга!")
        print(f"   Нужно: {required_usdt:.2f} USDT")
        print(f"   Доступно: {usdt_balance:.2f} USDT")
        print(f"   Не хватает: {required_usdt - usdt_balance:.2f} USDT")
        return
    
    # Округляем до правильного шага
    total_debt_with_interest = round_to_increment(total_debt_with_interest, symbol_info['baseIncrement'])
    
    print(f"📋 Информация о долге:")
    print(f"   Основной долг: {debt_amount} {base_currency}")
    print(f"   Проценты: {ton_position['interest']} {base_currency}")
    print(f"   Всего к погашению: {total_debt_with_interest} {base_currency}")
    print(f"   Стоимость закрытия: ~{total_debt_with_interest * prices['ask']:.2f} USDT")
    print()
    
    print(f"💰 Автоматически покупаю {total_debt_with_interest} {base_currency} для закрытия позиции...")
    
    # Покупаем TON для закрытия шорт-позиции
    result = place_margin_buy_order(symbol, total_debt_with_interest, symbol_info)
    
    if result.get("code") == "200000":
        print(f"✅ Ордер на покупку создан!")
        print(f"   ID ордера: {result['data']['orderId']}")
        print()
        
        # Ждем исполнения ордера
        print("⏳ Ожидаю исполнения ордера...")
        time.sleep(5)
        
        # Показываем обновленный статус
        print("📊 Обновленный статус:")
        print_margin_status()
        
        # Проверяем, нужно ли погасить оставшийся долг
        updated_position = get_margin_position(base_currency)
        if updated_position and updated_position['liability'] > 0.000001:  # Учитываем погрешности
            print(f"\n💳 Погашаю оставшийся долг: {updated_position['liability']} {base_currency}")
            repay_result = repay_margin_debt(base_currency, updated_position['liability'])
            if repay_result.get("code") == "200000":
                print("✅ Долг погашен!")
            else:
                print(f"❌ Ошибка погашения долга: {repay_result}")
        
        # Финальная проверка статуса
        print("\n📊 Финальный статус после закрытия позиций:")
        print_margin_status()
        
    else:
        print(f"❌ Ошибка при создании ордера: {result}")
        print(f"   Детали ошибки: {result.get('msg', 'Неизвестная ошибка')}")
        print(f"   Попробуйте проверить баланс или размер позиции")


if __name__ == "__main__":
    main() 