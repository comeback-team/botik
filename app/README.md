# botik

Бот принимает запрос на сайт в Telegram или MAX, отправляет его в GigaChat и получает не вёрстку, а JSON-инструкцию. HTML из этой инструкции собирается уже в проекте.

Модель заполняет `SiteStructure`: тип бизнеса, тон, цвета и блоки (`header`, `hero`, `features`, `pricing`, `menu`, `interactive` и другие). В ответе запрещены HTML, CSS и JS. Готовая страница — это Jinja-шаблоны блоков плюс скрипт интерактивного блока.

Живой маршрут: сообщение → короткое «all ok» → бриф и JSON Schema в GigaChat → файлы в `var/site-requests/` (запрос, ответ модели, HTML).

## Состав

Корень репозитория поднимает бота и nginx через `compose.yaml`.

- `app/src/botik/adapters/` — Telegram, MAX, GigaChat, Whisper, Mongo, nginx.
- `app/src/botik/app/intake.py` — приём текста и запуск генерации сайта. Это рабочий путь.
- `app/src/botik/app/turn.py` — ход диалога с историей и инструментами. Собирается, но на входящие не подписан.
- `app/src/botik/site/` — промпт и схема запроса, модель инструкции, рендер HTML.
- `app/src/botik/ai_generator.py` — вызов GigaChat и разбор JSON.
- `nginx/` — раздача статики и правил из тома `nginx-rules`.

## Запуск

Из каталога `app`:

```bash
uv sync
```

Токены ботов положи в файл `.env` рядом с `pyproject.toml`. Достаточно одного, можно оба. Для генерации сайта нужен ключ GigaChat.

```bash
TELEGRAM_BOT_TOKEN=123456:telegram-token
MAX_BOT_TOKEN=max-token
GIGACHAT_CREDENTIALS=ключ
```

```bash
uv run botik
```

Напиши боту в Telegram или MAX. Остановка — Ctrl+C.
