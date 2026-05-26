import os
import subprocess
import sys
from pathlib import Path
from dotenv import load_dotenv

def start_mcp_server():
    # 1. Загружаем переменные из .env
    load_dotenv()
    
    # 2. Достаем токен Фигмы
    # Если в .env переменная называется FIGMA_API_KEY, берем ее. 
    # Если нет — скрипт выдаст ошибку, чтобы ты сразу заметил.
    figma_api_key = os.getenv("figma_mcp_key")
    if not figma_api_key:
        print("❌ Ошибка: В .env файле не найдена переменная figma_mcp_key")
        sys.exit(1)

    port = os.getenv("mcp_server_port")
    log_file_path = "/tmp/figma_mcp.log"

    print(f"🚀 Запуск figma-developer-mcp на порту {port}...")
    print(f"📝 Логи будут записываться в: {log_file_path}")

    # 3. Готовим команду запуска
    cmd = [
        "figma-developer-mcp",
        "--port", port,
        "--figmaApiKey", figma_api_key
    ]

    # 4. Настраиваем окружение (LC_ALL=C для предотвращения проблем с локалью)
    env = os.environ.copy()
    env["LC_ALL"] = "C"

    try:
        # Открываем файл для записи логов (как > /tmp/figma_mcp.log 2>&1)
        with open(log_file_path, "a") as log_file:
            # Popen запускает процесс в фоне и не ждет его завершения (аналог &)
            process = subprocess.Popen(
                cmd,
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                preexec_fn=os.setpgrp # Отвязываем процесс от текущего терминала (аналог nohup)
            )
        
        print(f"✅ Сервер успешно запущен в фоне! PID процесса: {process.pid}")
        
    except FileNotFoundError:
        print("❌ Ошибка: Утилита figma-developer-mcp не найдена в системе.")
        print("Убедись, что она установлена глобально или активировано нужное виртуальное окружение.")
    except Exception as e:
        print(f"❌ Не удалось запустить сервер: {e}")

if __name__ == "__main__":
    start_mcp_server()
