## Aider agent

Позволяет работать с aider как с ии агентом. 

## Установка

Клонируем
```
cd ~
git clone {ссылка_на_репозиторий}
```

## Управление правами к репозиторию

Копируем приватные ключи всех репозиториев, в ~/.ssh из github

Настраиваем ssh для подключения по 443 порту к гитхабу
```
nano ~/.ssh

Host github.com
    Hostname ssh.github.com
    Port 443
    User git
```

Скопируйте пропишите ваши секреты в .env

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
docker compose up --build
```


Клонируем репозитории
```
docker exec -it aider_agent /bin/bash

# убедись, что ssh ключ пробросился в /root/.ssh
ls -la ~/.ssh

git clone {ссылка_на_проект_через_ssh}
```


## Работа с ботом

Для скачивания дизайна с figma используйте скрипт exportSelectedContext.js из репозитория https://github.com/vershiny-top/how-to-generate-figma-design