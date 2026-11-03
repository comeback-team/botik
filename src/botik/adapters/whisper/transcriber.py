"""Локальная транскрибация через work_table/transcribation.py.

Вызов блокирует CPU, поэтому он уходит в поток. Исходный файл не удаляется.
"""

import asyncio
import importlib.util
from pathlib import Path
from types import ModuleType

_MODULE: ModuleType | None = None


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
        return await asyncio.to_thread(
            _transcribe,
            path,
            self._model_size,
            self._language,
            self._denoise,
        )


def _transcribe(path: Path, model_size: str, language: str | None, denoise: bool) -> str:
    module = _load()
    return module.transcribe(
        str(path),
        model_size=model_size,
        language=language,
        denoise=denoise,
    )


def _load() -> ModuleType:
    global _MODULE
    if _MODULE is not None:
        return _MODULE
    path = _module_path()
    spec = importlib.util.spec_from_file_location("work_table_transcribation", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _MODULE = module
    return module


def _module_path() -> Path:
    candidates = (
        Path.cwd() / "work_table" / "transcribation.py",
        Path(__file__).resolve().parents[4] / "work_table" / "transcribation.py",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("work_table/transcribation.py")
