"""Локальная транскрибация. Модель крутится на этой машине, не по API."""

from pathlib import Path
from typing import Protocol


class Transcriber(Protocol):
    async def transcribe(self, path: Path) -> str:
        """Файл .ogg, .oga или .opus уже лежит на диске. Вернуть текст речи.

        Вызов блокирует CPU. Адаптер уводит его с event loop.
        Исходный файл не удаляет: им владеет канал, который его скачал.
        """
        ...
