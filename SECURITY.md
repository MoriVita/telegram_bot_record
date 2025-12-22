# Безопасность и конфигурация

## Секретные данные

Все секретные данные (токены, пароли, ID) хранятся в файле `.env`, который **НЕ включен в git**.

## Настройка

1. Создайте файл `.env` в корне проекта:
```bash
touch .env
```

2. Скопируйте содержимое из `.env.example` (создайте его вручную со следующим содержимым):

```
# Токен бота от @BotFather
BOT_TOKEN=your_bot_token_here

# ID администратора в Telegram (получить можно у @userinfobot)
ADMIN_ID=your_admin_id_here
LOG_ADMIN_ID=your_admin_id_here

# Настройки базы данных PostgreSQL
DB_HOST=localhost
DB_PORT=5432
DB_NAME=beauty_bot
DB_USER=postgres
DB_PASSWORD=your_password_here

# Часовой пояс мастера (например: Europe/Moscow, Asia/Yekaterinburg)
MASTER_TIMEZONE=Europe/Moscow
```

3. Заполните все значения своими данными

## Важно

- ⚠️ **НИКОГДА** не коммитьте файл `.env` в git
- ⚠️ Файл `.env` уже добавлен в `.gitignore`
- ✅ Файл `config.py` можно коммитить - в нем нет секретных данных

## Проверка

Запустите скрипт проверки:
```bash
python3 check_setup.py
```

Он проверит наличие всех необходимых переменных в `.env`.
