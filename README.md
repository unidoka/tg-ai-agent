## Aider agent

Позволяет работать с aider как с ии агентом. 

## Установка

Клонируем
```
cd ~
git clone {ссылка_на_репозиторий}
```

Пропишите ваши секреты в .env
```
cp .env.example .env
nano .env
```

Запуск aider
```
docker compose up -d mcp-server
cd {ваша_папка_с_проектом}
docker compose -f {папка_с_репозиторием}/docker-compose.yml run -T --rm aider-agent python3 /app/scripts/test_figma.py "Сверстай секцию, используя tailwind" "ссылка_блока"
```
