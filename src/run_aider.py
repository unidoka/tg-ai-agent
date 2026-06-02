import os
import asyncio

# Базовый путь, где лежат все проекты (внутри контейнера)
BASE_WORKSPACE = "/app/workspace"

def find_project_files(project_path, max_depth=5):
    """Находит файлы в конкретном выбранном проекте"""
    project_files = []
    excludes = {'.git', 'node_modules', 'venv', '.venv', '__pycache__', '.idea', 'dist', 'build'}
    
    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in excludes and not d.startswith('.')]
        
        # Считаем глубину относительно корня выбранного проекта
        relative_root = os.path.relpath(root, project_path)
        if relative_root != '.' and relative_root.count(os.sep) >= max_depth:
            continue
            
        for file in files:
            if not file.startswith('.'):
                project_files.append(os.path.join(root, file))
                
    return project_files

async def run_aider(project_name: str, message_text: str) -> str:
    """Асинхронный вызов Aider внутри конкретной папки проекта"""
    project_path = os.path.join(BASE_WORKSPACE, project_name)
    
    if not os.path.exists(project_path):
        return f"❌ Ошибка: Папка проекта '{project_name}' не найдена в воркспейсе!"

    env = os.environ.copy()
    if os.environ.get("OPENAI_API_BASE"):
        env["OPENAI_API_BASE"] = os.environ["OPENAI_API_BASE"]

    project_files = find_project_files(project_path)
    
    # 🚨 ЖЕСТКАЯ ИНЪЕКЦИЯ ПРОМПТА ДЛЯ ПОДАВЛЕНИЯ МУСОРА И <think>
    prompt = message_text + (
        "\n\n====================\n"
        "🚨 СИСТЕМНОЕ ПРАВИЛО (КРИТИЧЕСКИ ВАЖНО): 🚨\n"
        "1. ЗАПРЕЩЕНО использовать теги <think> и писать цепочки рассуждений.\n"
        "2. ЗАПРЕЩЕНО писать любые вводные фразы (например, 'Let\\'s write the code', 'Here is', 'Ок, сделаю').\n"
        "3. Твой ответ должен начинаться СТРОГО с имени файла на чистой строке, после чего сразу идет блок кода. "
        "Если ты напишешь хоть один символ перед именем файла, система упадет!"
    )
    
    figma_name = os.environ.get("FIGMA_STATE_PATH", "figma_state.txt")
    tasks_name = os.environ.get("TASKS_PATH", "tasks.md")
    
    figma_file_path = os.path.join(project_path, figma_name)
    tasks_file_path = os.path.join(project_path, tasks_name)

    cmd = [
        "aider", 
        "--model", os.environ.get("OPENAI_API_MODEL"),
        "--edit-format", "whole",
        "--yes-always",
        "--no-auto-commits",
        "--no-show-model-warnings",
        "--analytics-disable",
        "--no-stream",
        "--no-suggest-shell-commands"
    ]

    if os.path.exists(figma_file_path):
        prompt += f"\n\nУЧИТЫВАЙ КОНТЕКСТ ДИЗАЙНА ИЗ ФАЙЛА: {figma_name}"
        cmd.extend(["--read", figma_file_path])
        
    if os.path.exists(tasks_file_path):
        prompt += f"\n\nУЧИТЫВАЙ ТЕХНИЧЕСКОЕ ЗАДАНИЕ ИЗ ФАЙЛА: {tasks_name}"
        cmd.extend(["--read", tasks_file_path])

    cmd.extend(["--message", prompt])
    cmd.extend(project_files)
    
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
    
    return f"STDOUT:\n{out_str}\n\nSTDERR:\n{err_str}"