import ccxt
import sys
import os
from dotenv import load_dotenv
import time

load_dotenv()

import sys
sys.stdout.reconfigure(encoding='utf-8')

exchange = ccxt.mexc({
    'apiKey': os.getenv('MEXC_KEY'),
    'secret': os.getenv('MEXC_SECRET'),
})

try:
    symbol = sys.argv[1]
    deposit = int(sys.argv[2])
    # symbol = 'XAR/USDT'
    # deposit = 10
    if deposit <= 0 or '/' not in symbol:
        raise ValueError
except:
    print("❌ MEXC - Ошибка: символ или депозит не указаны или некорректны")
    sys.exit(1) 

base, quote = symbol.split('/')

def retry_call(func, *args, retries=3, delay=2, **kwargs):
    for i in range(retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f"Ретрай {i+1}/{retries}: {e}")
            time.sleep(delay)
    raise Exception(f"Не удалось выполнить {func.__name__} после {retries} попыток")

markets = retry_call(exchange.load_markets)
if symbol not in markets:
    print(f"❌ MEXC - Ошибка: пара {symbol} не поддерживается на MEXC")
    sys.exit(1)

balance = retry_call(exchange.fetch_balance)
usdt_available = min(deposit, balance.get(quote, {}).get('free', 0))
if usdt_available <= 0:
    print(f"MEXC - ❌ Недостаточно {quote}: {usdt_available}")
    sys.exit(1)

ticker = retry_call(exchange.fetch_ticker, symbol)
price = ticker.get('ask') or ticker.get('last') or ticker.get('bid')
if not price:
    print(f"MEXC - ❌ Не удалось получить цену для {symbol}")
    sys.exit(1)

base_available = usdt_available / price
market = markets[symbol]
min_amount = market.get('limits', {}).get('amount', {}).get('min', 0)
precision = int(market.get('precision', {}).get('amount', 6))
base_available = round(base_available, precision)

if base_available < min_amount:
    print(f"MEXC - ❌ Объём {base_available} {base} ниже минимального ({min_amount})")
    sys.exit(1)

print(f"MEXC - Доступно {usdt_available} {quote} — покупаем {base_available} {base}")

# Получаем стакан
orderbook = retry_call(exchange.fetch_order_book, symbol)
asks = orderbook.get('asks', [])

# Проверка ликвидности
remaining = usdt_available
liquidity = 0
for price_, volume in asks:
    cost = price_ * volume
    if remaining <= 0:
        break
    if cost <= remaining:
        liquidity += cost
        remaining -= cost
    else:
        liquidity += remaining
        remaining = 0

if liquidity < usdt_available:
    print(f"MEXC - ❌ Не хватает ликвидности для покупки на {usdt_available} {quote}")
    sys.exit(1)

try:
    order = retry_call(exchange.create_market_buy_order, symbol=symbol, amount=base_available)
    # Получаем детали ордера
    order_details = retry_call(exchange.fetch_order, order['id'], symbol)
    filled = order_details.get('filled')
    cost = order_details.get('cost')
    if not filled or not cost:
        print("MEXC - ❌ Сделка не исполнена — недостаточно ликвидности")
        sys.exit(1)
    print(f"MEXC - ✅ Куплено по рынку {order_details['filled']} {order_details['symbol'].replace('/', '')}")
    # Выводим количество для передачи в основной скрипт
    print(f"FILLED_AMOUNT:{order_details['filled']}")
except Exception as e:
    message = str(e)
    if "minimum transaction volume" in message:
        print(f"MEXC - Сделка отклонена: объём меньше минимального ({symbol}, {base_available} USDT)")
    else:
        print(f"MEXC - ❌ Ошибка при создании ордера: {e.__class__.__name__}: {message}")
    sys.exit(1)