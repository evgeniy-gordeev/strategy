import ccxt
import sys
import os
from dotenv import load_dotenv

load_dotenv()

exchange = ccxt.kucoin({
    'apiKey': os.getenv('KUCOIN_KEY'),
    'secret': os.getenv('KUCOIN_SECRET'),
    'password': os.getenv('KUCOIN_PASSWORD'),
    'options': {
        'defaultType': 'margin'
    }
})

try:
    symbol = 'TON/USDT'
    deposit = 20
    if deposit <= 0 or '/' not in symbol:
        raise ValueError
except:
    print("❌ KUCOIN - Ошибка: символ или депозит не указаны или некорректны")
    sys.exit(1)

base, quote = symbol.split('/')

markets = exchange.load_markets()
if symbol not in markets:
    print(f"❌ KUCOIN - Ошибка: пара {symbol} не поддерживается на KUCOIN")
    sys.exit(1)

balance = exchange.fetch_balance({'type': 'margin'})
usdt_available = min(deposit, balance.get(quote, {}).get('free', 0))
if usdt_available <= 0:
    print(f"KUCOIN - ❌ Недостаточно {quote} в cross margin: {usdt_available}")
    sys.exit(1)

ticker = exchange.fetch_ticker(symbol)
price = ticker.get('bid') or ticker.get('last') or ticker.get('ask')
if not price:
    print(f"KUCOIN - ❌ Не удалось получить цену для {symbol}")
    sys.exit(1)

market = markets[symbol]
precision = int(market.get('precision', {}).get('amount', 6))
base_amount = round(usdt_available / price, precision)

min_amount = market.get('limits', {}).get('amount', {}).get('min', 0)
if base_amount < min_amount:
    print(f"KUCOIN - ❌ Объём {base_amount} {base} меньше минимального {min_amount}")
    sys.exit(1)

print(f"KUCOIN - 💰 Пробуем продать {base_amount} {base} с автозаёмом под {usdt_available} {quote}")

try:
    order = exchange.create_market_sell_order(
        symbol=symbol,
        amount=base_amount,
        params={
            'type': 'margin',
            'autoBorrow': True
        }
    )
    print(order)
    print(f"KUCOIN - ✅ Продано {order['amount']} {order['symbol'].replace('/', '')}")
except Exception as e:
    message = str(e)
    if "minimum transaction volume" in message:
        print(f"KUCOIN - ⚠️ Сделка отклонена: объём меньше минимального ({symbol}, {base_amount})")
    else:
        print(f"KUCOIN - ❌ Ошибка при создании ордера: {e.__class__.__name__}: {message}")