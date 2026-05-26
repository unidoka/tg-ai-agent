import os
import json
import asyncio
import subprocess
from pathlib import Path
from dotenv import load_file, load_dotenv

load_dotenv()

from aiogram import Bot, Dispatcher, F, html
from aiogram.types import Message, InlineQuery, InlineQueryResultArticle, InputMessageContent
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatAction
from openai import AsyncOpenAI

TG_TOKEN = os.environ.get("TG_TOKEN")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
DEEPSEEK_API_URL = os.environ.get("DEEPSEEK_API_URL")
ALLOWED_USER_ID = int(os.environ.get("ALLOWED_USER_ID", 0))
PROJECT_DIR = os.environ.get("PROJECT_DIR")

HOME_DIR = str(Path.home())
CONFIG_PATH = os.path.join(HOME_DIR, ".aider.conf.json")

bot = Bot(token=TG_TOKEN, default_properties=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
ai_client = AsyncOpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_API_URL)

def ensure_mcp_config():
    """Синхронизирует токены из .env в JSON-конфиг Aider при каждом запуске бота"""
    mcp_config = {
        "mcpServers": {
            "figma-developer-mcp": {
                "command": "npx",
                "args": ["-y", "figma-developer-mcp", "--stdio"],
                "env": {
                    "FIGMA_API_KEY": os.environ.get("FIGMA_API_KEY", "")
                }
            },
            "github": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-github", "--stdio"],
                "env": {
                    "GITHUB_PERSONAL_ACCESS_TOKEN": os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN", "")
                }
            }
        }
    }
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(mcp_config, f, indent=2, ensure_ascii=False)

def get_claude_md_content() -> str:
    path = os.path.join(PROJECT_DIR, "CLAUDE.md")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return "Файл задач пуст или отсутствует."

async def run_aider_command(prompt: str) -> str:
    cmd = f"aider --model deepseek/deepseek-chat --message {html.quote(prompt)} --yes"
    process = await asyncio.create_subprocess_shell(
        cmd,
        cwd=PROJECT_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    return f"STDOUT:\n{stdout.decode().strip()}\n\nSTDERR:\n{stderr.decode().strip()}"

@dp.message(F.from_user.id != ALLOWED_USER_ID)
async def restriction_handler(message: Message):
    return

@dp.message(F.text.startswith("/mcp"))
async def handle_mcp_list(message: Message):
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            formatted_json = f.read()
    else:
        formatted_json = "Конфигурация еще не сгенерирована."
        
    response_text = (
        "🛠️ <b>Список подключенных MCP серверов:</b>\n\n"
        f"Глобальный конфиг (<code>~/.aider.conf.json</code>):\n"
        f"<pre><code class=\"language-json\">{formatted_json}</code></pre>"
    )
    await message.reply(response_text)

@dp.message(F.text.startswith("/task"))
async def handle_add_task(message: Message):
    task_text = message.text.replace("/task", "", 1).strip()
    if not task_text:
        await message.reply("❌ Напиши текст задачи после команды /task")
        return
        
    claude_path = os.path.join(PROJECT_DIR, "CLAUDE.md")
    os.makedirs(os.path.dirname(claude_path), exist_ok=True)
    with open(claude_path, "a", encoding="utf-8") as f:
        f.write(f"\n- {task_text}")
        
    await message.reply("🎯 Задача добавлена в список CLAUDE.md. Запускаю ИИ-разработчика Aider...")
    await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
    
    aider_prompt = (
        f"Выполни задачу из CLAUDE.md: '{task_text}'. Используй Figma MCP для макетов, "
        f"пиши код строго в ветку 'claude' и сделай пуш. Выведи краткий отчет."
    )
    result = await run_aider_command(aider_prompt)
    await message.answer(f"🤖 <b>Aider выполнил задачу! Лог:</b>\n<pre>{result[:3500]}</pre>")

@dp.message(F.text.startswith("/list"))
async def handle_list_tasks(message: Message):
    tasks = get_claude_md_content()
    await message.reply(f"📋 <b>Текущий список задач из CLAUDE.md:</b>\n\n<pre>{tasks}</pre>")

@dp.message(F.text.startswith("/replace"))
async def handle_replace_tasks(message: Message):
    new_tasks = message.text.replace("/replace", "", 1).strip()
    if not new_tasks:
        await message.reply("❌ Укажи новый список задач после команды /replace")
        return
        
    claude_path = os.path.join(PROJECT_DIR, "CLAUDE.md")
    os.makedirs(os.path.dirname(claude_path), exist_ok=True)
    with open(claude_path, "w", encoding="utf-8") as f:
        f.write(new_tasks)
        
    tasks = get_claude_md_content()
    await message.reply(f"♻️ <b>Все задачи успешно заменены!</b> Текущий список:\n\n<pre>{tasks}</pre>")

@dp.message(F.text.startswith("/report") | F.text.contains("отчет"))
async def handle_ai_report(message: Message):
    await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
    tasks_context = get_claude_md_content()
    
    response = await ai_client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": "Ты технический лид проекта. Проанализируй файл задач и составь краткий, понятный технический отчет о статусе."},
            {"role": "user", "content": f"Контекст файла CLAUDE.md:\n{tasks_context}"}
        ],
        max_tokens=1500
    )
    await message.reply(f"📊 <b>Базовый отчет от ИИ:</b>\n\n{response.choices.message.content}")

@dp.inline_query()
async def handle_inline_query(inline_query: InlineQuery):
    query_text = inline_query.query.strip()
    tasks_context = get_claude_md_content()
    
    if not query_text:
        results = [InlineQueryResultArticle(
            id="1",
            title="Проверить задачи",
            description="Показывает текущее содержимое CLAUDE.md",
            input_message_content=InputMessageContent(
                message_text=f"📋 <b>Текущие задачи проекта:</b>\n<pre>{tasks_context}</pre>"
            )
        )]
        await inline_query.answer(results, cache_time=1)
        return

    response = await ai_client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": f"Ты ИИ-ассистент разработчика. Отвечай коротко и по делу. Контекст проекта:\n{tasks_context}"},
            {"role": "user", "content": query_text}
        ],
        max_tokens=500
    )
    answer_text = response.choices.message.content
    
    results = [InlineQueryResultArticle(
        id="2",
        title="Ответ от DeepSeek",
        description=answer_text[:100] + "...",
        input_message_content=InputMessageContent(
            message_text=f"💡 <b>Запрос:</b> {query_text}\n\n🤖 <b>Ответ ИИ:</b> {answer_text}"
        )
    )]
    await inline_query.answer(results, cache_time=1)

@dp.message()
async def handle_generic_message(message: Message):
    await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
    tasks_context = get_claude_md_content()
    
    response = await ai_client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": f"Ты профессиональный ИИ-разработчик. Текущий контекст проекта:\n{tasks_context}"},
            {"role": "user", "content": message.text}
        ],
        max_tokens=2000
    )
    await message.reply(response.choices.message.content)

async def main():
    ensure_mcp_config()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
