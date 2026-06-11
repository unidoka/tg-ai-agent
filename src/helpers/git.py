import os
import asyncio

def get_target_branch(repo_name_or_path: str) -> str:
    """
    Парсит REPO_KEYS_MAP из .env и возвращает ветку для текущего репозитория.
    Если репозиторий не найден или маппинг пустой, возвращает 'ai'.
    """
    if not repo_name_or_path:
        return "ai"
        
    repo_name = os.path.basename(os.path.normpath(repo_name_or_path))
    repo_keys_map = os.getenv("REPO_KEYS_MAP", "")
    
    if not repo_keys_map:
        return "ai"

    for item in repo_keys_map.split(","):
        parts = item.split(":", 2)
        if len(parts) >= 3 and parts[0].strip() == repo_name:
            return parts[2].strip()
            
    return "ai"


async def run_git_cmd(args: list, cwd: str, env: dict):
    """Утилита для быстрого и безопасного выполнения git-команд"""
    proc = await asyncio.create_subprocess_exec(
        *args, cwd=cwd, env=env,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    return (
        proc.returncode, 
        stdout.decode('utf-8', errors='replace').strip(), 
        stderr.decode('utf-8', errors='replace').strip()
    )