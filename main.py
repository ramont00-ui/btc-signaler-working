import os
import logging
import ccxt
import asyncio
from datetime import datetime
from telegram import Bot
import time

print("=" * 50)
print("🚀 BTC/USDT SIGNAL BOT")
print("⚡ Bybit Futures | 10x Leverage")
print("📱 Telegram Alerts")
print("=" * 50)

# ============================
# НАСТРОЙКИ
# ============================
SYMBOL = 'BTC/USDT:USDT'
TIMEFRAME = '15m'
INTERVAL = 900
TELEGRAM_BOT_TOKEN = "ВАШ_TELEGRAM_BOT_TOKEN"  # 8296961504:AAEmgsjkSBewLaudDBYWranZWcfC6aBlNq4
TELEGRAM_CHAT_ID = "ВАШ_CHAT_ID"               # 6453886559

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Инициализация биржи
exchange = ccxt.bybit({'enableRateLimit': True})
last_signal = None

def get_simple_signal():
    """Простая логика сигнала на основе цены"""
    try:
        # Получаем последние свечи
        ohlcv = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=10)
        if len(ohlcv) < 2:
            return None, None
            
        current_close = ohlcv[-1][4]  # последняя цена закрытия
        previous_close = ohlcv[-2][4] # предыдущая цена закрытия
        
        # Простая логика: если цена выросла - LONG, упала - SHORT
        if current_close > previous_close:
            return "LONG", current_close
        elif current_close < previous_close:
            return "SHORT", current_close
        else:
            return None, current_close
            
    except Exception as e:
        logger.error(f"Ошибка получения данных: {e}")
        return None, None

async def send_telegram_alert(signal, price):
    """Отправка сигнала в Telegram"""
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        
        message = f"""
🎯 **BTC TRADING SIGNAL**

📈 **Направление:** {signal}
💰 **Цена:** ${price:,.2f}
⏰ **Время:** {datetime.now().strftime('%d.%m %H:%M')}

⚡ **Bybit Futures**
🎚️ **Плечо:** 10x

🔔 Следующая проверка через 15 минут...
        """
        
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID, 
            text=message,
            parse_mode='Markdown'
        )
        logger.info(f"✅ Сигнал отправлен: {signal} по цене ${price:,.2f}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка отправки в Telegram: {e}")

async def check_market():
    """Проверка рынка и отправка сигнала"""
    global last_signal
    
    try:
        logger.info("🔍 Проверяем рынок...")
        signal, price = get_simple_signal()
        
        if signal and signal != last_signal:
            logger.info(f"🎯 Новый сигнал: {signal}")
            await send_telegram_alert(signal, price)
            last_signal = signal
        elif price:
            logger.info(f"📊 Текущая цена: ${price:,.2f}, Сигнал: {signal or 'НЕТ'}")
        else:
            logger.warning("⚠️ Не удалось получить данные")
            
    except Exception as e:
        logger.error(f"💥 Ошибка проверки рынка: {e}")

async def main_loop():
    """Основной цикл бота"""
    logger.info("🚀 Бот запущен и работает!")
    logger.info(f"⏰ Интервал проверки: {INTERVAL} секунд")
    logger.info("📱 Ожидайте сигналы в Telegram...")
    
    # Бесконечный цикл
    while True:
        await check_market()
        logger.info(f"💤 Ожидание {INTERVAL} секунд до следующей проверки...")
        await asyncio.sleep(INTERVAL)

if __name__ == "__main__":
    try:
        # Проверяем что токен и chat ID установлены
        if "ВАШ_" in TELEGRAM_BOT_TOKEN or "ВАШ_" in TELEGRAM_CHAT_ID:
            print("❌ ОШИБКА: Замените TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID на реальные значения!")
            exit(1)
            
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"💥 Критическая ошибка: {e}")
