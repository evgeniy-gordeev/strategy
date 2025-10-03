import ccxt
import sys
import os
from dotenv import load_dotenv
import logging

# Настройка логирования
# logging.basicConfig(
#     filename='./logs/xyz415.log',
#     level=print,
#     format='%(asctime)s - %(levelname)s - %(message)s'
# )

import sys
sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

# Проверка переменных окружения
bitget_key = os.getenv('BITGET_KEY')
bitget_secret = os.getenv('BITGET_SECRET') 
bitget_password = os.getenv('BITGET_PASSWORD')

if not all([bitget_key, bitget_secret, bitget_password]):
    print("❌ BITGET - Ошибка: не найдены переменные окружения BITGET_KEY, BITGET_SECRET, BITGET_PASSWORD")
    sys.exit(1)

exchange = ccxt.bitget({
    'apiKey': bitget_key,
    'secret': bitget_secret,
    'password': bitget_password,
})


try:
    symbol = sys.argv[1]
    deposit = int(sys.argv[2])
    if deposit <= 0 or '/' not in symbol:
        raise ValueError
except (IndexError, ValueError) as e:
    print(f"❌ BITGET - Ошибка: символ или депозит не указаны или некорректны. Использование: python bitget.py SYMBOL DEPOSIT")
    print(f"Пример: python bitget.py REX/USDT 10")
    sys.exit(1)

base, quote = symbol.split('/')

try:
    markets = exchange.load_markets()
    if symbol not in markets:
        print(f"❌ BITGET - Ошибка: пара {symbol} не поддерживается на BITGET")
        sys.exit(1)
except Exception as e:
    print(f"❌ BITGET - Ошибка при загрузке рынков: {e}")
    sys.exit(1)

try:
    balance = exchange.fetch_balance()
    usdt_available = min(deposit, balance.get(quote, {}).get('free', 0))
    if usdt_available <= 0:
        print(f"BITGET - ❌ Недостаточно {quote}: {usdt_available}")
        sys.exit(1)
except Exception as e:
    print(f"❌ BITGET - Ошибка при получении баланса: {e}")
    sys.exit(1)

try:
    ticker = exchange.fetch_ticker(symbol)
    price = ticker.get('ask') or ticker.get('last') or ticker.get('bid')
    if not price:
        print(f"BITGET - ❌ Не удалось получить цену для {symbol}")
        sys.exit(1)
except Exception as e:
    print(f"❌ BITGET - Ошибка при получении цены: {e}")
    sys.exit(1)

base_available = usdt_available / price
market = markets[symbol]
min_amount = market.get('limits', {}).get('amount', {}).get('min', 0)
precision = int(market.get('precision', {}).get('amount', 6))
base_available = round(base_available, precision)

if base_available < min_amount:
    print(f"BITGET - ❌ Недостаточно средств для покупки минимального количества {base}")
    sys.exit(1)

print(f"BITGET - Доступно {usdt_available} {quote} — покупаем {base_available} {base}")

try:
    print(f"BITGET - Подготовка к покупке {base_available} {base} за {usdt_available} {quote}")
    exchange.options['createMarketBuyOrderRequiresPrice'] = False

    order = exchange.create_market_buy_order(
        symbol=symbol,
        amount=usdt_available,
        params={'createMarketBuyOrderRequiresPrice': False}
    )
    
    print(f"BITGET - Ордер создан: {order['id']}")
    detailed_order = exchange.fetch_order(order['id'], symbol)
    print(f"BITGET - ✅ Куплено: {detailed_order['filled']} {base} по цене {detailed_order['average']} USDT")
    print(f"FILLED_AMOUNT:{detailed_order['filled']}")

except Exception as e:
    message = str(e)
    print(f"BITGET - ❌ Детальная ошибка: {e.__class__.__name__}: {message}")
    
    if "minimum transaction volume" in message:
        print(f"BITGET - Сделка отклонена: объём меньше минимального ({symbol}, {base_available} USDT)")
    else:
        print(f"BITGET - ❌ Ошибка при создании ордера: {e.__class__.__name__}: {message}")
    
    # Выводим FILLED_AMOUNT:0 даже при ошибке
    print("FILLED_AMOUNT:0")
    sys.exit(1)
