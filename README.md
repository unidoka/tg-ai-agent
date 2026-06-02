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

Настройка прокси
```
cp xray_config.json.example xray_config.json
Открой файл xray_config.json и в массив "outbounds" вставь конфигурацию своего рабочего прокси (VLESS / Reality / Shadowsocks).
```

Запуск
```
docker compose up -d --build
```


## Работа с ботом

/list для просмотра команд

Для скачивания дизайна с figma используйте скрипт exportSelectedContext.js из репозитория https://github.com/vershiny-top/how-to-generate-figma-design