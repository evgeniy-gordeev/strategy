import time
import base64
import hmac
import hashlib
import requests
import os
import json
from dotenv import load_dotenv
from datetime import datetime

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
        return None
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
        return None
    return r['data']


def get_margin_position(currency):
    """Получить текущую маржинальную позицию для валюты"""
    account_data = get_margin_account()
    if not account_data:
        return None
    
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


def calculate_margin_level():
    """Рассчитать уровень маржи"""
    account_data = get_margin_account()
    if not account_data:
        return None
    
    total_asset_of_quote_currency = float(account_data.get('totalAssetOfQuoteCurrency', 0))
    total_liability_of_quote_currency = float(account_data.get('totalLiabilityOfQuoteCurrency', 0))
    
    if total_liability_of_quote_currency == 0:
        return float('inf')  # Нет долгов
    
    margin_level = total_asset_of_quote_currency / total_liability_of_quote_currency
    return margin_level


def get_margin_risk_info():
    """Получить информацию о рисках маржинальной торговли"""
    account_data = get_margin_account()
    if not account_data:
        return None
    
    return {
        'debtRatio': float(account_data.get('debtRatio', 0)),
        'totalAssetOfQuoteCurrency': float(account_data.get('totalAssetOfQuoteCurrency', 0)),
        'totalLiabilityOfQuoteCurrency': float(account_data.get('totalLiabilityOfQuoteCurrency', 0)),
        'marginLevel': calculate_margin_level()
    }


def print_detailed_status():
    """Показать детальный статус маржинального аккаунта"""
    print(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # Получаем цены
    prices = get_price(symbol)
    if not prices:
        return
    
    print(f"💱 Цена {symbol}:")
    print(f"   Bid: {prices['bid']:.6f} USDT")
    print(f"   Ask: {prices['ask']:.6f} USDT")
    print(f"   Спред: {(prices['ask'] - prices['bid']):.6f} USDT ({((prices['ask'] - prices['bid']) / prices['bid'] * 100):.3f}%)")
    print()
    
    # Получаем информацию о рисках
    risk_info = get_margin_risk_info()
    if risk_info:
        print("⚖️  Информация о марже:")
        print(f"   Общие активы: {risk_info['totalAssetOfQuoteCurrency']:.2f} USDT")
        print(f"   Общие долги: {risk_info['totalLiabilityOfQuoteCurrency']:.2f} USDT")
        print(f"   Уровень маржи: {risk_info['marginLevel']:.2f}")
        print(f"   Коэффициент долга: {risk_info['debtRatio']:.4f}")
        
        # Предупреждения о рисках
        if risk_info['marginLevel'] < 1.5:
            print("🚨 КРИТИЧЕСКИЙ РИСК! Уровень маржи очень низкий!")
        elif risk_info['marginLevel'] < 2.0:
            print("⚠️  ВЫСОКИЙ РИСК! Уровень маржи низкий!")
        elif risk_info['marginLevel'] < 3.0:
            print("⚡ Средний риск. Следите за позицией.")
        else:
            print("✅ Безопасный уровень маржи.")
        print()
    
    # Получаем позицию по TON
    base_currency = symbol.split('-')[0]  # TON
    ton_position = get_margin_position(base_currency)
    if ton_position and (ton_position['total'] != 0 or ton_position['liability'] != 0):
        print(f"🪙 Позиция {base_currency}:")
        print(f"   Всего: {ton_position['total']:.6f}")
        print(f"   Доступно: {ton_position['available']:.6f}")
        print(f"   Заем: {ton_position['liability']:.6f}")
        print(f"   Проценты: {ton_position['interest']:.6f}")
        
        if ton_position['liability'] > 0:
            total_debt = ton_position['liability'] + ton_position['interest']
            debt_value = total_debt * prices['ask']
            print(f"   💸 Общий долг: {total_debt:.6f} {base_currency} (~{debt_value:.2f} USDT)")
            
            # Рассчитываем P&L для шорт-позиции
            # Предполагаем, что средняя цена входа была близка к текущей bid цене
            # (это приблизительный расчет, для точного нужна история сделок)
            estimated_entry_price = prices['bid']  # Приблизительная цена входа
            current_exit_price = prices['ask']  # Цена выхода (покупки для закрытия)
            
            pnl_per_unit = estimated_entry_price - current_exit_price
            estimated_pnl = pnl_per_unit * ton_position['liability']
            
            print(f"   📊 Приблизительный P&L: {estimated_pnl:.2f} USDT")
            if estimated_pnl > 0:
                print(f"   📈 Позиция в прибыли")
            else:
                print(f"   📉 Позиция в убытке")
        print()
    
    # Получаем позицию по USDT
    usdt_position = get_margin_position('USDT')
    if usdt_position and (usdt_position['total'] != 0 or usdt_position['liability'] != 0):
        print(f"💰 Позиция USDT:")
        print(f"   Всего: {usdt_position['total']:.2f}")
        print(f"   Доступно: {usdt_position['available']:.2f}")
        print(f"   Заем: {usdt_position['liability']:.2f}")
        print(f"   Проценты: {usdt_position['interest']:.6f}")
        print()


def monitor_continuous(interval=30):
    """Непрерывный мониторинг с заданным интервалом"""
    print("🔄 Запуск непрерывного мониторинга...")
    print(f"⏱️  Интервал обновления: {interval} секунд")
    print("Нажмите Ctrl+C для остановки")
    print()
    
    try:
        while True:
            print_detailed_status()
            print(f"⏳ Следующее обновление через {interval} секунд...")
            print("=" * 60)
            print()
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n👋 Мониторинг остановлен пользователем")


def main():
    print("📊 Мониторинг маржинальных позиций KuCoin")
    print("=" * 50)
    print()
    
    # Показать текущий статус
    print_detailed_status()
    
    # Спросить о непрерывном мониторинге
    choice = input("Запустить непрерывный мониторинг? (y/N): ")
    if choice.lower() == 'y':
        interval_input = input("Интервал в секундах (по умолчанию 30): ")
        try:
            interval = int(interval_input) if interval_input else 30
        except ValueError:
            interval = 30
        monitor_continuous(interval)


if __name__ == "__main__":
    main() 