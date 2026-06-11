FROM python:3.10-slim

# Ставим системные зависимости (обязательно openssh-client)
RUN apt-get update && apt-get install -y \
    git \
    openssh-client \
    bash \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Твоя установка пакетов
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Наглухо отключаем паранойю гит-владения для root внутри контейнера
RUN git config --global safe.directory "*"

# Копируем и даем права скрипту точки входа
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

WORKDIR /app/workspace