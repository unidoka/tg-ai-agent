import os
import asyncio

# Базовый путь
BASE_WORKSPACE = "/app/workspace"

def find_project_files(project_path, max_depth=5):
    """Рекурсивный поиск файлов, аналогичный твоему старому скрипту"""
    project_files = []
    excludes = {'.git', 'node_modules', 'venv', '.venv', '__pycache__', '.idea', 'dist', 'build'}
    
    for root, dirs, files in os.walk(project_path):
        # Исключаем лишнее
        dirs[:] = [d for d in dirs if d not in excludes and not d.startswith('.')]
        
        # Считаем глубину
        relative_root = os.path.relpath(root, project_path)
        if relative_root != '.' and relative_root.count(os.sep) >= max_depth:
            continue
            
        for file in files:
            if not file.startswith('.'):
                # Добавляем путь относительно cwd (когда запустим subprocess, это будет просто имя файла)
                rel_file = os.path.relpath(os.path.join(root, file), project_path)
                project_files.append(rel_file)
                
    return project_files

async def run_aider(project_name: str, message_text: str) -> str:
    project_path = os.path.join(BASE_WORKSPACE, project_name)
    
    if not os.path.exists(project_path):
        return f"❌ Ошибка: Папка проекта '{project_name}' не найдена!"

    # Подготовка файлов
    project_files = find_project_files(project_path)
    
    # 🚨 Фикс для пустого репозитория: если файлов нет, Aider не поймет, что делать
    if not project_files:
        default_file = os.path.join(project_path, "index.html")
        with open(default_file, "w", encoding="utf-8") as f:
            f.write("")
        project_files = ["index.html"]

    env = os.environ.copy()
    env.pop("HTTP_PROXY", None)
    env.pop("HTTPS_PROXY", None)
    env.pop("http_proxy", None)
    env.pop("https_proxy", None)
    if os.environ.get("OPENAI_API_BASE"):
        env["OPENAI_API_BASE"] = os.environ["OPENAI_API_BASE"]

    # Формируем команду
    cmd = [
        "aider", 
        "--model", os.environ.get("OPENAI_API_MODEL"),
        "--edit-format", "whole",
        "--yes-always",
        "--no-auto-commits",
        "--no-show-model-warnings",
        "--analytics-disable",
        "--no-stream",
        "--no-suggest-shell-commands",
        "--message", message_text
    ]

    # Добавляем файлы из Figma/Tasks, если есть
    figma_path = os.path.join(project_path, os.environ.get("FIGMA_STATE_PATH", "figma_state.txt"))
    tasks_path = os.path.join(project_path, os.environ.get("TASKS_PATH", "tasks.md"))
    
    if os.path.exists(figma_path):
        cmd.extend(["--read", os.path.relpath(figma_path, project_path)])
    if os.path.exists(tasks_path):
        cmd.extend(["--read", os.path.relpath(tasks_path, project_path)])

    # Добавляем файлы проекта в конец
    cmd.extend(project_files)
    
    # Запуск
    process = await asyncio.create_subprocess_exec(
        *cmd,
        env=env,
        cwd=project_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    stdout, stderr = await process.communicate()
    
    out_str = stdout.decode('utf-8', errors='replace').strip()
    err_str = stderr.decode('utf-8', errors='replace').strip()
    
    return f"=== STDOUT ===\n{out_str}\n\n=== STDERR ===\n{err_str}"