"""Локальная транскрибация .ogg / .oga / .opus через faster-whisper."""

import logging
import os
import tempfile
from pathlib import Path

import noisereduce as nr
import numpy as np
import soundfile as sf
from faster_whisper import WhisperModel
from pydub import AudioSegment

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".ogg", ".oga", ".opus"}
MAX_FILE_SIZE_MB = 100
MAX_DURATION_SEC = 600

_MODELS: dict[str, WhisperModel] = {}


def get_model(model_size: str = "small") -> WhisperModel:
    """Загружает модель один раз и переиспользует её."""
    if model_size not in _MODELS:
        logger.info("Загружаю модель Whisper: %s", model_size)
        _MODELS[model_size] = WhisperModel(
            model_size,
            device="cpu",
            compute_type="int8",
        )
    return _MODELS[model_size]


def clean_audio(audio_path: str, output_path: str, denoise: bool = False) -> str:
    """OGG/Opus -> WAV 16 кГц mono и пиковая нормализация. Шумоподавление по запросу."""
    audio = AudioSegment.from_file(audio_path)
    audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)
    audio.export(output_path, format="wav")

    data, sample_rate = sf.read(output_path, dtype="float32")
    if data.ndim > 1:
        data = data.mean(axis=1)

    if denoise:
        logger.info("Применяю шумоподавление")
        data = nr.reduce_noise(
            y=data,
            sr=sample_rate,
            stationary=False,
            prop_decrease=0.6,
        )

    peak = np.max(np.abs(data))
    if peak > 0:
        data = data / peak * 0.9

    sf.write(output_path, data, sample_rate, subtype="PCM_16")
    return output_path


def transcribe(
    file_path: str,
    model_size: str = "small",
    language: str | None = None,
    denoise: bool = False,
) -> str:
    """Вернуть текст речи из файла .ogg, .oga или .opus."""
    _validate_input(file_path)
    model = get_model(model_size)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        cleaned_path = tmp.name

    try:
        logger.info("Очищаю звук: %s", file_path)
        clean_audio(file_path, cleaned_path, denoise=denoise)

        wav_info = sf.info(cleaned_path)
        if wav_info.duration > MAX_DURATION_SEC:
            raise ValueError(
                f"Аудио слишком длинное: {wav_info.duration:.0f} сек "
                f"(лимит {MAX_DURATION_SEC} сек)"
            )

        logger.info("Транскрибирую")
        audio_array, _sample_rate = sf.read(cleaned_path, dtype="float32")
        if audio_array.ndim > 1:
            audio_array = audio_array.mean(axis=1)

        segments, info = model.transcribe(
            audio_array,
            language=language,
            beam_size=5,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
            condition_on_previous_text=False,
        )
        logger.info(
            "Язык: %s (уверенность %.1f%%), длительность %.1f сек",
            info.language,
            info.language_probability * 100,
            info.duration,
        )
        return " ".join(segment.text.strip() for segment in segments if segment.text.strip())
    finally:
        if os.path.exists(cleaned_path):
            os.unlink(cleaned_path)


def _validate_input(file_path: str) -> None:
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"Файл не найден: {file_path}")

    ext = Path(file_path).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Неподдерживаемое расширение '{ext}'. "
            f"Ожидается: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    size_mb = os.path.getsize(file_path) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise ValueError(
            f"Файл слишком большой: {size_mb:.1f} МБ (лимит {MAX_FILE_SIZE_MB} МБ)"
        )
