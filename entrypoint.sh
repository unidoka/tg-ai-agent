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


# === ШАГ 2: СКАНИРОВАНИЕ И КОНФИГУРАЦИЯ РЕПОЗИТОРИЕВ ===
echo "[INFO] Сканирование /app/workspace на наличие Git-репозиториев..."
cd /app/workspace

for dir in *; do
    if [ -d "$dir/.git" ]; then
        echo "----------------------------------------"
        echo "[INFO] Найдена папка репозитория: $dir"
        
        # Чиним права папки проекта для root, чтобы Git работал без safe.directory
        chown -R root:root "$dir"

        SELECTED_KEY=""
        SELECTED_BRANCH=""
        
        # Парсим REPO_KEYS_MAP (формат: folder:key:branch)
        if [ -n "$REPO_KEYS_MAP" ]; then
            IFS=',' read -r -a MAP_ARRAY <<< "$REPO_KEYS_MAP"
            for pair in "${MAP_ARRAY[@]}"; do
                pair=$(echo "$pair" | xargs)
                
                # Извлекаем компоненты структуры folder:key:branch
                map_folder=$(echo "$pair" | cut -d':' -f1)
                map_key=$(echo "$pair" | cut -d':' -f2)
                map_branch=$(echo "$pair" | cut -d':' -f3)
                
                if [ "$map_folder" == "$dir" ]; then
                    SELECTED_KEY="$map_key"
                    SELECTED_BRANCH="$map_branch"
                    break
                fi
            done
        fi

        # Дефолтный фоллбэк для ключа, если папки нет в маппинге
        if [ -z "$SELECTED_KEY" ] && [ -n "$SSH_KEYS" ]; then
            SELECTED_KEY=$(echo "$SSH_KEYS" | cut -d',' -f1 | xargs)
            echo "[INFO] Используем дефолтный ключ для '$dir': $SELECTED_KEY"
        fi

        # Дефолтный фоллбэк для ветки (если не указана, пусть будет main)
        if [ -z "$SELECTED_BRANCH" ]; then
            SELECTED_BRANCH="main"
        fi

        # 1. Применяем настройки SSH для Git
        if [ -n "$SELECTED_KEY" ] && [ -f "/root/.ssh_local/$SELECTED_KEY" ]; then
            cd "$dir"
            git config --local core.sshCommand "ssh -F /dev/null -i /root/.ssh_local/${SELECTED_KEY} -o Hostname=ssh.github.com -o Port=443 -o StrictHostKeyChecking=accept-new"
            echo "[SUCCESS] Репозиторий '$dir' успешно привязан к ключу '$SELECTED_KEY' (Порт 443)"
            
            # 2. Конфигурируем и переключаем ветку
            echo "[INFO] Проверка ветки для '$dir'. Целевая ветка: $SELECTED_BRANCH"
            
            # Получаем имя текущей активной ветки
            CURRENT_BRANCH=$(git branch --show-current 2>/dev/null || echo "")
            
            if [ "$CURRENT_BRANCH" != "$SELECTED_BRANCH" ]; then
                echo "[INFO] Текущая ветка '$CURRENT_BRANCH' отличается от целевой '$SELECTED_BRANCH'. Переключаем..."
                
                # Пытаемся переключиться на ветку, если она локально существует. 
                # Если её нет — создаем новую от текущего места.
                git checkout "$SELECTED_BRANCH" 2>/dev/null || git checkout -b "$SELECTED_BRANCH"
                echo "[SUCCESS] Ветка переключена на '$(git branch --show-current)'"
            else
                echo "[INFO] Репозиторий уже находится на ветке '$SELECTED_BRANCH'"
            fi
            
            cd /app/workspace
        else
            echo "[WARN] Не удалось настроить локальный SSH для '$dir' (ключ не найден)."
        fi
    fi
done

echo "----------------------------------------"
# Передаем управление боту
exec "$@"