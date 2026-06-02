FROM python:3.10-slim

# Ставим системные зависимости
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем requirements.txt и устанавливаем python-пакеты
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Указываем рабочую директорию для самого кода
WORKDIR /app/workspace