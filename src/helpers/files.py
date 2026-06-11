import os

def find_project_files(project_path: str, max_depth: int = 5) -> list:
    """Рекурсивный поиск файлов проекта для передачи в Aider.

    Файлы контекста (figma_state, tasks, LLM_RULES) в корне добавляются ВСЕГДА.
    Остальные файлы — только если они меньше 30 КБ и не содержат мусорных тегов.
    """
    project_files = []
    excludes = {'.git', 'node_modules', '.next', 'dist', 'build', 'public', '__pycache__'}
    ALWAYS_INCLUDE = {'figma_state.txt', 'tasks.md', 'LLM_RULES.md'}

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

            # Фильтр по размеру (до 30 КБ)
            try:
                if os.path.getsize(file_full_path) > 30 * 1024:
                    continue
            except OSError:
                continue

            rel_file = os.path.relpath(file_full_path, project_path)
            project_files.append(rel_file)
                
    return project_files