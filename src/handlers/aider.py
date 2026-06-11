import asyncio
from aiogram import Router, F, html
from aiogram.types import Message
from aiogram.enums import ParseMode

from config import USER_PROJECTS, PROJECT_QUEUES, MAX_QUEUE_SIZE, ALLOWED_USERS

router = Router()

@router.message(lambda msg: msg.from_user.id not in ALLOWED_USERS)
async def ignore_unauthorized(message: Message):
    return

@router.message(F.text.startswith("/run "))
async def cmd_run_aider(message: Message):
    prompt = message.text.replace("/run ", "", 1).strip()
    user_id = message.from_user.id
    
    if user_id not in USER_PROJECTS:
        return await message.reply("❌ Сначала выбери проект.", parse_mode=ParseMode.HTML)
    if not prompt:
        return await message.reply("❌ Напиши промпт.", parse_mode=ParseMode.HTML)

    project_name = USER_PROJECTS[user_id]

    # Локальный импорт для защиты от круговой зависимости
    from queue_manager import AiderTask, aider_queue_worker

    if project_name not in PROJECT_QUEUES:
        PROJECT_QUEUES[project_name] = asyncio.Queue()
        asyncio.create_task(aider_queue_worker(project_name, PROJECT_QUEUES[project_name]))

    project_queue = PROJECT_QUEUES[project_name]

    if project_queue.qsize() >= MAX_QUEUE_SIZE:
        return await message.reply(
            f"⚠️ Очередь задач для проекта <code>{html.quote(project_name)}</code> переполнена (макс. {MAX_QUEUE_SIZE}).\n"
            f"Подожди завершения текущих задач.", 
            parse_mode=ParseMode.HTML
        )

    task = AiderTask(message, project_name, prompt)
    await project_queue.put(task)

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