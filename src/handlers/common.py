import os
from aiogram import Router, F, html
from aiogram.types import Message
from aiogram.enums import ParseMode

from run_aider import BASE_WORKSPACE
from config import ALLOWED_USERS, USER_PROJECTS

router = Router()

@router.message(lambda msg: msg.from_user.id not in ALLOWED_USERS)
async def handle_unauthorized(message: Message):
    await message.reply("доступ запрещен")

@router.message(F.text == "/list")
async def cmd_list(message: Message):
    current_project = USER_PROJECTS.get(message.from_user.id, "❌ Не выбран")
    text = (
        "🤖 <b>Доступные команды:</b>\n\n"
        "📁 <code>/projects</code> — Показать список проектов на сервере\n"
        "🎯 <code>/select [имя_папки]</code> — Выбрать проект для работы\n"
        "🚀 <code>/run [промпт]</code> — Поставить задачу Aider в очередь проекта\n"
        "📐 <code>/set-figma-state</code> — Загрузить контекст дизайна (figma_state.txt)\n"
        "🧠 <code>/set-skills</code> — Загрузить спецификацию правил для бота (skills.md)\n\n"
        f"<b>Текущий активный проект:</b> <code>{html.quote(current_project)}</code>"
    )
    await message.reply(text, parse_mode=ParseMode.HTML)

@router.message(F.text == "/projects")
async def cmd_projects(message: Message):
    if not os.path.exists(BASE_WORKSPACE):
        return await message.reply("❌ Корневой воркспейс отсутствует.", parse_mode=ParseMode.HTML)
    
    projects = [d for d in os.listdir(BASE_WORKSPACE) if os.path.isdir(os.path.join(BASE_WORKSPACE, d)) and not d.startswith('.')]
    if not projects:
        return await message.reply("📁 Воркспейс пуст.", parse_mode=ParseMode.HTML)
        
    current_project = USER_PROJECTS.get(message.from_user.id, "Не выбран")
    list_str = "\n".join([f"🔹 <code>{html.quote(p)}</code>" for p in projects])
    await message.reply(f"📁 <b>Список доступных проектов:</b>\n\n{list_str}\n\nСейчас выбран: <code>{html.quote(current_project)}</code>", parse_mode=ParseMode.HTML)

@router.message(F.text.startswith("/select "))
async def cmd_select_project(message: Message):
    project_name = message.text.replace("/select ", "", 1).strip()
    project_path = os.path.join(BASE_WORKSPACE, project_name)
    
    if not project_name or not os.path.exists(project_path) or not os.path.isdir(project_path):
        return await message.reply("❌ Такой папки проекта не существует.", parse_mode=ParseMode.HTML)
        
    USER_PROJECTS[message.from_user.id] = project_name
    await message.reply(f"🎯 Проект <code>{html.quote(project_name)}</code> успешно выбран!", parse_mode=ParseMode.HTML)


@router.message()
async def fallback(message: Message):
    await message.reply("Используй <code>/list</code> для просмотра доступных команд.", parse_mode=ParseMode.HTML)