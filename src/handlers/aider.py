import os
import asyncio
import aiohttp
import re
from aiogram import Router, F, html
from aiogram.types import Message
from aiogram.enums import ParseMode

from config import USER_PROJECTS, PROJECT_QUEUES, MAX_QUEUE_SIZE, ALLOWED_USERS
from run_aider import BASE_WORKSPACE
from helpers.git import get_target_branch, run_git_cmd

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

    # Local import to prevent circular dependency
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

@router.message(F.text.startswith("/pull"))
async def cmd_git_pull(message: Message):
    user_id = message.from_user.id
    if user_id not in USER_PROJECTS:
        return await message.reply("❌ Сначала выбери проект.", parse_mode=ParseMode.HTML)
    
    project_name = USER_PROJECTS[user_id]
    project_path = os.path.join(BASE_WORKSPACE, project_name)
    
    args = message.text.split(maxsplit=1)
    target_branch = args[1].strip() if len(args) > 1 else get_target_branch(project_name)

    status_msg = await message.reply(f"🔄 Выполняю <code>git pull origin {html.quote(target_branch)}</code>...", parse_mode=ParseMode.HTML)
    
    env = os.environ.copy()
    for proxy_key in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]:
        env.pop(proxy_key, None)

    await run_git_cmd(["git", "fetch", "origin"], project_path, env)
    code, out, err = await run_git_cmd(["git", "pull", "origin", target_branch], project_path, env)
    
    if code == 0:
        await status_msg.edit_text(
            f"✅ Проект <code>{html.quote(project_name)}</code> обновлен из <b>{html.quote(target_branch)}</b>.\n\n"
            f"<pre>{html.quote(out or 'Already up to date.')}</pre>",
            parse_mode=ParseMode.HTML
        )
    else:
        await status_msg.edit_text(f"❌ Ошибка pull:\n<pre>{html.quote(err or out)}</pre>", parse_mode=ParseMode.HTML)

@router.message(F.text.startswith("/pr"))
async def cmd_git_pr(message: Message):
    """
    Creates a Pull Request from the current AI branch to a target branch.
    Usage: /pr [target_branch] (default: develop)
    """
    user_id = message.from_user.id
    if user_id not in USER_PROJECTS:
        return await message.reply("❌ Сначала выбери проект.", parse_mode=ParseMode.HTML)
    
    project_name = USER_PROJECTS[user_id]
    project_path = os.path.join(BASE_WORKSPACE, project_name)
    
    args = message.text.split(maxsplit=1)
    base_branch = args[1].strip() if len(args) > 1 else "develop"
    
    # Git environment (exclude proxies for git operations)
    env = os.environ.copy()
    for proxy_key in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]:
        env.pop(proxy_key, None)

    # 1. Get current branch name
    _, head_branch, _ = await run_git_cmd(["git", "branch", "--show-current"], project_path, env)
    
    # 2. Get remote origin URL to parse owner/repo
    _, remote_url, _ = await run_git_cmd(["git", "remote", "get-url", "origin"], project_path, env)
    
    # Parse github owner/repo from SSH or HTTPS URL
    match = re.search(r"github\.com[:/](.+?)/(.+?)(\.git)?$", remote_url)
    if not match:
        return await message.reply("❌ Не удалось определить репозиторий GitHub из origin URL.")
    
    owner, repo = match.group(1), match.group(2)
    gh_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("OPENAI_API_KEY") # Attempting to reuse key if it's a proxy token or needs explicit GH_TOKEN

    status_msg = await message.reply(f"🚀 Создаю PR: <code>{head_branch}</code> → <code>{base_branch}</code>...", parse_mode=ParseMode.HTML)

    # 3. Ensure branch is pushed
    await run_git_cmd(["git", "push", "origin", head_branch], project_path, env)

    # 4. Create PR via GitHub API
    api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
    headers = {
        "Authorization": f"token {gh_token}",
        "Accept": "application/vnd.github.v3+json"
    }
    payload = {
        "title": f"feat(bot): aider improvements for {project_name}",
        "body": "Automated Pull Request created by Aider Agent.",
        "head": head_branch,
        "base": base_branch
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(api_url, json=payload, headers=headers) as resp:
            res_json = await resp.json()
            if resp.status == 201:
                pr_url = res_json.get("html_url")
                await status_msg.edit_text(
                    f"✅ <b>Pull Request успешно создан!</b>\n\n"
                    f"🔗 <a href='{pr_url}'>Просмотреть PR #{res_json.get('number')}</a>",
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=False
                )
            else:
                error_detail = res_json.get('message', 'Unknown error')
                if "already exists" in error_detail.lower():
                    await status_msg.edit_text("ℹ️ Pull Request уже существует для этой ветки.")
                else:
                    await status_msg.edit_text(f"❌ Ошибка API GitHub ({resp.status}):\n<code>{html.quote(error_detail)}</code>")