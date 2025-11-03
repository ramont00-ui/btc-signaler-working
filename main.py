import os
import logging
import ccxt
import asyncio
from datetime import datetime, timedelta
from telegram import Bot
import time
from flask import Flask
import threading

# ============================
# Flask для Render
# ============================
app = Flask(__name__)
bot_start_time = datetime.now()

@app.route('/')
def home():
    return "🚀 BTC Signal Bot is running! Check logs for signals."

@app.route('/health')
def health():
    """Эндпоинт для проверки статуса"""
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
    app.run(host='0.0.0.0', port=10000, debug=False, use_reloader=False)

# ============================
# Настройки
# ============================
print("=" * 50)
print("🚀 BTC/USDT SIGNAL BOT")
print("⚡️ Bybit Futures | 10x Leverage") 
print("📊 Multi-Filter System (No Pandas)")
print("🌐 Web Server: Port 10000")
print("=" * 50)

SYMBOL = 'BTC/USDT:USDT'
TIMEFRAME_MAIN = '15m'
TIMEFRAME_HIGHER = '4h'
INTERVAL = 900  # 15 минут
LEVERAGE = 10

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

# ============================
# Вспомогательные функции
# ============================
def calculate_simple_atr(ohlcv, period=14):
    if len(ohlcv) < period + 1:
        return None
    true_ranges = []
    for i in range(1, len(ohlcv)):
        high, low, prev_close = ohlcv[i][2], ohlcv[i][3], ohlcv[i-1][4]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        true_ranges.append(tr)
    return sum(true_ranges[-period:]) / period

def calculate_simple_supertrend(ohlcv, period=7, multiplier=3):
    if len(ohlcv) < period + 1:
        return None
    atr = calculate_simple_atr(ohlcv, period)
    if atr is None:
        return None
    current_high, current_low, current_close = ohlcv[-1][2], ohlcv[-1][3], ohlcv[-1][4]
    hl2 = (current_high + current_low) / 2
    upper_band = hl2 + (multiplier * atr)
    lower_band = hl2 - (multiplier * atr)
    prev_close = ohlcv[-2][4] if len(ohlcv) >= 2 else current_close
    if current_close > upper_band:
        return 1
    elif current_close < lower_band:
        return -1
    else:
        if prev_close > upper_band:
            return 1
        elif prev_close < lower_band:
            return -1
        else:
            return 1

def calculate_volume_average(ohlcv, period=20):
    if len(ohlcv) < period:
        return None
    volumes = [candle[5] for candle in ohlcv[-period:]]
    return sum(volumes) / period

def check_filters():
    try:
        ohlcv_15m = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME_MAIN, limit=200)
        ohlcv_4h = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME_HIGHER, limit=200)
        if not ohlcv_15m or not ohlcv_4h:
            return None, None, []

        current_price = ohlcv_15m[-1][4]
        current_volume = ohlcv_15m[-1][5]

        atr_current = calculate_simple_atr(ohlcv_15m, SUPERTREND_PERIOD)
        atr_avg = calculate_simple_atr(ohlcv_15m, ATR_PERIOD)
        atr_filter_passed = atr_current and atr_avg and atr_current > (atr_avg * ATR_FILTER_THRESHOLD)

        volume_avg = calculate_volume_average(ohlcv_15m, VOLUME_PERIOD)
        volume_filter_passed = volume_avg and current_volume > (volume_avg * VOLUME_FILTER_THRESHOLD)

        direction_15m = calculate_simple_supertrend(ohlcv_15m, SUPERTREND_PERIOD, SUPERTREND_MULTIPLIER)
        direction_4h = calculate_simple_supertrend(ohlcv_4h, SUPERTREND_PERIOD, SUPERTREND_MULTIPLIER)
        timeframe_filter_passed = direction_15m and direction_4h and direction_15m == direction_4h

        signal = "LONG" if direction_15m == 1 else "SHORT" if direction_15m == -1 else None
        passed_filters = []
        if atr_filter_passed: passed_filters.append("ATR")
        if volume_filter_passed: passed_filters.append("VOLUME")
        if timeframe_filter_passed: passed_filters.append("TIMEFRAME")
        return signal, current_price, passed_filters

    except Exception as e:
        logger.error(f"Ошибка проверки фильтров: {e}")
        return None, None, []

def get_moscow_time():
    return datetime.utcnow() + timedelta(hours=3)

async def send_telegram_alert(signal, price, passed_filters):
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        filter_emojis = {"ATR": "📊", "VOLUME": "💧", "TIMEFRAME": "⏰"}
        filters_text = ""
        for name in ["ATR", "VOLUME", "TIMEFRAME"]:
            emoji = filter_emojis[name]
            status = "✅" if name in passed_filters else "❌"
            filters_text += f"{status} {emoji} {name}\n"

        message = f"""
🎯 BTC TRADING SIGNAL

📈 Направление: {signal}
💰 Цена: ${price:,.2f}
⏰ Время (МСК): {get_moscow_time().strftime('%d.%m %H:%M')}

ФИЛЬТРЫ:
{filters_text}
Условие: ≥2 фильтра ✅

⚡️ Bybit Futures | Плечо {LEVERAGE}x
        """
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.info(f"✅ Сигнал отправлен: {signal} по цене ${price:,.2f}")
        logger.info(f"📊 Пройдены фильтры: {passed_filters}")
    except Exception as e:
        logger.error(f"Ошибка Telegram: {e}")

async def check_market():
    global last_signal
    try:
        logger.info("🔍 Проверка рынка...")
        signal, price, filters = check_filters()
        if signal and len(filters) >= 2 and signal != last_signal:
            await send_telegram_alert(signal, price, filters)
            last_signal = signal
        else:
            logger.info(f"📊 Сигнал: {signal}, фильтры: {filters}")
    except Exception as e:
        logger.error(f"Ошибка в check_market: {e}")

async def bot_loop():
    logger.info("🚀 Бот запущен с системой фильтров!")
    logger.info(f"⏰ Интервал: {INTERVAL} сек.")
    while True:
        await check_market()
        await asyncio.sleep(INTERVAL)

def start_bot():
    """Запускает бота в собственном event loop"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(bot_loop())
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()

# ============================
# Точка входа - ИСПРАВЛЕННАЯ
# ============================
if __name__ == "__main__":
    # Запускаем Flask в отдельном потоке (для Render)
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("🌐 Flask сервер запущен в отдельном потоке на порту 10000")

    # Запускаем бота в основном потоке
    logger.info("🤖 Запускаем торгового бота в основном потоке")
    start_bot()  # Этот вызов блокирует основной поток - это нормально для бота!
