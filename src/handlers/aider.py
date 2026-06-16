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
    user_id = message.from_user.id
    gh_token = os.environ.get("GITHUB_TOKEN")
    
    if not gh_token:
        return await message.reply("❌ Ошибка: <code>GITHUB_TOKEN</code> не задан в .env файле.", parse_mode=ParseMode.HTML)
    
    if user_id not in USER_PROJECTS:
        return await message.reply("❌ Сначала выбери проект.", parse_mode=ParseMode.HTML)
    
    project_name = USER_PROJECTS[user_id]
    project_path = os.path.join(BASE_WORKSPACE, project_name)
    
    args = message.text.split(maxsplit=1)
    base_branch = args[1].strip() if len(args) > 1 else "develop"
    
    env = os.environ.copy()
    for proxy_key in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]:
        env.pop(proxy_key, None)

    # Get metadata
    _, head_branch, _ = await run_git_cmd(["git", "branch", "--show-current"], project_path, env)
    _, remote_url, _ = await run_git_cmd(["git", "remote", "get-url", "origin"], project_path, env)
    
    match = re.search(r"github\.com[:/](.+?)/(.+?)(\.git)?$", remote_url)
    if not match:
        return await message.reply("❌ Не удалось определить репозиторий GitHub.")
    
    owner, repo = match.group(1), match.group(2)
    status_msg = await message.reply(f"🚀 Подготовка PR: <code>{head_branch}</code> → <code>{base_branch}</code>...", parse_mode=ParseMode.HTML)

    # Sync state before PR
    push_code, _, push_err = await run_git_cmd(["git", "push", "origin", head_branch], project_path, env)
    if push_code != 0:
        return await status_msg.edit_text(f"❌ Ошибка при пуше ветки:\n<code>{html.quote(push_err)}</code>")

    # GitHub API Call
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
                    f"✅ <b>Pull Request создан!</b>\n\n"
                    f"🔗 <a href='{pr_url}'>Просмотреть PR #{res_json.get('number')}</a>",
                    parse_mode=ParseMode.HTML
                )
            elif resp.status == 422 and "already exists" in str(res_json):
                await status_msg.edit_text(f"ℹ️ Pull Request для ветки <code>{head_branch}</code> уже существует.")
            else:
                error_msg = res_json.get('message', 'Unknown error')
                await status_msg.edit_text(f"❌ GitHub API Error ({resp.status}):\n<code>{html.quote(error_msg)}</code>")