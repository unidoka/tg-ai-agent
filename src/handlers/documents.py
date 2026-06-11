import os
from aiogram import Router, F, html
from aiogram.types import Message
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from run_aider import BASE_WORKSPACE
from config import USER_PROJECTS, ALLOWED_USERS

router = Router()

# Определяем состояния ожидания файлов
class UploadStates(StatesGroup):
    waiting_for_figma = State()
    waiting_for_skills = State()


@router.message(lambda msg: msg.from_user.id not in ALLOWED_USERS)
async def ignore_unauthorized(message: Message):
    return


# --- БЛОК КОМАНД (ВЫЗОВ ИЗ МЕНЮ) ---

@router.message(F.text == "/set-figma-state")
async def cmd_set_figma_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id not in USER_PROJECTS:
        return await message.reply("❌ Сначала выбери проект с помощью команды <code>/select [имя_папки]</code>", parse_mode=ParseMode.HTML)
    
    await state.set_state(UploadStates.waiting_for_figma)
    await message.reply(
        f"📎 <b>Ожидаю файл дизайна Figma.</b>\n"
        f"Отправь мне файл контекста (например, <code>figma_state.txt</code>) для проекта <code>{html.quote(USER_PROJECTS[user_id])}</code>.\n\n"
        f"<i>Для отмены отправь любое текстовое сообщение.</i>", 
        parse_mode=ParseMode.HTML
    )


@router.message(F.text == "/set-skills")
async def cmd_set_skills_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id not in USER_PROJECTS:
        return await message.reply("❌ Сначала выбери проект с помощью команды <code>/select [имя_папки]</code>", parse_mode=ParseMode.HTML)
    
    await state.set_state(UploadStates.waiting_for_skills)
    await message.reply(
        f"🧠 <b>Ожидаю файл спецификации (Skills).</b>\n"
        f"Отправь мне <code>.md</code> файл с инструкциями для проекта <code>{html.quote(USER_PROJECTS[user_id])}</code>.\n\n"
        f"<i>Для отмены отправь любое текстовое сообщение.</i>", 
        parse_mode=ParseMode.HTML
    )


# --- БЛОК ОБРАБОТКИ ХЭНДЛЕРОВ С ФАЙЛАМИ (ПРИ ТЕКСТОВОЙ ПОДПИСИ) ---

@router.message(F.document)
async def handle_document_with_caption(message: Message, state: FSMContext):
    """Ловит прямую загрузку, если команда написана прямо в подписи (caption) к файлу"""
    user_id = message.from_user.id
    if user_id not in USER_PROJECTS:
        return await message.reply("❌ Сначала выбери проект.", parse_mode=ParseMode.HTML)
        
    caption = (message.caption or "").lower().strip()
    
    if "/set-figma-state" in caption or "figma" in caption:
        await save_context_file(message, "figma_state.txt", "figma_state.txt")
    elif "/set-skills" in caption or "skills" in caption:
        await save_context_file(message, "skills.md", "skills.md")
    else:
        await message.reply(
            "⚠️ Файл не распознан. Если хочешь загрузить контекст, используй команды:\n"
            "/set-figma-state — для дизайна Figma\n"
            "/set-skills — для спецификации (инструкций)", 
            parse_mode=ParseMode.HTML
        )


# --- БЛОК ПРИЕМА ФАЙЛОВ ИЗ СОСТОЯНИЙ (FSM) ---

@router.message(UploadStates.waiting_for_figma, F.document)
async def process_figma_upload(message: Message, state: FSMContext):
    target_filename = os.environ.get("FIGMA_STATE_PATH", "figma_state.txt")
    success = await save_context_file(message, target_filename, "Figma State")
    if success:
        await state.clear()


@router.message(UploadStates.waiting_for_skills, F.document)
async def process_skills_upload(message: Message, state: FSMContext):
    success = await save_context_file(message, "skills.md", "Спецификация (Skills)")
    if success:
        await state.clear()


# Сброс состояния, если вместо файла пришел обычный текст (отмена действия)
@router.message(UploadStates.waiting_for_figma)
@router.message(UploadStates.waiting_for_skills)
async def cancel_upload(message: Message, state: FSMContext):
    await state.clear()
    await message.reply("❌ Загрузка файла отменена. Возвращаюсь в обычный режим.")


# --- ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ДЛЯ КЛИЕНТСКОЙ ЗАГРУЗКИ ---

async def save_context_file(message: Message, target_filename: str, display_name: str) -> bool:
    user_id = message.from_user.id
    project_name = USER_PROJECTS[user_id]
    project_path = os.path.join(BASE_WORKSPACE, project_name)
    target_path = os.path.join(project_path, target_filename)
    
    try:
        await message.bot.download(file=message.document.file_id, destination=target_path)
        await message.reply(
            f"✅ Файл <b>{display_name}</b> успешно сохранен как <code>{html.quote(target_filename)}</code> "
            f"в корень проекта <code>{html.quote(project_name)}</code>.", 
            parse_mode=ParseMode.HTML
        )
        return True
    except Exception as e:
        await message.reply(f"❌ Ошибка при сохранении файла: {str(e)}")
        return False