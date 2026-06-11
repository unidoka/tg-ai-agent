import os
import asyncio

from helpers.git import get_target_branch, run_git_cmd
from helpers.files import find_project_files
from services.yandex_proxy import YandexApiProxy

BASE_WORKSPACE = "/app/workspace"

async def run_aider(project_name: str, message_text: str) -> str:
    project_path = os.path.join(BASE_WORKSPACE, project_name)
    full_log = []
    
    if not os.path.exists(project_path):
        return f"❌ Ошибка: Папка проекта '{project_name}' не найдена в воркспейсе!"

    # 1. Настройка окружения и определение веток
    aider_branch = get_target_branch(project_name)

    env = os.environ.copy()
    for proxy_key in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]:
        env.pop(proxy_key, None)
    
    env["OPENAI_API_BASE"] = "http://127.0.0.1:28394"

    await run_git_cmd(["git", "config", "--global", "--add", "safe.directory", project_path], project_path, env)
    
    # 2. Подготовка Git-ветки
    full_log.append("=== GIT BRANCHING ===")
    await run_git_cmd(["git", "fetch", "origin"], project_path, env)

    code, out, _ = await run_git_cmd(["git", "branch", "--list", aider_branch], project_path, env)
    
    if aider_branch in out:
        code, _, err = await run_git_cmd(["git", "checkout", aider_branch], project_path, env)
        if code == 0:
            full_log.append(f"Переключено на существующую ветку {aider_branch}")
            pull_code, _, _ = await run_git_cmd(["git", "pull", "origin", aider_branch], project_path, env)
            if pull_code == 0:
                full_log.append(f"Синхронизировано с origin/{aider_branch}")
        else:
            full_log.append(f"⚠️ Ошибка перехода на ветку {aider_branch}: {err}")
    else:
        code_remote, out_remote, _ = await run_git_cmd(["git", "branch", "-r", "--list", f"origin/{aider_branch}"], project_path, env)
        if f"origin/{aider_branch}" in out_remote:
            code, _, err = await run_git_cmd(["git", "checkout", "-b", aider_branch, f"origin/{aider_branch}"], project_path, env)
            full_log.append(f"Создана локальная ветка {aider_branch} на основе удаленной origin/{aider_branch}")
        else:
            code, _, err = await run_git_cmd(["git", "checkout", "-b", aider_branch], project_path, env)
            if code == 0:
                full_log.append(f"Создана и выбрана новая ветка: {aider_branch}")
            else:
                full_log.append(f"⚠️ Ошибка создания ветки (работаем в текущей): {err}")

    # 3. Запуск локального прокси-сервера
    proxy_server = YandexApiProxy()
    await proxy_server.start()

    # 4. Подготовка файлов для Aider
    project_files = find_project_files(project_path)
    if not project_files:
        default_file = os.path.join(project_path, "index.html")
        if not os.path.exists(default_file):
            with open(default_file, "w", encoding="utf-8") as f: f.write("")
        project_files = ["index.html"]

    context_files = {"figma_state.txt", "tasks.md", "LLM_RULES.md"}
    project_files = [f for f in project_files if os.path.basename(f) not in context_files]

    # Сборка CLI-команды
    cmd = [
        "aider", 
        "--model", os.environ.get("OPENAI_API_MODEL"),
        "--edit-format", "whole",
        "--yes-always",
        "--no-show-model-warnings",
        "--analytics-disable",
        "--no-stream",
        "--no-suggest-shell-commands",
        "--no-auto-commits", 
        "--message", message_text
    ]

    for ctx_file in ["FIGMA_STATE_PATH", "TASKS_PATH", "LLM_RULES.md"]:
        default_name = "LLM_RULES.md" if ctx_file == "LLM_RULES.md" else os.environ.get(ctx_file, ctx_file.lower().replace("_path", ".txt").replace("tasks", "tasks.md"))
        path = os.path.join(project_path, default_name)
        if os.path.exists(path):
            cmd.extend(["--read", os.path.relpath(path, project_path)])

    cmd.extend(project_files)
    
    # 5. Выполнение Aider
    process = await asyncio.create_subprocess_exec(
        *cmd, env=env, cwd=project_path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    
    # Гарантированно глушим прокси после завершения работы Aider
    await proxy_server.stop()
    
    out_str = stdout.decode('utf-8', errors='replace').strip()
    err_str = stderr.decode('utf-8', errors='replace').strip()
    
    if out_str:
        full_log.append("\n=== AIDER STDOUT ===")
        full_log.append(out_str)
    if err_str and "Input is not a terminal" not in err_str:
        full_log.append("\n=== AIDER STDERR ===")
        full_log.append(err_str)
        
    # Коммит изменений
    await run_git_cmd(["git", "add", "."], project_path, env)
    commit_code, _, _ = await run_git_cmd(
        ["git", "commit", "-m", f"feat(bot): aider auto update - {message_text[:30]}"], 
        project_path, env
    )

    # 6. Автопуш результатов
    if process.returncode == 0:
        full_log.append("\n=== GIT AUTO PUSH ===")
        push_code, p_out, p_err = await run_git_cmd(["git", "push", "-u", "origin", aider_branch], project_path, env)
        
        if p_out: full_log.append(p_out)
        if p_err: full_log.append(p_err)
            
        if push_code == 0:
            full_log.append(f"\n✅ Все коммиты успешно улетели в ветку {aider_branch} на удаленный репозиторий!")
        else:
            full_log.append(f"\n❌ Ошибка во время выполнения git push. Код ответа: {push_code}")
    else:
        full_log.append(f"\n⚠️ Автопуш отменен, так как Aider завершился с ошибкой (код {process.returncode})")
        
    return "\n".join(full_log) if full_log else "Aider отработал, логи пусты."