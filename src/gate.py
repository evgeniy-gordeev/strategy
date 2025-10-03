# coding: utf-8

import requests
import time
import hashlib
import hmac
import json
import sys
import os
from dotenv import load_dotenv
from utils import gen_sign, get_balance, get_price, send_order, get_max_borrowable_gate, is_borrowable_gate

load_dotenv()

import sys
sys.stdout.reconfigure(encoding='utf-8')

symbol_raw = sys.argv[1] if len(sys.argv) > 1 else None
deposit = int(sys.argv[2]) if len(sys.argv) > 2 else None
filled_amount = float(sys.argv[3]) if len(sys.argv) > 3 else None


# Валидация входных данных
if not symbol_raw or "/" not in symbol_raw or deposit is None or deposit <= 0:
    print("❌ Ошибка: символ или депозит не указаны или некорректны")
    sys.exit(1)

# Дополнительная валидация символа
import re
if not re.match(r'^[A-Z0-9]+/[A-Z0-9]+$', symbol_raw):
    print("❌ Ошибка: некорректный формат символа")
    sys.exit(1)

# Валидация депозита
if deposit > 10000:  # Максимальный лимит
    print("❌ Ошибка: депозит превышает максимальный лимит")
    sys.exit(1)

symbol_api = symbol_raw.replace("/", "_")
base, quote = symbol_raw.split("/")

host = "https://api.gateio.ws"
prefix = "/api/v4"

api_key = os.getenv('GATE_KEY')
api_secret = os.getenv('GATE_SECRET')

available_usdt = min(deposit, get_balance(quote, host, prefix, api_key, api_secret))
if available_usdt <= 0:
    print(f"GATE - ❌ Недостаточно {quote}: {available_usdt}")
    sys.exit(1)

price = get_price(symbol_api, host, prefix)
if not price:
    print("GATE - ❌ Не удалось получить цену актива")
    sys.exit(1)

if filled_amount and filled_amount > 0:
    amount = filled_amount
else:
    amount = round(available_usdt / price, 6)

print(f"GATE - Доступно {available_usdt} {quote} USDT — продаем {amount} {base}")

# Проверяем доступность займа
if not is_borrowable_gate(symbol_api, host, prefix):
    print(f"GATE - ❌ Займ для {base} недоступен")
    sys.exit(1)

max_borrowable = get_max_borrowable_gate(symbol_api, host, prefix, api_key, api_secret)
print(f"GATE - Максимально доступный заем: {max_borrowable} {base}")

if amount > max_borrowable:
    print(f"GATE - ❌ Недостаточно заемных средств для {base}: {max_borrowable}")
    sys.exit(1)

try:
    order = send_order(symbol_api, host, prefix, api_key, api_secret, amount)
    if not order or 'amount' not in order:
        print(f"GATE - ❌ Недостаточно заемных средств для {base}")
        sys.exit(1)
    print(f"GATE - ✅ Ордер выполнен: {order['amount']} {order['currency_pair'].replace('/', '')}")
    # Выводим количество для передачи в основной скрипт
    print(f"FILLED_AMOUNT:{order['amount']}")
except Exception as e:
    if 'amount' in str(e):
        print(f"GATE - ❌ Недостаточно заемных средств для {base}")
        sys.exit(1)
    print(f"GATE - ❌ Ошибка: {str(e)}")
    if 'AUTO_BORROW_TOO_MUCH' in str(e):
        print("GATE - ❌ Уменьшите сумму ордера или проверьте лимиты маржинального займа")
        sys.exit(1)
