"""Место под локальный faster-whisper.

Будущая реализация повторяет temp.transcribation.py и из этого модуля не торчит:
ogg/oga/opus до 100 МБ и 10 минут, перевод в wav 16 кГц mono, шумоподавление
выключено, модель small на cpu/int8 загружается один раз, текст сегментов
склеивается через пробел. Отсюда наружу — async-обёртка над этой синхронной функцией.
"""

from pathlib import Path


class WhisperTranscriber:
    def __init__(
        self,
        *,
        model_size: str = "small",
        language: str | None = None,
        denoise: bool = False,
    ) -> None:
        self._model_size = model_size
        self._language = language
        self._denoise = denoise

    async def transcribe(self, path: Path) -> str:
        del path
        raise NotImplementedError("local whisper transcription is not implemented")
