import asyncio
import subprocess
from telethon import TelegramClient, events
import os
from dotenv import load_dotenv
import time
import ccxt
import requests
import re
from src.utils import extract_symbol, extract_exchange, is_borrowable_gate
from datetime import datetime, timedelta
from src.utils import calculate_average_buy_price, calculate_average_sell_price
from typing import Dict, List, Optional, Tuple

load_dotenv()

class ArbitrageBot:
    def __init__(self):
        self.api_id = os.getenv('APP_ID')
        self.api_hash = os.getenv('APP_HASH')
        self.deposit = 10  # депозит в долларах
        self.use_validation = True  # True - с проверкой, False - без проверки
        self.simultaneously = True  # True - одновременно, False - нет
        self.last_signal_time = None
        self.min_interval = timedelta(minutes=1)
        
        # Rate limiting для API запросов
        self.api_call_times = {}
        self.max_api_calls_per_minute = 60
        
        # Инициализация клиента Telegram
        self.client = TelegramClient(
            'arbitrage_session245',
            self.api_id,
            self.api_hash,
            auto_reconnect=True,
            connection_retries=None,
            request_retries=1,
            system_version='4.16.30-vxCUSTOM'
        )
        
        # Кэш для бирж и их рынков
        self.exchanges = {}
        self.markets_cache = {}
        self.markets_cache_time = None
        self.cache_duration = timedelta(minutes=5)
        
        # Конфигурация бирж
        self.exchange_configs = {
            'mexc': {
                'class': ccxt.mexc,
                'params': {
                    'apiKey': os.getenv('MEXC_KEY'),
                    'secret': os.getenv('MEXC_SECRET'),
                }
            },
            'bitget': {
                'class': ccxt.bitget,
                'params': {
                    'apiKey': os.getenv('BITGET_KEY'),
                    'secret': os.getenv('BITGET_SECRET'),
                    'password': os.getenv('BITGET_PASSWORD'),
                }
            },
            'okx': {
                'class': ccxt.okx,
                'params': {
                    'apiKey': os.getenv('OKX_KEY'),
                    'secret': os.getenv('OKX_SECRET'),
                    'password': os.getenv('OKX_PASSWORD'),
                }
            },
            'gate': {
                'class': ccxt.gate,
                'params': {
                    'apiKey': os.getenv('GATE_KEY'),
                    'secret': os.getenv('GATE_SECRET'),
                }
            },
            'kucoin': {
                'class': ccxt.kucoin,
                'params': {
                    'apiKey': os.getenv('KUCOIN_KEY'),
                    'secret': os.getenv('KUCOIN_SECRET'),
                    'password': os.getenv('KUCOIN_PASSWORD'),
                }
            }
        }
        
        # Маппинг бирж для покупки и продажи
        self.buyer_exchanges = ['bitget', 'okx', 'mexc']
        self.seller_exchanges = ['gate', 'kucoin']
        
        print(f"🔍 Запуск бота с депозитом ${self.deposit} | "
              f"Проверка {'включена' if self.use_validation else 'выключена'} | "
              f"{'Одновременные сделки' if self.simultaneously else 'Последовательные сделки'}")

    def get_exchange(self, exchange_name: str):
        """Получить или создать экземпляр биржи"""
        if exchange_name not in self.exchanges:
            if exchange_name in self.exchange_configs:
                config = self.exchange_configs[exchange_name]
                self.exchanges[exchange_name] = config['class'](config['params'])
            else:
                raise ValueError(f"Неизвестная биржа: {exchange_name}")
        return self.exchanges[exchange_name]

    def get_markets(self, exchange_name: str) -> List[str]:
        """Получить список доступных символов для биржи с кэшированием"""
        current_time = datetime.now()
        
        # Проверяем, нужно ли обновить кэш
        if (self.markets_cache_time is None or 
            current_time - self.markets_cache_time > self.cache_duration):
            self.markets_cache = {}
            self.markets_cache_time = current_time
        
        if exchange_name not in self.markets_cache:
            try:
                exchange = self.get_exchange(exchange_name)
                markets = exchange.load_markets()
                self.markets_cache[exchange_name] = list(markets.keys())
                print(f"Загружены рынки для {exchange_name}: {len(self.markets_cache[exchange_name])} символов")
            except Exception as e:
                print(f"Ошибка загрузки рынков для {exchange_name}: {e}")
                self.markets_cache[exchange_name] = []
        
        return self.markets_cache[exchange_name]

    def calculate_prices(self, symbol: str, buy_exchange: str, sell_exchange: str) -> Tuple[Optional[float], Optional[float]]:
        """Рассчитать цены покупки и продажи"""
        buy_price = None
        sell_price = None
        
        try:
            # Расчет цены покупки
            if buy_exchange in self.buyer_exchanges:
                exchange = self.get_exchange(buy_exchange)
                buy_price = calculate_average_buy_price(self.deposit, symbol, exchange)
                print(f"Цена покупки на {buy_exchange}: {buy_price}")
            
            # Расчет цены продажи
            if sell_exchange in self.seller_exchanges:
                exchange = self.get_exchange(sell_exchange)
                sell_price = calculate_average_sell_price(self.deposit, symbol, exchange)
                print(f"Цена продажи на {sell_exchange}: {sell_price}")
                
        except Exception as e:
            print(f"Ошибка расчета цен: {e}")
        
        return buy_price, sell_price

    def _validate_api_keys(self, buy_exchange: str, sell_exchange: str) -> bool:
        """Проверить наличие и валидность API ключей"""
        exchanges_to_check = [buy_exchange, sell_exchange]
        
        for exchange_name in exchanges_to_check:
            if exchange_name not in self.exchange_configs:
                print(f"❌ Неизвестная биржа: {exchange_name}")
                return False
            
            config = self.exchange_configs[exchange_name]
            required_keys = ['apiKey', 'secret']
            
            # Проверяем наличие обязательных ключей
            for key in required_keys:
                if not config['params'].get(key):
                    print(f"❌ Отсутствует {key} для {exchange_name.upper()}")
                    return False
            
            # Дополнительная проверка для бирж с паролем
            if exchange_name in ['bitget', 'okx', 'kucoin']:
                if not config['params'].get('password'):
                    print(f"❌ Отсутствует password для {exchange_name.upper()}")
                    return False
        
        print("✅ API ключи валидны")
        return True

    def _sanitize_log_output(self, output: str) -> str:
        """Очистить логи от чувствительных данных"""
        if not output:
            return output
        
        # Список паттернов для маскировки
        sensitive_patterns = [
            (r'api[_-]?key["\']?\s*[:=]\s*["\']?([^"\'\s]+)', r'api_key="***"'),
            (r'secret["\']?\s*[:=]\s*["\']?([^"\'\s]+)', r'secret="***"'),
            (r'password["\']?\s*[:=]\s*["\']?([^"\'\s]+)', r'password="***"'),
            (r'token["\']?\s*[:=]\s*["\']?([^"\'\s]+)', r'token="***"'),
        ]
        
        sanitized = output
        for pattern, replacement in sensitive_patterns:
            sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)
        
        return sanitized

    def _check_rate_limit(self, exchange_name: str) -> bool:
        """Проверить rate limiting для API"""
        current_time = datetime.now()
        minute_ago = current_time - timedelta(minutes=1)
        
        # Очищаем старые записи
        if exchange_name in self.api_call_times:
            self.api_call_times[exchange_name] = [
                call_time for call_time in self.api_call_times[exchange_name]
                if call_time > minute_ago
            ]
        else:
            self.api_call_times[exchange_name] = []
        
        # Проверяем лимит
        if len(self.api_call_times[exchange_name]) >= self.max_api_calls_per_minute:
            print(f"⚠️ Rate limit превышен для {exchange_name}")
            return False
        
        # Добавляем текущий вызов
        self.api_call_times[exchange_name].append(current_time)
        return True

    def check_margin_availability(self, symbol: str, sell_exchange: str = None) -> bool:
        """Проверить доступность маржинальной торговли"""
        try:
            base, quote = symbol.split("/")
            
            # Проверка для Gate.io
            if sell_exchange == 'gate':
                return is_borrowable_gate(f"{base}_USDT", "https://api.gateio.ws", "/api/v4")
            
            # Проверка для KuCoin
            elif sell_exchange == 'kucoin':
                url = 'https://api.kucoin.com/api/v1/margin/config'
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                data = response.json()
                
                if data.get("code") != "200000":
                    print(f"Ошибка получения конфигурации маржи KuCoin: {data}")
                    return False
                
                currency_list = data.get("data", {}).get("currencyList", [])
                return base in currency_list
            
            # По умолчанию проверяем Gate.io (для обратной совместимости)
            else:
                return is_borrowable_gate(f"{base}_USDT", "https://api.gateio.ws", "/api/v4")
                
        except Exception as e:
            print(f"Ошибка проверки маржинальной торговли для {sell_exchange or 'gate'}: {e}")
            return False

    def validate_arbitrage(self, symbol: str, buy_exchange: str, sell_exchange: str, 
                          buy_price: float, sell_price: float) -> bool:
        """Проверить валидность арбитражной сделки"""
        print('🚀 Начало проверок...')
        
        # Проверка 0: Валидация API ключей
        if not self._validate_api_keys(buy_exchange, sell_exchange):
            return False
        
        # Проверка 1: Доступность символа на биржах
        if buy_exchange not in self.buyer_exchanges:
            print('❌ Указаны неверные биржи для покупки')
            return False
            
        if sell_exchange not in self.seller_exchanges:
            print('❌ Указаны неверные биржи для продажи')
            return False
        
        buy_markets = self.get_markets(buy_exchange)
        sell_markets = self.get_markets(sell_exchange)
        
        if symbol not in buy_markets:
            print(f'❌ Символ не найден на бирже покупки: {buy_exchange.upper()}')
            return False
            
        if symbol not in sell_markets:
            print(f'❌ Символ не найден на бирже продажи: {sell_exchange.upper()}')
            return False
        
        # Проверка 2: Прибыльность сделки
        if buy_price is None or sell_price is None:
            print('❌ Не удалось получить цены')
            return False
            
        if buy_price >= sell_price:
            print('❌ Проверка 2 - Сделка отклонена: нет прибыли')
            return False
        
        # Проверка 3: Доступность маржинальной торговли
        if not self.check_margin_availability(symbol, sell_exchange):
            print('❌ Проверка 3 - Сделка отклонена: нет заемных средств')
            return False
        
        print(f'✅ Проверка 1 - символ доступен на {buy_exchange.upper()} и {sell_exchange.upper()}')
        print('✅ Проверка 2 - цена покупки ниже цены продажи')
        print('✅ Проверка 3 - маржинальная торговля доступна')
        return True

    def execute_trades(self, symbol: str, buy_exchange: str, sell_exchange: str):
        str_deposit = str(self.deposit)
        # Покупка
        filled_amount = self._run_trade_script(buy_exchange, symbol, str_deposit, "Покупка", wait=True)
        # Продажа с передачей количества купленных монет
        if filled_amount:
            self._run_trade_script(sell_exchange, symbol, str_deposit, "Продажа", wait=False, filled_amount=filled_amount)
        else:
            print("❌ Не удалось получить количество купленных монет")

    def _run_trade_script(self, exchange: str, symbol: str, deposit: str, 
                         operation: str, wait: bool = False, filled_amount: float = None):
        """Запустить торговый скрипт"""
        try:
            # Валидация параметров для предотвращения command injection
            if not re.match(r'^[a-z]+$', exchange):
                print(f"❌ Недопустимое имя биржи: {exchange}")
                return None
            
            if not re.match(r'^[A-Z0-9]+/[A-Z0-9]+$', symbol):
                print(f"❌ Недопустимый символ: {symbol}")
                return None
                
            if not re.match(r'^\d+$', deposit):
                print(f"❌ Недопустимый депозит: {deposit}")
                return None
            
            script_path = f'./src/{exchange}.py'
            print(f"🚀 {operation} - Запуск {exchange}.py...")
            
            cmd = ['python3', script_path, symbol, deposit]
            if filled_amount is not None:
                if not isinstance(filled_amount, (int, float)) or filled_amount < 0:
                    print(f"❌ Недопустимое количество: {filled_amount}")
                    return None
                cmd.append(str(filled_amount))
            
            # Безопасное выполнение с ограничениями
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                text=True,
                cwd=os.getcwd(),  # Ограничиваем рабочую директорию
                env=os.environ    # Передаем только безопасные переменные окружения
            )
            
            if wait:
                stdout, stderr = process.communicate()
                success = process.returncode == 0
                
                # Безопасное логирование (скрываем чувствительные данные)
                safe_stdout = self._sanitize_log_output(stdout)
                print(f"📋 {exchange}.py stdout:\n{safe_stdout}")
                if stderr:
                    safe_stderr = self._sanitize_log_output(stderr)
                    print(f"📋 {exchange}.py stderr:\n{safe_stderr}")
                print(f"📋 {exchange}.py return code: {process.returncode}")
                
                if not success:
                    print(f"⚠️ {exchange}.py завершился с ошибкой")
                    if stderr:
                        print(f"Ошибка: {stderr}")
                    return None
                
                # Извлекаем количество купленных монет из вывода
                for line in stdout.split('\n'):
                    if line.startswith('FILLED_AMOUNT:'):
                        try:
                            amount = float(line.split(':', 1)[1])
                            print(f"📊 Получено количество монет: {amount}")
                            return amount
                        except (ValueError, IndexError) as e:
                            print(f"⚠️ Не удалось извлечь количество монет из вывода: {e}")
                            print(f"⚠️ Проблемная строка: {line}")
                            return None
                
                print("⚠️ Количество монет не найдено в выводе")
                print("⚠️ Доступные строки вывода:")
                for i, line in enumerate(stdout.split('\n')):
                    if line.strip():
                        print(f"  {i}: {line}")
                return None
            else:
                return True
                
        except Exception as e:
            print(f"⚠️ Ошибка запуска {exchange}.py: {e}")
            return None

    async def handle_message(self, event):
        """Обработать входящее сообщение"""
        current_time = datetime.now()
        print("TELETHON - 📨 Новое сообщение от @ArbitrageSmartBot")
        
        # Проверка интервала между сигналами
        if (self.last_signal_time and 
            (current_time - self.last_signal_time) < self.min_interval):
            print(f"TELETHON - ⏳ Сигнал проигнорирован: слишком частые сообщения "
                  f"(интервал < {self.min_interval.seconds} сек)")
            return
        
        sender = await event.get_sender()
        
        if not (sender.bot and not event.fwd_from):
            print("TELETHON - ⏭️ Сообщение проигнорировано (не от бота)")
            return
        
        self.last_signal_time = current_time
        text = event.message.message
        
        # Извлечение данных из сообщения
        symbol = extract_symbol(text)
        buy_exchange, sell_exchange = extract_exchange(text)
        
        if not symbol:
            print("TELETHON - ❌ Символ не найден в сообщении")
            return
        
        print(f"💱 Найден символ: {symbol}")
        print(f"📊 Биржа покупки: {buy_exchange.upper()} → Биржа продажи: {sell_exchange.upper()}")
        
        # Расчет цен
        buy_price, sell_price = self.calculate_prices(symbol, buy_exchange, sell_exchange)
        
        # Выполнение сделок
        if self.use_validation:
            if self.validate_arbitrage(symbol, buy_exchange, sell_exchange, buy_price, sell_price):
                self.execute_trades(symbol, buy_exchange, sell_exchange)
        else:
            print('🚀 Запуск без проверок...')
            self.execute_trades(symbol, buy_exchange, sell_exchange)

    async def start(self):
        """Запустить бота"""
        @self.client.on(events.NewMessage(chats='ArbitrageSmartBot'))
        async def handler(event):
            await self.handle_message(event)
        
        await self.client.start()
        print("TELETHON - 🔍 Отслеживание сообщений от @ArbitrageSmartBot...")
        await self.client.run_until_disconnected()

def main():
    """Главная функция"""
    bot = ArbitrageBot()
    with bot.client:
        bot.client.loop.run_until_complete(bot.start())

if __name__ == "__main__":
    main()