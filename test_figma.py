import sys
import json
import yaml
import requests
import subprocess
import os
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv

load_dotenv()

def get_ids_from_url(url):
    path_parts = urlparse(url).path.split('/')
    file_key = next((part for part in path_parts if len(part) >= 22), None)
    query = parse_qs(urlparse(url).query)
    node_id = query.get('node-id', [None])[0]
    # ПРИНУДИТЕЛЬНО чистим ID от лишних символов
    if node_id:
        node_id = node_id.replace("%3A", "-").replace(":", "-")
    return file_key, node_id

def fetch_figma_data(node_id, file_key):
    mcp_host = os.getenv("MCP_SERVER_HOST", "127.0.0.1")
    url = f"http://mcp-server:{os.environ['mcp_server_port']}/mcp"
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "id": 1,
        "params": {
            "name": "get_figma_data",
            "arguments": {"fileKey": file_key, "nodeId": node_id}
        }
    }
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    
    response = requests.post(url, json=payload, headers=headers, stream=True)
    
    for line in response.iter_lines():
        if line:
            decoded = line.decode('utf-8')
            if decoded.startswith("data: "):
                try:
                    data = json.loads(decoded[6:])
                    if data.get("isError"):
                        return f"Error: {data.get('result', {}).get('content', [{}])[0].get('text')}"
                    return data.get("result", {}).get("content", [{}])[0].get("text")
                except: continue
    return None

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

def run_aider(message, yaml_file):
    env = os.environ.copy()
    env["OPENAI_API_KEY"] = os.environ["openai_api_key"]
    env["OPENAI_API_BASE"] = os.environ["openai_api_base"]

    # Собираем файлы проекта для контекста
    project_files = find_project_files()

    # Базовые аргументы Aider из твоего Bash-скрипта + фикс каталога и модели
    cmd = [
        "aider", 
        "--model", os.environ["openai_api_model"],
        "--read", yaml_file,
        "--message", f"{message}. Используй данные из {yaml_file}.",
        "--yes-always",
        "--no-auto-commits",
        "--no-show-model-warnings",
        "--analytics-disable",
        "--no-stream",
        "--no-suggest-shell-commands"
    ]
    
    # Добавляем найденные файлы в конец команды
    cmd.extend(project_files)
    
    subprocess.run(cmd, env=env)

def extract_code_from_yaml(yaml_file):
    try:
        with open(yaml_file, 'r') as f:
            data = yaml.safe_load(f)
    except FileNotFoundError:
        return None
    # Recursive search for Text node with numeric content
    def find_code(node):
        if isinstance(node, dict):
            # Check if this node is the input text field
            if node.get('name') == 'Text' and node.get('type') == 'TEXT':
                text = node.get('text')
                # Return if text exists and looks like a code (digits)
                if text and text.strip().isdigit():
                    return text.strip()
            for key, value in node.items():
                result = find_code(value)
                if result is not None:
                    return result
        elif isinstance(node, list):
            for item in node:
                result = find_code(item)
                if result is not None:
                    return result
        return None
    return find_code(data)

if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "get_code":
        code = extract_code_from_yaml("figma_design_current.yaml")
        if code:
            print(f"Code: {code}")
        else:
            print("Code not found")
        sys.exit(0)
    if len(sys.argv) < 3:
        print("Использование: python3 test_figma.py <сообщение> <URL>")
        print("       или: python3 test_figma.py get_code")
        sys.exit(1)

    message, url = sys.argv[1], sys.argv[2]
    file_key, node_id = get_ids_from_url(url)
    
    print(f"🌐 Скачиваю {node_id} (Key: {file_key})...")
    content = fetch_figma_data(node_id, file_key)
    
    if content:
        Path("figma_design_current.yaml").write_text(content)
        print("✅ Файл готов, запускаю Аидер...")
        run_aider(message, "figma_design_current.yaml")
    else:
        print("❌ Ошибка при получении данных из Фигмы.")
