import asyncio
import os

from config import bot, dp
from handlers import register_all_handlers

async def main():
    if os.environ.get("BOT_PROXY"):
        print("⏳ Ожидание инициализации Xray прокси (5 сек)...")
        await asyncio.sleep(5)
        
    # Подключаем роутеры из папки handlers
    register_all_handlers(dp)
    
    print("Бот успешно запущен.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())