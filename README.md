# botik

## Запуск

Из корня проекта:

```bash
uv sync
```

Токен бота положи в файл `.env` рядом с `pyproject.toml`:

```bash
TELEGRAM_BOT_TOKEN=123456:telegram-token
```

```bash
uv run botik
```

Напиши боту в личку. Текст сообщения появится в логе процесса. Остановка — Ctrl+C.
