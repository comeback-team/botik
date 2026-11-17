"""Локальная транскрибация .ogg / .oga / .opus через faster-whisper.

Вызов блокирует CPU, поэтому он уходит в поток. Исходный файл не удаляется.
"""

import asyncio
import logging
import tempfile
from pathlib import Path

import noisereduce as nr
import numpy as np
import soundfile as sf
from faster_whisper import WhisperModel
from pydub import AudioSegment

logger = logging.getLogger(__name__)

_ALLOWED = {".ogg", ".oga", ".opus"}
_MAX_FILE_SIZE_MB = 100
_MAX_DURATION_SEC = 600
_MODELS: dict[str, WhisperModel] = {}


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
            transcribe,
            path,
            model_size=self._model_size,
            language=self._language,
            denoise=self._denoise,
        )


def transcribe(
    path: Path,
    *,
    model_size: str = "small",
    language: str | None = None,
    denoise: bool = False,
) -> str:
    """Вернуть текст речи из файла .ogg, .oga или .opus."""

    _validate(path)
    model = _model(model_size)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        cleaned = Path(tmp.name)
    try:
        _clean(path, cleaned, denoise=denoise)
        duration = sf.info(cleaned).duration
        if duration > _MAX_DURATION_SEC:
            raise ValueError(
                f"Аудио слишком длинное: {duration:.0f} сек (лимит {_MAX_DURATION_SEC} сек)"
            )
        audio, _sample_rate = sf.read(cleaned, dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        segments, info = model.transcribe(
            audio,
            language=language,
            beam_size=5,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
            condition_on_previous_text=False,
        )
        logger.info(
            "язык=%s уверенность=%.1f длительность=%.1f",
            info.language,
            info.language_probability * 100,
            info.duration,
        )
        return " ".join(segment.text.strip() for segment in segments if segment.text.strip())
    finally:
        cleaned.unlink(missing_ok=True)


def _model(model_size: str) -> WhisperModel:
    if model_size not in _MODELS:
        logger.info("загружаю модель whisper %s", model_size)
        _MODELS[model_size] = WhisperModel(model_size, device="cpu", compute_type="int8")
    return _MODELS[model_size]


def _clean(source: Path, output: Path, *, denoise: bool) -> None:
    audio = AudioSegment.from_file(source)
    audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)
    audio.export(output, format="wav")

    data, sample_rate = sf.read(output, dtype="float32")
    if data.ndim > 1:
        data = data.mean(axis=1)
    if denoise:
        data = nr.reduce_noise(y=data, sr=sample_rate, stationary=False, prop_decrease=0.6)
    peak = np.max(np.abs(data))
    if peak > 0:
        data = data / peak * 0.9
    sf.write(output, data, sample_rate, subtype="PCM_16")


def _validate(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Файл не найден: {path}")
    if path.suffix.lower() not in _ALLOWED:
        allowed = ", ".join(sorted(_ALLOWED))
        raise ValueError(f"Неподдерживаемое расширение '{path.suffix}'. Ожидается: {allowed}")
    size_mb = path.stat().st_size / (1024 * 1024)
    if size_mb > _MAX_FILE_SIZE_MB:
        raise ValueError(f"Файл слишком большой: {size_mb:.1f} МБ (лимит {_MAX_FILE_SIZE_MB} МБ)")
