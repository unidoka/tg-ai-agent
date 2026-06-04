import os
import asyncio
import aiohttp
import json
from aiohttp import web


def get_target_branch(repo_name_or_path):
    """
    Парсит REPO_KEYS_MAP из .env и возвращает ветку для текущего репозитория.
    Если репозиторий не найден или маппинг пустой, возвращает 'ai'.
    """
    if not repo_name_or_path:
        return "ai"
        
    # Вытаскиваем чистое имя папки (на случай, если передан полный путь)
    repo_name = os.path.basename(os.path.normpath(repo_name_or_path))
    
    repo_keys_map = os.getenv("REPO_KEYS_MAP", "")
    if not repo_keys_map:
        return "ai"

    # Проходим по парам folder:key:branch
    for item in repo_keys_map.split(","):
        parts = item.split(":")
        # Проверяем, что это валидная тройка и имя папки совпадает
        if len(parts) == 3 and parts[0].strip() == repo_name:
            return parts[2].strip()
            
    return "ai"  # Фоллбэк, если репозитория нет в списке


# Базовый путь, где лежат все проекты (внутри контейнера)
BASE_WORKSPACE = "/app/workspace"


def find_project_files(project_path, max_depth=5):
    """Рекурсивный поиск файлов. 

    Файлы контекста (figma_state, tasks) в корне добавляются ВСЕГДА.
    Остальные файлы — только если они меньше 30 КБ и не содержат мусорных тегов.
    """
    project_files = []
    excludes = {'.git', 'node_modules', '.next', 'dist', 'build', 'public', '__pycache__'}
    ALWAYS_INCLUDE = {'figma_state.txt', 'tasks.md'}

    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in excludes and not d.startswith('.')]
        
        relative_root = os.path.relpath(root, project_path)
        if relative_root != '.' and relative_root.count(os.sep) >= max_depth:
            continue
            
        for file in files:
            if file.startswith('.env'):
                continue
                
            # Игнорируем битые файлы от прошлых косяков модели с <think>
            if '<' in file or '>' in file or 'think' in file.lower():
                continue
                
            file_full_path = os.path.join(root, file)
            is_root_file = (relative_root == '.')

            if is_root_file and file in ALWAYS_INCLUDE:
                rel_file = os.path.relpath(file_full_path, project_path)
                project_files.append(rel_file)
                continue

            # Фильтр по размеру (до 30 КБ), чтобы не взорвать лимит Яндекса в 1 МБ
            try:
                if os.path.getsize(file_full_path) > 30 * 1024:
                    continue
            except OSError:
                continue

            rel_file = os.path.relpath(file_full_path, project_path)
            project_files.append(rel_file)
                
    return project_files


# --- МИДЛВАРЬ-ПРОКСИ ДЛЯ ФИКСА ЯНДЕКСА ---
async def proxy_handler(request):
    """Перехватывает запрос от Aider, сует туда reasoning_effort=none и шлет в Яндекс"""
    target_url = "https://ai.api.cloud.yandex.net/v1/chat/completions"
    
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ['host', 'content-length']}
    body = await request.json()
    
    # Отключаем deep think
    body["reasoning_effort"] = "none"
    
    connector = aiohttp.TCPConnector(use_dns_cache=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        try:
            async with session.post(target_url, json=body, headers=headers, timeout=120) as resp:
                res_bytes = await resp.read()
                
                # Защитный пост-фильтр текста от тегов <think>
                try:
                    res_json = json.loads(res_bytes.decode('utf-8'))
                    if "choices" in res_json and len(res_json["choices"]) > 0:
                        content = res_json["choices"][0]["message"].get("content", "")
                        if "</think>" in content:
                            res_json["choices"][0]["message"]["content"] = content.split("</think>")[-1].strip()
                            res_bytes = json.dumps(res_json).encode('utf-8')
                except Exception:
                    pass

                return web.Response(
                    body=res_bytes, 
                    status=resp.status, 
                    headers={k: v for k, v in resp.headers.items() if k.lower() not in ['content-encoding', 'transfer-encoding', 'content-length']}
                )
        except Exception as e:
            return web.Response(text=f"Proxy Error: {str(e)}", status=500)


async def run_git_cmd(args, cwd, env):
    """Утилита для быстрого и безопасного выполнения git-команд"""
    proc = await asyncio.create_subprocess_exec(
        *args, cwd=cwd, env=env,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode, stdout.decode('utf-8', errors='replace').strip(), stderr.decode('utf-8', errors='replace').strip()


async def run_aider(project_name: str, message_text: str) -> str:
    project_path = os.path.join(BASE_WORKSPACE, project_name)
    full_log = []
    
    if not os.path.exists(project_path):
        return f"❌ Ошибка: Папка проекта '{project_name}' не найдена в воркспейсе!"

    # === ФИКС 1: Динамически определяем ветку именно для этого проекта ===
    aider_branch = get_target_branch(project_name)

    env = os.environ.copy()
    env.pop("HTTP_PROXY", None)
    env.pop("HTTPS_PROXY", None)
    env.pop("http_proxy", None)
    env.pop("https_proxy", None)
    
    # Направляем Aider в наш прокси
    env["OPENAI_API_BASE"] = "http://127.0.0.1:28394"

    # 1. Настройка гит-окружения
    await run_git_cmd(["git", "config", "--global", "--add", "safe.directory", project_path], project_path, env)
    
    # 2. Логика автоматического создания и переключения на ветку Aider'а
    full_log.append("=== GIT BRANCHING ===")
    
    # На всякий случай стягиваем свежие ветки с origin, чтобы знать актуальное состояние удаленного репо
    await run_git_cmd(["git", "fetch", "origin"], project_path, env)

    # Проверяем, существует ли уже локальная ветка
    code, out, _ = await run_git_cmd(["git", "branch", "--list", aider_branch], project_path, env)
    
    if aider_branch in out:
        # Ветка есть, переключаемся на неё
        code, _, err = await run_git_cmd(["git", "checkout", aider_branch], project_path, env)
        if code == 0:
            full_log.append(f"Переключено на существующую ветку {aider_branch}")
            # Пытаемся сделать pull, если ветка уже отслеживается на origin, чтобы избежать конфликтов
            pull_code, _, _ = await run_git_cmd(["git", "pull", "origin", aider_branch], project_path, env)
            if pull_code == 0:
                full_log.append(f"Синхронизировано с origin/{aider_branch}")
        else:
            full_log.append(f"⚠️ Ошибка перехода на ветку {aider_branch}: {err}")
    else:
        # Ветки локально нет. Проверим, может она есть на удаленном сервере (origin/ветка)
        code_remote, out_remote, _ = await run_git_cmd(["git", "branch", "-r", "--list", f"origin/{aider_branch}"], project_path, env)
        
        if f"origin/{aider_branch}" in out_remote:
            # Создаем локальную ветку, привязанную к удаленной
            code, _, err = await run_git_cmd(["git", "checkout", "-b", aider_branch, f"origin/{aider_branch}"], project_path, env)
            full_log.append(f"Создана локальная ветка {aider_branch} на основе удаленной origin/{aider_branch}")
        else:
            # Полностью новая ветка от текущего места
            code, _, err = await run_git_cmd(["git", "checkout", "-b", aider_branch], project_path, env)
            if code == 0:
                full_log.append(f"Создана и выбрана новая ветка: {aider_branch}")
            else:
                full_log.append(f"⚠️ Ошибка создания ветки (работаем в текущей): {err}")

    # 3. Запуск локального сервера-прокси для Яндекса
    app = web.Application()
    app.router.add_post('/chat/completions', proxy_handler)
    app.router.add_post('/v1/chat/completions', proxy_handler)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 28394)
    await site.start()

    # Собираем файлы проекта
    project_files = find_project_files(project_path)
    if not project_files:
        default_file = os.path.join(project_path, "index.html")
        if not os.path.exists(default_file):
            with open(default_file, "w", encoding="utf-8") as f: f.write("")
        project_files = ["index.html"]

    # Конфигурация запуска самого Aider
    cmd = [
        "aider", 
        "--model", os.environ.get("OPENAI_API_MODEL"),
        "--edit-format", "whole",
        "--yes-always",
        "--no-show-model-warnings",
        "--analytics-disable",
        "--no-stream",
        "--no-suggest-shell-commands",
        # Говорим айдеру не создавать свои "aider-auto-branch" ветки, а коммитить в текущую выбранную ветку
        "--no-auto-commits", 
        "--message", message_text
    ]

    figma_name = os.environ.get("FIGMA_STATE_PATH", "figma_state.txt")
    tasks_name = os.environ.get("TASKS_PATH", "tasks.md")
    figma_file_path = os.path.join(project_path, figma_name)
    tasks_file_path = os.path.join(project_path, tasks_name)

    if os.path.exists(figma_file_path):
        cmd.extend(["--read", os.path.relpath(figma_file_path, project_path)])
    if os.path.exists(tasks_file_path):
        cmd.extend(["--read", os.path.relpath(tasks_file_path, project_path)])

    cmd.extend(project_files)
    
    # 4. Запуск Aider
    process = await asyncio.create_subprocess_exec(
        *cmd, env=env, cwd=project_path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    
    # Выключаем прокси-сервер
    await runner.cleanup()
    
    out_str = stdout.decode('utf-8', errors='replace').strip()
    err_str = stderr.decode('utf-8', errors='replace').strip()
    
    if out_str:
        full_log.append("\n=== AIDER STDOUT ===")
        full_log.append(out_str)
    if err_str and "Input is not a terminal" not in err_str:
        full_log.append("\n=== AIDER STDERR ===")
        full_log.append(err_str)
        
    # Пытаемся сделать коммит, если у нас стоял флаг `--no-auto-commits`, чтобы собрать все правки Aider'а
    await run_git_cmd(["git", "add", "."], project_path, env)
    commit_code, _, _ = await run_git_cmd(["git", "commit", "-m", f"feat(bot): aider auto update - {message_text[:30]}"], project_path, env)

    # 5. БЛОК АВТОМАТИЧЕСКОГО ПУША НА УДАЛЕННЫЙ РЕПОЗИТОРИЙ
    if process.returncode == 0:
        full_log.append("\n=== GIT AUTO PUSH ===")
        # Пушим именно динамически вычисленную ветку
        push_code, p_out, p_err = await run_git_cmd(
            ["git", "push", "-u", "origin", aider_branch], 
            project_path, env
        )
        
        if p_out:
            full_log.append(p_out)
        if p_err:
            full_log.append(p_err)  # Гит пишет прогресс отправки в stderr, это ок
            
        if push_code == 0:
            full_log.append(f"\n✅ Все коммиты успешно улетели в ветку {aider_branch} на удаленный репозиторий!")
        else:
            full_log.append(f"\n❌ Ошибка во время выполнения git push. Код ответа: {push_code}")
    else:
        full_log.append(f"\n⚠️ Автопуш отменен, так как Aider завершился с ошибкой (код {process.returncode})")
        
    return "\n".join(full_log) if full_log else "Aider отработал, логи пусты."