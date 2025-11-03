import os
import logging
import ccxt
import asyncio
from datetime import datetime, timedelta
from telegram import Bot
import time
from flask import Flask
import threading

# Создаем Flask приложение для Render
app = Flask(__name__)

@app.route('/')
def home():
    return "🚀 BTC Signal Bot is running! Check logs for signals."
    
@app.route('/health')
def health():
    """Эндпоинт для проверки работоспособности"""
    bot_status = "active" if (datetime.now() - bot_start_time).total_seconds() < 3600 else "possibly_stalled"
    
    return {
        "status": "ok", 
        "time": datetime.now().isoformat(),
        "bot_uptime": str(datetime.now() - bot_start_time),
        "bot_status": bot_status,
        "service": "BTC Signal Bot"
    }
    
def run_flask():
    """Запускает Flask в отдельном потоке"""
    app.run(host='0.0.0.0', port=10000, debug=False)

print("=" * 50)
print("🚀 BTC/USDT SIGNAL BOT")
print("⚡ Bybit Futures | 10x Leverage") 
print("📊 Multi-Filter System (No Pandas)")
print("🌐 Web Server: Port 10000")
print("=" * 50)

# ============================
# НАСТРОЙКИ
# ============================
SYMBOL = 'BTC/USDT:USDT'
TIMEFRAME_MAIN = '15m'
TIMEFRAME_HIGHER = '4h'
INTERVAL = 900
LEVERAGE = 10

# Параметры фильтров
SUPERTREND_PERIOD = 8
SUPERTREND_MULTIPLIER = 2.5
ATR_PERIOD = 96
VOLUME_PERIOD = 20
ATR_FILTER_THRESHOLD = 1.1
VOLUME_FILTER_THRESHOLD = 1.3

TELEGRAM_BOT_TOKEN = "8296961504:AAEmgsjkSBewLaudDBYWranZWcfC6aBlNq4"
TELEGRAM_CHAT_ID = "6453886559"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

exchange = ccxt.bybit({'enableRateLimit': True})
last_signal = None

def calculate_simple_atr(ohlcv, period=14):
    """Упрощенный расчет ATR без pandas"""
    if len(ohlcv) < period + 1:
        return None
    
    true_ranges = []
    for i in range(1, len(ohlcv)):
        high = ohlcv[i][2]
        low = ohlcv[i][3]
        prev_close = ohlcv[i-1][4]
        
        tr1 = high - low
        tr2 = abs(high - prev_close)
        tr3 = abs(low - prev_close)
        true_range = max(tr1, tr2, tr3)
        true_ranges.append(true_range)
    
    # Простое скользящее среднее для ATR
    atr = sum(true_ranges[-period:]) / period
    return atr

def calculate_simple_supertrend(ohlcv, period=7, multiplier=3):
    """Упрощенный расчет Supertrend без pandas"""
    if len(ohlcv) < period + 1:
        return None
    
    atr = calculate_simple_atr(ohlcv, period)
    if atr is None:
        return None
    
    # Текущие значения
    current_high = ohlcv[-1][2]
    current_low = ohlcv[-1][3]
    current_close = ohlcv[-1][4]
    
    # Базовые линии
    hl2 = (current_high + current_low) / 2
    upper_band = hl2 + (multiplier * atr)
    lower_band = hl2 - (multiplier * atr)
    
    # Предыдущие значения для сравнения
    prev_close = ohlcv[-2][4] if len(ohlcv) >= 2 else current_close
    
    # Определение направления
    if current_close > upper_band:
        return 1  # UP
    elif current_close < lower_band:
        return -1  # DOWN
    else:
        # Если между band'ами, сохраняем предыдущее направление
        if prev_close > upper_band:
            return 1
        elif prev_close < lower_band:
            return -1
        else:
            return 1  # По умолчанию UP

def calculate_volume_average(ohlcv, period=20):
    """Расчет среднего объема"""
    if len(ohlcv) < period:
        return None
    
    volumes = [candle[5] for candle in ohlcv[-period:]]
    return sum(volumes) / period

def check_filters():
    """Проверка всех фильтров без pandas"""
    try:
        # Получаем данные для 15m и 4h
        ohlcv_15m = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME_MAIN, limit=200)
        ohlcv_4h = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME_HIGHER, limit=200)
        
        if not ohlcv_15m or not ohlcv_4h:
            return None, None, []
        
        # Текущая цена и объем
        current_price = ohlcv_15m[-1][4]
        current_volume = ohlcv_15m[-1][5]
        
        # Расчет ATR фильтра
        atr_current = calculate_simple_atr(ohlcv_15m, SUPERTREND_PERIOD)
        atr_avg = calculate_simple_atr(ohlcv_15m, ATR_PERIOD)
        
        atr_filter_passed = False
        if atr_current and atr_avg:
            atr_filter_passed = atr_current > (atr_avg * ATR_FILTER_THRESHOLD)
        
        # Расчет Volume фильтра
        volume_avg = calculate_volume_average(ohlcv_15m, VOLUME_PERIOD)
        volume_filter_passed = False
        if volume_avg:
            volume_filter_passed = current_volume > (volume_avg * VOLUME_FILTER_THRESHOLD)
        
        # Расчет таймфрейм фильтра
        direction_15m = calculate_simple_supertrend(ohlcv_15m, SUPERTREND_PERIOD, SUPERTREND_MULTIPLIER)
        direction_4h = calculate_simple_supertrend(ohlcv_4h, SUPERTREND_PERIOD, SUPERTREND_MULTIPLIER)
        
        timeframe_filter_passed = False
        if direction_15m and direction_4h:
            timeframe_filter_passed = (direction_15m == direction_4h)
        
        # Определение сигнала
        signal = None
        if direction_15m == 1:
            signal = "LONG"
        elif direction_15m == -1:
            signal = "SHORT"
        
        # Собираем пройденные фильтры
        passed_filters = []
        if atr_filter_passed:
            passed_filters.append("ATR")
        if volume_filter_passed:
            passed_filters.append("VOLUME") 
        if timeframe_filter_passed:
            passed_filters.append("TIMEFRAME")
        
        return signal, current_price, passed_filters
        
    except Exception as e:
        logger.error(f"Ошибка проверки фильтров: {e}")
        return None, None, []

def get_moscow_time():
    """Получение московского времени"""
    return datetime.utcnow() + timedelta(hours=3)

async def send_telegram_alert(signal, price, passed_filters):
    """Отправка сигнала в Telegram с информацией о фильтрах"""
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        
        # Эмодзи для фильтров
        filter_emojis = {
            "ATR": "📊",
            "VOLUME": "💧", 
            "TIMEFRAME": "⏰"
        }
        
        # Форматирование списка фильтров
        filters_text = ""
        for filter_name in ["ATR", "VOLUME", "TIMEFRAME"]:
            emoji = filter_emojis[filter_name]
            status = "✅" if filter_name in passed_filters else "❌"
            filters_text += f"{status} {emoji} {filter_name}\n"
        
        message = f"""
🎯 **BTC TRADING SIGNAL**

📈 **Направление:** {signal}
💰 **Текущая цена:** ${price:,.2f}
⏰ **Время (МСК):** {get_moscow_time().strftime('%d.%m %H:%M')}

**ФИЛЬТРЫ:**
{filters_text}
**Условие:** ≥2 фильтра ✅

⚡ **Bybit Futures**
🎚️ **Плечо:** {LEVERAGE}x

💡 **Рекомендации:**
• Стоп-лосс: 1.5-2% от цены входа
• Риск: не более 2% от депозита
• Плечо: {LEVERAGE}x

🔔 Следующая проверка через 15 минут...

⚠️ **ВНИМАНИЕ:** Всегда проверяйте сигнал самостоятельно!
        """
        
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID, 
            text=message,
            parse_mode='Markdown'
        )
        logger.info(f"✅ Сигнал отправлен: {signal} по цене ${price:,.2f}")
        logger.info(f"📊 Пройдены фильтры: {passed_filters}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка отправки в Telegram: {e}")

async def check_market():
    """Проверка рынка и отправка сигнала"""
    global last_signal
    
    try:
        logger.info("🔍 Проверяем рынок с фильтрами...")
        signal, price, passed_filters = check_filters()
        
        # Условие: минимум 2 фильтра пройдено И есть сигнал
        if signal and len(passed_filters) >= 2 and signal != last_signal:
            logger.info(f"🎯 Новый сигнал: {signal} (фильтры: {passed_filters})")
            await send_telegram_alert(signal, price, passed_filters)
            last_signal = signal
        elif signal:
            logger.info(f"📊 Цена: ${price:,.2f}, Сигнал: {signal}, Фильтры: {passed_filters} (недостаточно)")
        else:
            logger.info(f"📊 Проверка завершена. Сигнала нет.")
            
    except Exception as e:
        logger.error(f"💥 Ошибка проверки рынка: {e}")

async def bot_loop():
    """Основной цикл бота"""
    logger.info("🚀 Бот запущен с системой фильтров!")
    logger.info(f"⏰ Интервал проверки: {INTERVAL} секунд")
    logger.info("📊 Фильтры: ATR, Volume, Timeframe (минимум 2 для сигнала)")
    logger.info("📱 Ожидайте сигналы в Telegram...")
    
    # Бесконечный цикл
    def bot_loop():
        logger.info("🚀 Бот запущен с системой фильтров (синхронно)!")
    while True:
        try:
            asyncio.run(check_market())
        except Exception as e:
            logger.error(f"Ошибка в check_market: {e}")
        time.sleep(INTERVAL)

def start_bot():
   bot_loop()

if __name__ == "__main__":
    # Запускаем Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("🌐 Flask сервер запущен на порту 10000")
    
    # Запускаем бота в основном потоке
    try:
        start_bot()
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"💥 Критическая ошибка: {e}")
