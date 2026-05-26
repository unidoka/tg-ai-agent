FROM python:3.10-slim

# Устанавливаем Node.js, git и зависимости для сборки npm пакетов
RUN apt-get update && apt-get install -y \
    curl \
    git \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем figma-developer-mcp глобально
RUN npm install -g figma-developer-mcp

# Устанавливаем Aider и необходимые Python библиотеки
RUN pip install --no-cache-dir \
    aider-chat \
    requests \
    python-dotenv \
    pyyaml

WORKDIR /app

# По умолчанию контейнер ничего не делает, логику запуска опишем в Compose
CMD ["bash"]
