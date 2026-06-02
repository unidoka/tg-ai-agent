так блять давай заново все продумаем

```
OPENAI_API_KEY=
OPENAI_API_MODEL=
OPENAI_API_BASE=

TG_TOKEN=
ALLOWED_USERS_ID=
FIGMA_STATE_PATH= // путь к файлу (находится в репозитории и пользователь сам будет загружать контекст. ему придется именно в таком пути создавать файл)
TASKS_PATH= // путь к тз в репозитории. пользователю придется сюда тз загружать
```

роуты:

получить список команд (которые бот выдает) /list 
запулить репозиторий(промпт. не надо промпт инженерингом заниматься, пользователь полностью сам его напишет), вызвать aider
больше не будет роутов, чтобы не ебать мозги


## вот как вызвать aider
обязательно епта читаем весь репозиторий. модифицируй функцию на большую глубина
```
def find_project_files():
    """Находит все файлы в текущем репозитории (глубина до 3 уровней), исключая скрытые."""
    project_files = []
    for root, dirs, files in os.walk('.'):
        # Исключаем скрытые директории (например, .git)
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        
        # Считаем глубину, чтобы не уходить глубже 3 уровней (аналог -maxdepth 3)
        depth = root.count(os.sep)
        if depth >= 3:
            continue
        for file in files:
            if not file.startswith('.'):
                project_files.append(os.path.join(root, file))
    return project_files


def run_aider(message, figma_state):
    env = os.environ.copy()
    env["OPENAI_API_KEY"] = os.environ["openai_api_key"]
    env["OPENAI_API_BASE"] = os.environ["openai_api_base"]

    project_files = find_project_files()

    cmd = [
        "aider", 
        "--model", os.environ["openai_api_model"],
        "--read", figma_state,
        "--message", f"{message}. {if figma_state f"Используй данные из {figma_state}"}",
        "--yes-always",
        "--no-auto-commits",
        "--no-show-model-warnings",
        "--analytics-disable",
        "--no-stream",
        "--no-suggest-shell-commands"
    ]
    
    cmd.extend(project_files)
    
    subprocess.run(cmd, env=env)
```