import os
import asyncio
from dotenv import load_dotenv

# Подгружаем .env из родительской директории
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from aiogram import Bot, Dispatcher, F, html
from aiogram.types import Message, FSInputFile
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatAction
from aiogram.client.session.aiohttp import AiohttpSession

from run_aider import run_aider, BASE_WORKSPACE

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

dp = Dispatcher()
USER_PROJECTS = {}

@dp.message(lambda msg: msg.from_user.id not in ALLOWED_USERS)
async def handle_unauthorized(message: Message):
    await message.reply("доступ запрещен")

@dp.message(F.text == "/list")
async def cmd_list(message: Message):
    current_project = USER_PROJECTS.get(message.from_user.id, "❌ Не выбран")
    text = (
        "🤖 <b>Доступные команды:</b>\n\n"
        "📁 <code>/projects</code> — Показать список проектов\n"
        "🎯 <code>/select [имя]</code> — Выбрать проект\n"
        "🚀 <code>/run [промпт]</code> — Запустить Aider\n"
        "📎 <i>Пришли файл (документ) для загрузки контекста (figma_state.txt)</i>\n\n"
        f"<b>Текущий проект:</b> <code>{html.quote(current_project)}</code>"
    )
    await message.reply(text, parse_mode=ParseMode.HTML)

@dp.message(F.text == "/projects")
async def cmd_projects(message: Message):
    if not os.path.exists(BASE_WORKSPACE):
        return await message.reply("❌ Корневой воркспейс отсутствует.", parse_mode=ParseMode.HTML)
    projects = [d for d in os.listdir(BASE_WORKSPACE) if os.path.isdir(os.path.join(BASE_WORKSPACE, d)) and not d.startswith('.')]
    if not projects:
        return await message.reply("📁 Воркспейс пуст.", parse_mode=ParseMode.HTML)
    
    current_project = USER_PROJECTS.get(message.from_user.id, "Не выбран")
    list_str = "\n".join([f"🔹 <code>{html.quote(p)}</code>" for p in projects])
    await message.reply(f"📁 <b>Проекты:</b>\n\n{list_str}\n\nВыбран: <code>{html.quote(current_project)}</code>", parse_mode=ParseMode.HTML)

@dp.message(F.text.startswith("/select "))
async def cmd_select_project(message: Message):
    project_name = message.text.replace("/select ", "", 1).strip()
    project_path = os.path.join(BASE_WORKSPACE, project_name)
    if not project_name or not os.path.exists(project_path) or not os.path.isdir(project_path):
        return await message.reply("❌ Такой папки не существует.", parse_mode=ParseMode.HTML)
    USER_PROJECTS[message.from_user.id] = project_name
    await message.reply(f"🎯 Проект <code>{html.quote(project_name)}</code> выбран.", parse_mode=ParseMode.HTML)

@dp.message(F.document)
async def handle_document(message: Message):
    user_id = message.from_user.id
    if user_id not in USER_PROJECTS:
        return await message.reply("❌ Сначала выбери проект через <code>/select</code>", parse_mode=ParseMode.HTML)
    
    project_path = os.path.join(BASE_WORKSPACE, USER_PROJECTS[user_id])
    target_filename = os.environ.get("FIGMA_STATE_PATH", "figma_state.txt")
    target_path = os.path.join(project_path, target_filename)
    
    try:
        await message.bot.download(file=message.document.file_id, destination=target_path)
        await message.reply(f"✅ Файл загружен как <code>{html.quote(target_filename)}</code>", parse_mode=ParseMode.HTML)
    except Exception as e:
        await message.reply(f"❌ Ошибка: {str(e)}")

@dp.message(F.text.startswith("/run "))
async def cmd_run_aider(message: Message):
    prompt = message.text.replace("/run ", "", 1).strip()
    user_id = message.from_user.id
    
    if user_id not in USER_PROJECTS:
        return await message.reply("❌ Сначала выбери проект.", parse_mode=ParseMode.HTML)
    if not prompt:
        return await message.reply("❌ Напиши промпт.", parse_mode=ParseMode.HTML)

    project_name = USER_PROJECTS[user_id]
    status_msg = await message.reply(f"⏳ [Проект: {html.quote(project_name)}] Запуск Aider...", parse_mode=ParseMode.HTML)
    await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
    
    result = await run_aider(project_name, prompt)
    
    log_filename = f"aider_{project_name}_{user_id}.txt"
    try:
        with open(log_filename, "w", encoding="utf-8") as f:
            f.write(result)
        document = FSInputFile(log_filename)
        await status_msg.delete()
        await message.reply_document(
            document=document,
            caption=f"✅ Изменения в <code>{html.quote(project_name)}</code> применены.",
            parse_mode=ParseMode.HTML
        )
    finally:
        if os.path.exists(log_filename):
            os.remove(log_filename)

async def main():
    if os.environ.get("BOT_PROXY"):
        print("⏳ Ожидание Xray (5 сек)...")
        await asyncio.sleep(5)
    print("Бот запущен.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())