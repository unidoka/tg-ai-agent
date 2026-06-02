import os
import asyncio
from dotenv import load_dotenv

# Подгружаем .env из родительской директории
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from aiogram import Bot, Dispatcher, F, html  # <-- html нужен для экранирования символов
from aiogram.types import Message
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatAction
from aiogram.client.session.aiohttp import AiohttpSession

from run_aider import run_aider, BASE_WORKSPACE

TG_TOKEN = os.environ.get("TG_TOKEN")
ALLOWED_USERS_RAW = os.environ.get("ALLOWED_USERS_ID", "")
ALLOWED_USERS = set(int(uid.strip()) for uid in ALLOWED_USERS_RAW.split(",") if uid.strip().isdigit())

# --- НАСТРОЙКА ПРОКСИ ДЛЯ ОБХОДА БЛОКИРОВОК ---
BOT_PROXY = os.environ.get("BOT_PROXY")

if BOT_PROXY:
    print(f"📡 Инициализация бота через прокси: {BOT_PROXY}")
    session = AiohttpSession(proxy=BOT_PROXY)
    bot = Bot(token=TG_TOKEN, session=session, default_properties=DefaultBotProperties(parse_mode=ParseMode.HTML))
else:
    print("⚠️ Прокси не задан. Бот идет напрямую.")
    bot = Bot(token=TG_TOKEN, default_properties=DefaultBotProperties(parse_mode=ParseMode.HTML))

dp = Dispatcher()

# Хранилище выбранных проектов в памяти: {user_id: "имя_папки_проекта"}
USER_PROJECTS = {}

@dp.message(lambda msg: msg.from_user.id not in ALLOWED_USERS)
async def handle_unauthorized(message: Message):
    await message.reply("доступ запрещен")

@dp.message(F.text == "/list")
async def cmd_list(message: Message):
    current_project = USER_PROJECTS.get(message.from_user.id, "❌ Не выбран")
    text = (
        "🤖 <b>Доступные команды:</b>\n\n"
        "📁 <code>/projects</code> — Показать список всех проектов на сервере\n"
        "🎯 <code>/select [имя_папки]</code> — Выбрать проект для работы\n"
        "🚀 <code>/run [промпт]</code> — Запустить Aider в выбранном проекте\n\n"
        f"<b>Текущий активный проект:</b> <code>{html.quote(current_project)}</code>"
    )
    await message.reply(text, parse_mode=ParseMode.HTML)

@dp.message(F.text == "/projects")
async def cmd_projects(message: Message):
    """Сканирует папку workspace и выводит список подпапок (проектов)"""
    if not os.path.exists(BASE_WORKSPACE):
        return await message.reply("❌ Корневой воркспейс отсутствует.", parse_mode=ParseMode.HTML)
        
    # Берем только папки, игнорируем скрытые
    projects = [d for d in os.listdir(BASE_WORKSPACE) if os.path.isdir(os.path.join(BASE_WORKSPACE, d)) and not d.startswith('.')]
    
    if not projects:
        return await message.reply("📁 Воркспейс пуст. Загрузи проекты в папку репозиториев.", parse_mode=ParseMode.HTML)
        
    current_project = USER_PROJECTS.get(message.from_user.id, "Не выбран")
    
    # Безопасно экранируем имена папок, чтобы не ломать HTML-разметку телеги
    list_str = "\n".join([f"🔹 <code>{html.quote(p)}</code>" for p in projects])
    text = (
        "📁 <b>Список доступных проектов:</b>\n\n"
        f"{list_str}\n\n"
        f"Чтобы выбрать, напиши: <code>/select имя_папки</code>\n"
        f"Сейчас выбран: <code>{html.quote(current_project)}</code>"
    )
    await message.reply(text, parse_mode=ParseMode.HTML)

@dp.message(F.text.startswith("/select "))
async def cmd_select_project(message: Message):
    """Выбирает проект для текущего пользователя"""
    project_name = message.text.replace("/select ", "", 1).strip()
    project_path = os.path.join(BASE_WORKSPACE, project_name)
    
    if not project_name or not os.path.exists(project_path) or not os.path.isdir(project_path):
        return await message.reply("❌ Такой папки проекта не существует. Проверь имя через <code>/projects</code>", parse_mode=ParseMode.HTML)
        
    USER_PROJECTS[message.from_user.id] = project_name
    await message.reply(f"🎯 Проект <code>{html.quote(project_name)}</code> успешно выбран! Теперь все команды <code>/run</code> будут выполняться в нём.", parse_mode=ParseMode.HTML)

@dp.message(F.text.startswith("/run "))
async def cmd_run_aider(message: Message):
    prompt = message.text.replace("/run ", "", 1).strip()
    user_id = message.from_user.id
    
    if user_id not in USER_PROJECTS:
        return await message.reply("❌ Сначала выбери проект с помощью команды <code>/select [имя_папки]</code>", parse_mode=ParseMode.HTML)
        
    if not prompt:
        return await message.reply("❌ Напиши промпт. Пример: <code>/run Создай контроллер</code>", parse_mode=ParseMode.HTML)

    project_name = USER_PROJECTS[user_id]
    
    await message.reply(f"⏳ [Проект: {html.quote(project_name)}] Запускаю фоновый процесс Aider...", parse_mode=ParseMode.HTML)
    await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
    
    # Передаем и имя проекта, и промпт в функцию запуска
    result = await run_aider(project_name, prompt)
    
    safe_result = result[:3900] + "\n...[ОБРЕЗАНО]" if len(result) > 3900 else result
    
    # Экранируем логи, так как в выводе кода 100% будут символы <, >, &, ломающие телегу
    await message.answer(
        f"✅ <b>Готово. Лог Aider ({html.quote(project_name)}):</b>\n<pre>{html.quote(safe_result)}</pre>", 
        parse_mode=ParseMode.HTML
    )

@dp.message()
async def fallback(message: Message):
    await message.reply("Используй <code>/list</code> для просмотра доступных команд.", parse_mode=ParseMode.HTML)

async def main():
    # Если запущен прокси-сервер в соседнем контейнере, даем ему 5 секунд проснуться
    if os.environ.get("BOT_PROXY"):
        print("⏳ Ожидание инициализации Xray прокси (5 сек)...")
        await asyncio.sleep(5)

    print("Бот запущен. Ожидание команд...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())