import os
import asyncio
import re
from dotenv import load_dotenv

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

# Хранилище выбранных проектов: {user_id: project_name}
USER_PROJECTS = {}

# --- ДВИЖОК ОЧЕРЕДЕЙ ЗАДАЧ ---
# Структура: { project_name: asyncio.Queue }
PROJECT_QUEUES = {}
# Максимальное количество задач в очереди для одного проекта
MAX_QUEUE_SIZE = 5

class AiderTask:
    """Класс для хранения контекста задачи в очереди"""
    def __init__(self, message: Message, project_name: str, prompt: str):
        self.message = message
        self.project_name = project_name
        self.prompt = prompt


async def aider_queue_worker(project_name: str, queue: asyncio.Queue):
    """Фоновый воркер, обрабатывающий задачи для конкретного проекта одну за другой"""
    print(f"⚙️ Воркер для проекта [{project_name}] успешно запущен.")
    while True:
        # Ждем появления задачи в очереди
        task: AiderTask = await queue.get()
        
        # Переменные для удобства отправки уведомлений автору таски
        msg = task.message
        
        status_msg = await msg.reply(
            f"🚀 Задача взята в работу для проекта <code>{html.quote(task.project_name)}</code>!\n"
            f"⏳ Применяю изменения и создаю коммит...", 
            parse_mode=ParseMode.HTML
        )
        
        try:
            # Симулируем тайпинг в чат во время работы
            await msg.bot.send_chat_action(chat_id=msg.chat.id, action=ChatAction.TYPING)
            
            # Запускаем тяжелый процесс Aider
            result = await run_aider(task.project_name, task.prompt)
            
            # Очистка ANSI-последовательностей (цвета терминала)
            ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
            clean_result = ansi_escape.sub('', result)
            
            lines = clean_result.splitlines()
            summary_lines = []
            
            for line in lines:
                clean_line = line.strip()
                low_line = clean_line.lower()
                if "commit" in low_line or "applied edit" in low_line or "created file" in low_line:
                    if "git config" not in low_line and "git repo" not in low_line:
                        summary_lines.append(clean_line)
                    
            if summary_lines:
                summary_text = "\n".join(summary_lines[:15])
            else:
                summary_text = "Изменения применены (информация о коммитах не перехвачена в stdout)."

            log_filename = f"aider_{task.project_name}_{msg.from_user.id}.log"
            
            with open(log_filename, "w", encoding="utf-8") as f:
                f.write(result)
                
            document = FSInputFile(log_filename)
            await status_msg.delete()
            
            await msg.reply_document(
                document=document,
                caption=(
                    f"✅ <b>Проект:</b> <code>{html.quote(task.project_name)}</code>\n\n"
                    f"<b>Git коммиты и изменения:</b>\n"
                    f"<pre>{html.quote(summary_text)}</pre>\n\n"
                    f"<i>Полный лог размышлений сохранен в .log файле.</i>"
                ),
                parse_mode=ParseMode.HTML
            )
            
            if os.path.exists(log_filename):
                os.remove(log_filename)
                
        except Exception as e:
            await msg.reply(f"❌ Ошибка при обработке задачи воркером: {str(e)}")
        finally:
            # Сообщаем очереди, что задача полностью обработана
            queue.task_done()


# --- ХЭНДЛЕРЫ БОТА ---

@dp.message(lambda msg: msg.from_user.id not in ALLOWED_USERS)
async def handle_unauthorized(message: Message):
    await message.reply("доступ запрещен")

@dp.message(F.text == "/list")
async def cmd_list(message: Message):
    current_project = USER_PROJECTS.get(message.from_user.id, "❌ Не выбран")
    text = (
        "🤖 <b>Доступные команды:</b>\n\n"
        "📁 <code>/projects</code> — Показать список проектов на сервере\n"
        "🎯 <code>/select [имя_папки]</code> — Выбрать проект для работы\n"
        "🚀 <code>/run [промпт]</code> — Поставить задачу Aider в очередь проекта\n"
        "📎 <i>Пришли файл (документ) для загрузки контекста дизайна (figma_state.txt)</i>\n\n"
        f"<b>Текущий активный проект:</b> <code>{html.quote(current_project)}</code>"
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
    await message.reply(f"📁 <b>Список доступных проектов:</b>\n\n{list_str}\n\nСейчас выбран: <code>{html.quote(current_project)}</code>", parse_mode=ParseMode.HTML)

@dp.message(F.text.startswith("/select "))
async def cmd_select_project(message: Message):
    project_name = message.text.replace("/select ", "", 1).strip()
    project_path = os.path.join(BASE_WORKSPACE, project_name)
    
    if not project_name or not os.path.exists(project_path) or not os.path.isdir(project_path):
        return await message.reply("❌ Такой папки проекта не существует.", parse_mode=ParseMode.HTML)
        
    USER_PROJECTS[message.from_user.id] = project_name
    await message.reply(f"🎯 Проект <code>{html.quote(project_name)}</code> успешно выбран!", parse_mode=ParseMode.HTML)

@dp.message(F.document)
async def handle_document(message: Message):
    user_id = message.from_user.id
    if user_id not in USER_PROJECTS:
        return await message.reply("❌ Сначала выбери проект с помощью команды <code>/select [имя_папки]</code>", parse_mode=ParseMode.HTML)
    
    project_name = USER_PROJECTS[user_id]
    project_path = os.path.join(BASE_WORKSPACE, project_name)
    
    target_filename = os.environ.get("FIGMA_STATE_PATH", "figma_state.txt")
    target_path = os.path.join(project_path, target_filename)
    
    try:
        await message.bot.download(file=message.document.file_id, destination=target_path)
        await message.reply(f"✅ Дизайн загружен как <code>{html.quote(target_filename)}</code> в проект <code>{html.quote(project_name)}</code>.", parse_mode=ParseMode.HTML)
    except Exception as e:
        await message.reply(f"❌ Ошибка при сохранении файла: {str(e)}")

@dp.message(F.text.startswith("/run "))
async def cmd_run_aider(message: Message):
    prompt = message.text.replace("/run ", "", 1).strip()
    user_id = message.from_user.id
    
    if user_id not in USER_PROJECTS:
        return await message.reply("❌ Сначала выбери проект.", parse_mode=ParseMode.HTML)
    if not prompt:
        return await message.reply("❌ Напиши промпт.", parse_mode=ParseMode.HTML)

    project_name = USER_PROJECTS[user_id]

    # Инициализируем очередь и фоновый воркер для проекта, если они еще не созданы
    if project_name not in PROJECT_QUEUES:
        PROJECT_QUEUES[project_name] = asyncio.Queue()
        # Запускаем асинхронный фоновый воркер для этого конкретного проекта
        asyncio.create_task(aider_queue_worker(project_name, PROJECT_QUEUES[project_name]))

    project_queue = PROJECT_QUEUES[project_name]

    # Проверяем лимит очереди (до 5 задач)
    if project_queue.qsize() >= MAX_QUEUE_SIZE:
        return await message.reply(
            f"⚠️ Очередь задач для проекта <code>{html.quote(project_name)}</code> переполнена (макс. {MAX_QUEUE_SIZE}).\n"
            f"Подожди завершения текущих задач.", 
            parse_mode=ParseMode.HTML
        )

    # Создаем объект задачи и пушим его в конец очереди
    task = AiderTask(message, project_name, prompt)
    await project_queue.put(task)

    # Высчитываем позицию (текущий размер очереди включая только что добавленную задачу)
    queue_position = project_queue.qsize()

    if queue_position == 1:
        await message.reply(
            f"📥 Задача добавлена. Проект <code>{html.quote(project_name)}</code> свободен, сейчас запустится!", 
            parse_mode=ParseMode.HTML
        )
    else:
        await message.reply(
            f"📥 Задача успешно добавлена в очередь проекта <code>{html.quote(project_name)}</code>.\n"
            f"🔢 Твоя позиция в очереди: <b>{queue_position}</b>", 
            parse_mode=ParseMode.HTML
        )

@dp.message()
async def fallback(message: Message):
    await message.reply("Используй <code>/list</code> для просмотра доступных команд.", parse_mode=ParseMode.HTML)

async def main():
    if os.environ.get("BOT_PROXY"):
        print("⏳ Ожидание инициализации Xray прокси (5 сек)...")
        await asyncio.sleep(5)
    print("Бот успешно запущен.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())