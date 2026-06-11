import os
import re
import asyncio
from aiogram import html
from aiogram.types import Message, FSInputFile
from aiogram.enums import ParseMode, ChatAction

from run_aider import run_aider

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
        task: AiderTask = await queue.get()
        msg = task.message
        
        status_msg = await msg.reply(
            f"🚀 Задача взята в работу для проекта <code>{html.quote(task.project_name)}</code>!\n"
            f"⏳ Применяю изменения и создаю коммит...", 
            parse_mode=ParseMode.HTML
        )
        
        try:
            await msg.bot.send_chat_action(chat_id=msg.chat.id, action=ChatAction.TYPING)
            
            # Вызов тяжелого процесса Aider
            result = await run_aider(task.project_name, task.prompt)
            
            # Очистка ANSI-последовательностей
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
            queue.task_done()