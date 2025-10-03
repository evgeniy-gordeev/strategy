import ccxt
import sys
import os
from dotenv import load_dotenv

load_dotenv()

exchange = ccxt.okx({
    'apiKey': os.getenv('OKX_KEY'),
    'secret': os.getenv('OKX_SECRET'),
    'password': os.getenv('OKX_PASSWORD'),
})

try:
    symbol = sys.argv[1]
    deposit = int(sys.argv[2])
    if deposit <= 0 or '/' not in symbol:
        raise ValueError
except:
    print("❌ OKX - Ошибка: символ или депозит не указаны или некорректны")
    sys.exit(1)

base, quote = symbol.split('/')

import sys
sys.stdout.reconfigure(encoding='utf-8')

markets = exchange.load_markets()
if symbol not in markets:
    print(f"❌ OKX - Ошибка: пара {symbol} не поддерживается на OKX")
    sys.exit(1)

balance = exchange.fetch_balance()
usdt_available = min(deposit, balance.get(quote, {}).get('free', 0))
if usdt_available <= 0:
    print(f"OKX - ❌ Недостаточно {quote}: {usdt_available}")
    sys.exit(1)

ticker = exchange.fetch_ticker(symbol)
price = ticker.get('ask') or ticker.get('last') or ticker.get('bid')
if not price:
    print(f"OKX - ❌ Не удалось получить цену для {symbol}")
    sys.exit(1)

base_available = usdt_available / price
market = markets[symbol]
min_amount = market.get('limits', {}).get('amount', {}).get('min', 0)
precision = int(market.get('precision', {}).get('amount', 6))
base_available = round(base_available, precision)

if base_available < min_amount:
    print(f"OKX - ❌ Недостаточно средств для покупки минимального количества {base}")
    sys.exit(1)

print(f"OKX - Доступно {usdt_available} {quote} — покупаем {base_available} {base}")

try:
    order = exchange.create_market_buy_order(
        symbol=symbol,
        amount=base_available
    )
    detailed_order = exchange.fetch_order(order['id'], symbol)
    print(f"OKX - ✅ Куплено: {detailed_order['filled']} {base} по цене {detailed_order['average']} USDT")
    print(f"FILLED_AMOUNT:{detailed_order['filled']}")
except Exception as e:
    message = str(e)
    if "minimum transaction volume" in message:
        print(f"OKX - Сделка отклонена: объём меньше минимального ({symbol}, {base_available} USDT)")
    else:
        print(f"OKX - ❌ Ошибка при создании ордера: {e.__class__.__name__}: {message}")
    sys.exit(1)
