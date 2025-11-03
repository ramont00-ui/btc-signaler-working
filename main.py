import os
import logging
import ccxt
import asyncio
from datetime import datetime, timedelta
from telegram import Bot
import pandas as pd
import time

print("=" * 50)
print("🚀 BTC/USDT SIGNAL BOT")
print("⚡ Bybit Futures | 10x Leverage")
print("📊 Multi-Filter System")
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

def calculate_atr(df, period=14):
    """Расчет Average True Range"""
    high_low = df['high'] - df['low']
    high_close = abs(df['high'] - df['close'].shift())
    low_close = abs(df['low'] - df['close'].shift())
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return true_range.rolling(window=period).mean()

def calculate_supertrend(df, period=7, multiplier=3):
    """Упрощенный расчет Supertrend направления"""
    atr = calculate_atr(df, period)
    hl2 = (df['high'] + df['low']) / 2
    upper_band = hl2 + (multiplier * atr)
    lower_band = hl2 - (multiplier * atr)
    
    direction = []
    for i in range(len(df)):
        if i == 0:
            direction.append(1)
            continue
            
        if df['close'].iloc[i] > upper_band.iloc[i-1]:
            direction.append(1)  # UP
        elif df['close'].iloc[i] < lower_band.iloc[i-1]:
            direction.append(-1)  # DOWN
        else:
            direction.append(direction[-1])
    
    return direction[-1]

def get_ohlcv_data(symbol, timeframe, limit=100):
    """Получение OHLCV данных"""
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col])
        return df
    except Exception as e:
        logger.error(f"Ошибка получения данных {timeframe}: {e}")
        return None

def check_filters():
    """Проверка всех фильтров"""
    try:
        # Получаем данные
        df_15m = get_ohlcv_data(SYMBOL, TIMEFRAME_MAIN, 200)
        df_4h = get_ohlcv_data(SYMBOL, TIMEFRAME_HIGHER, 200)
        
        if df_15m is None or df_4h is None:
            return None, None, []
        
        # Текущая цена и объем
        current_price = df_15m['close'].iloc[-1]
        current_volume = df_15m['volume'].iloc[-1]
        
        # Расчет ATR фильтра
        atr_current = calculate_atr(df_15m, SUPERTREND_PERIOD).iloc[-1]
        atr_avg = calculate_atr(df_15m, ATR_PERIOD).iloc[-1]
        atr_filter_passed = atr_current > (atr_avg * ATR_FILTER_THRESHOLD)
        
        # Расчет Volume фильтра
        volume_avg = df_15m['volume'].rolling(VOLUME_PERIOD).mean().iloc[-1]
        volume_filter_passed = current_volume > (volume_avg * VOLUME_FILTER_THRESHOLD)
        
        # Расчет таймфрейм фильтра
        direction_15m = calculate_supertrend(df_15m, SUPERTREND_PERIOD, SUPERTREND_MULTIPLIER)
        direction_4h = calculate_supertrend(df_4h, SUPERTREND_PERIOD, SUPERTREND_MULTIPLIER)
        timeframe_filter_passed = (direction_15m == direction_4h)
        
        # Определение сигнала
        signal = "LONG" if direction_15m == 1 else "SHORT" if direction_15m == -1 else None
        
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

async def main_loop():
    """Основной цикл бота"""
    logger.info("🚀 Бот запущен с системой фильтров!")
    logger.info(f"⏰ Интервал проверки: {INTERVAL} секунд")
    logger.info("📊 Фильтры: ATR, Volume, Timeframe (минимум 2 для сигнала)")
    logger.info("📱 Ожидайте сигналы в Telegram...")
    
    # Бесконечный цикл
    while True:
        await check_market()
        logger.info(f"💤 Ожидание {INTERVAL} секунд до следующей проверки...")
        await asyncio.sleep(INTERVAL)

if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"💥 Критическая ошибка: {e}")
