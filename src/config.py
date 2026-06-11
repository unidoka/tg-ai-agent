import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.memory import MemoryStorage  # Добавили хранилище

# Загружаем .env, который лежит на уровень выше папки src/
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

TG_TOKEN = os.environ.get("TG_TOKEN")
ALLOWED_USERS_RAW = os.environ.get("ALLOWED_USERS_ID", "")
ALLOWED_USERS = set(int(uid.strip()) for uid in ALLOWED_USERS_RAW.split(",") if uid.strip().isdigit())

BOT_PROXY = os.environ.get("BOT_PROXY")

if BOT_PROXY:
    print(f"📡 Инициализация бота через прокси: {BOT_PROXY}")
    session = AiohttpSession(proxy=BOT_PROXY)
    bot = Bot(token=TG_TOKEN, session=session, default_properties=DefaultBotProperties(parse_mode=ParseMode.HTML))
else:
    print("⚠️ Прокси не задан. Бот идет напрямую.")
    bot = Bot(token=TG_TOKEN, default_properties=DefaultBotProperties(parse_mode=ParseMode.HTML))

# Инициализируем диспетчер с хранилищем состояний
dp = Dispatcher(storage=MemoryStorage())

# Глобальные хранилища данных (состояния внутри памяти процесса)
USER_PROJECTS = {}
PROJECT_QUEUES = {}
MAX_QUEUE_SIZE = 5