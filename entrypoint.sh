#!/bin/bash
set -e

# === ШАГ 1: ИМПОРТ И НАСТРОЙКА ВСЕХ КЛЮЧЕЙ ===
if [ -z "$SSH_KEYS" ]; then
    echo "[WARN] Переменная SSH_KEYS в .env пустая. Ключи не будут настроены."
else
    echo "[INFO] Настройка безопасных SSH-ключей..."
    mkdir -p /root/.ssh_local
    chown root:root /root/.ssh_local
    chmod 700 /root/.ssh_local

    IFS=',' read -r -a KEYS_ARRAY <<< "$SSH_KEYS"
    for KEY_NAME in "${KEYS_ARRAY[@]}"; do
        KEY_NAME=$(echo "$KEY_NAME" | xargs)
        if [ -f "/root/.ssh/$KEY_NAME" ]; then
            cp "/root/.ssh/$KEY_NAME" "/root/.ssh_local/$KEY_NAME"
            [ -f "/root/.ssh/${KEY_NAME}.pub" ] && cp "/root/.ssh/${KEY_NAME}.pub" "/root/.ssh_local/${KEY_NAME}.pub" && chmod 644 "/root/.ssh_local/${KEY_NAME}.pub"
            
            chown root:root "/root/.ssh_local/$KEY_NAME"
            chmod 600 "/root/.ssh_local/$KEY_NAME"

            # Снимаем пароль
            ssh-keygen -p -P "" -N "" -f "/root/.ssh_local/$KEY_NAME" 2>/dev/null || true
        else
            echo "[ERROR] Файл ключа /root/.ssh/$KEY_NAME не найден!"
        fi
    done
fi


# === ШАГ 2: СКАНИРОВАНИЕ И ПРИВЯЗКА К РЕПОЗИТОРИЯМ ===
echo "[INFO] Сканирование /app/workspace на наличие Git-репозиториев..."
cd /app/workspace

for dir in *; do
    if [ -d "$dir/.git" ]; then
        echo "----------------------------------------"
        echo "[INFO] Найдена папка репозитория: $dir"
        
        # Чиним права папки проекта для root, чтобы Git работал без safe.directory
        chown -R root:root "$dir"

        # Ищем, какой ключ задан для этой папки в REPO_KEYS_MAP
        SELECTED_KEY=""
        
        if [ -n "$REPO_KEYS_MAP" ]; then
            # Парсим строку вида "folder1:key1,folder2:key2"
            IFS=',' read -r -a MAP_ARRAY <<< "$REPO_KEYS_MAP"
            for pair in "${MAP_ARRAY[@]}"; do
                pair=$(echo "$pair" | xargs)
                # Разделяем пару по двоеточию
                map_folder="${pair%%:*}"
                map_key="${pair#*:}"
                
                if [ "$map_folder" == "$dir" ]; then
                    SELECTED_KEY="$map_key"
                    break
                fi
            done
        fi

        # Если ключ определен и он физически существует, прописываем его в локальный гит репозитория
        if [ -n "$SELECTED_KEY" ] && [ -f "/root/.ssh_local/$SELECTED_KEY" ]; then
            cd "$dir"
            git config --local core.sshCommand "ssh -F /dev/null -i /root/.ssh_local/${SELECTED_KEY} -o Hostname=ssh.github.com -o Port=443 -o StrictHostKeyChecking=accept-new"
            cd /app/workspace
            echo "[SUCCESS] Репозиторий '$dir' успешно привязан к ключу '$SELECTED_KEY' на порт 443!"
        else
            echo "[WARN] Не удалось найти валидный ключ для репозитория '$dir'. Локальный SSH не настроен."
        fi
    fi
done

echo "----------------------------------------"
# Передаем управление боту
exec "$@"