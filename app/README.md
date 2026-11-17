# botik

## Запуск

Из корня проекта:

```bash
uv sync
```

Токены ботов положи в файл `.env` рядом с `pyproject.toml`. Достаточно одного, можно оба:

```bash
TELEGRAM_BOT_TOKEN=123456:telegram-token
MAX_BOT_TOKEN=max-token
```

```bash
uv run botik
```

Напиши боту в Telegram или MAX: текст, голосовое или картинку. Строка появится в логе процесса. Остановка — Ctrl+C.
