# 🛰 Telegram NOTAM & NAVAREA Bot

Бот отслеживает актуальные резервации воздушного и морского пространства и присылает уведомления в Telegram каждый час.

## 📡 Источники данных
- **FAA NOTAM** — воздушные резервации (ракетные пуски, военные учения, NASA, SpaceX и др.)
- **NAVAREA (NGA MSI)** — морские резервации (ракетные пуски, военно-морские учения)

## 📬 Что присылает бот
Каждое уведомление содержит:
- Тип резервации: ✈️ Воздушная / 🌊 Морская
- Источник и ID
- Зона / полигон запуска
- Временное окно (начало → конец)
- Краткое описание
- Координаты для копирования

---

## 🚀 Установка и запуск

### 1. Клонируй репозиторий
```bash
git clone https://github.com/ТВО_ИМЯ/telegram-notam-bot.git
cd telegram-notam-bot
```

### 2. Установи зависимости
```bash
pip install -r requirements.txt
```

### 3. Настрой переменные окружения
Создай файл `.env` (скопируй из `.env.example`):
```bash
cp .env.example .env
```

Заполни:
```
BOT_TOKEN=токен_от_BotFather
CHAT_ID=твой_chat_id
```

**Как получить BOT_TOKEN:**
1. Открой Telegram → найди `@BotFather`
2. Напиши `/newbot`
3. Следуй инструкциям → получишь токен

**Как получить CHAT_ID:**
1. Найди `@userinfobot` в Telegram
2. Напиши ему что угодно → он пришлёт твой ID

**FAA API ключи (опционально):**
Зарегистрируйся на https://api.faa.gov/ для повышенного лимита запросов

### 4. Запусти бота
```bash
python bot.py
```

---

## ☁️ Деплой на сервер (рекомендуется)

Для постоянной работы бота нужен сервер. Варианты:
- **Railway.app** — бесплатно, легко
- **Render.com** — бесплатный план
- **VPS** (DigitalOcean, Hetzner и т.д.)

### Railway (самый простой способ)
1. Зайди на https://railway.app
2. Подключи GitHub репозиторий
3. В настройках добавь переменные окружения (BOT_TOKEN, CHAT_ID)
4. Deploy!

### Переменные окружения в GitHub
Если используешь GitHub Actions (`.github/workflows/deploy.yml`):
1. GitHub репозиторий → Settings → Secrets and variables → Actions
2. Добавь: `BOT_TOKEN`, `CHAT_ID`, `FAA_CLIENT_ID`, `FAA_CLIENT_SECRET`

---

## 🤖 Команды бота
| Команда | Описание |
|---------|----------|
| `/start` | Приветствие и список команд |
| `/check` | Получить резервации прямо сейчас |
| `/help` | Справка |

---

## 📁 Структура проекта
```
telegram-notam-bot/
├── bot.py          # Основной файл бота
├── fetcher.py      # Получение данных FAA + NAVAREA
├── formatter.py    # Форматирование сообщений
├── requirements.txt
├── .env.example
└── .github/
    └── workflows/
        └── deploy.yml
```
