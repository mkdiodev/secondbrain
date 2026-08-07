"""Local/offline voice dictation backed by faster-whisper."""

from __future__ import annotations

import os
import re
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any


DEFAULT_INDONESIAN_PROMPT = (
    "Percakapan dalam bahasa Indonesia dengan asisten AI lokal. Topik mencakup "
    "workspace, file, folder, basis data SQL Server, query, konfigurasi JSON, "
    "validasi drillhole, collar, survey, assay, litologi, dan kedalaman."
)
DEFAULT_INDONESIAN_HOTWORDS = (
    "SecondBrain Ollama LM Studio workspace SQL Server query database JSON userConfig "
    "drillhole collar survey assay lithology litologi geotech RQD"
)
INDONESIAN_LANGUAGE_ALIASES = {
    "bahasa",
    "bahasa-indonesia",
    "bahasa indonesia",
    "id",
    "id-id",
    "indonesia",
    "indonesian",
}


class VoiceTranscriptionError(RuntimeError):
    """Raised when local voice transcription cannot be completed."""


def _get_env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return max(minimum, min(value, maximum))


def _get_env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        return default
    return max(minimum, min(value, maximum))


def _get_optional_env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip() or None


def normalize_language(language: str | None) -> str | None:
    if language is None:
        return None
    normalized = language.strip().lower().replace("_", "-")
    if not normalized or normalized == "auto":
        return None
    if normalized in INDONESIAN_LANGUAGE_ALIASES:
        return "id"
    return normalized.split("-", 1)[0]


def transcription_options(language: str | None) -> dict[str, Any]:
    is_indonesian = language == "id"
    prompt = _get_optional_env(
        "SECONDBRAIN_STT_INITIAL_PROMPT",
        DEFAULT_INDONESIAN_PROMPT if is_indonesian else None,
    )
    hotwords = _get_optional_env(
        "SECONDBRAIN_STT_HOTWORDS",
        DEFAULT_INDONESIAN_HOTWORDS if is_indonesian else None,
    )

    options: dict[str, Any] = {
        "language": language,
        "beam_size": _get_env_int("SECONDBRAIN_STT_BEAM_SIZE", 8, 1, 20),
        "patience": _get_env_float("SECONDBRAIN_STT_PATIENCE", 1.2, 1.0, 2.0),
        "temperature": 0.0,
        "condition_on_previous_text": True,
        "vad_filter": True,
        "vad_parameters": {
            "threshold": _get_env_float("SECONDBRAIN_STT_VAD_THRESHOLD", 0.45, 0.1, 0.9),
            "min_speech_duration_ms": _get_env_int(
                "SECONDBRAIN_STT_VAD_MIN_SPEECH_MS", 150, 0, 2000
            ),
            "min_silence_duration_ms": _get_env_int(
                "SECONDBRAIN_STT_VAD_MIN_SILENCE_MS", 500, 100, 5000
            ),
            "speech_pad_ms": _get_env_int(
                "SECONDBRAIN_STT_VAD_SPEECH_PAD_MS", 400, 0, 2000
            ),
        },
    }
    if prompt:
        options["initial_prompt"] = prompt
    if hotwords:
        options["hotwords"] = hotwords
    return options


def normalize_transcript(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"\s+([,.;:!?])", r"\1", text)


@lru_cache(maxsize=1)
def get_stt_model() -> Any:
    model_name = os.getenv("SECONDBRAIN_STT_MODEL", "medium").strip() or "medium"
    device = os.getenv("SECONDBRAIN_STT_DEVICE", "cpu").strip() or "cpu"
    compute_type = os.getenv("SECONDBRAIN_STT_COMPUTE_TYPE", "int8").strip() or "int8"

    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise VoiceTranscriptionError(
            "faster-whisper is not installed. Install it with: pip install faster-whisper"
        ) from exc

    return WhisperModel(
        model_name,
        device=device,
        compute_type=compute_type,
    )


def transcribe_audio(file_storage: Any, language: str | None = None) -> dict[str, Any]:
    if file_storage is None:
        raise VoiceTranscriptionError("Missing audio file.")

    model_name = os.getenv("SECONDBRAIN_STT_MODEL", "medium").strip() or "medium"
    default_language = os.getenv("SECONDBRAIN_STT_LANGUAGE", "id").strip()
    selected_language = normalize_language(language if language is not None else default_language)
    suffix = Path(getattr(file_storage, "filename", "") or "audio.webm").suffix or ".webm"
    tmp_path = ""

    content_length = getattr(file_storage, "content_length", None)
    max_seconds = _get_env_int("SECONDBRAIN_STT_MAX_SECONDS", 60, 5, 300)
    max_upload_bytes = max_seconds * 512 * 1024
    if content_length and content_length > max_upload_bytes:
        raise VoiceTranscriptionError("Audio upload is too large for local transcription.")

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = tmp.name
        file_storage.save(tmp_path)
        upload_size = Path(tmp_path).stat().st_size
        if upload_size <= 0:
            raise VoiceTranscriptionError("Audio upload is empty.")
        if upload_size > max_upload_bytes:
            raise VoiceTranscriptionError("Audio upload is too large for local transcription.")

        model = get_stt_model()
        segments, info = model.transcribe(tmp_path, **transcription_options(selected_language))
        text = normalize_transcript(" ".join(segment.text.strip() for segment in segments))
        return {
            "text": text,
            "language": getattr(info, "language", selected_language),
            "language_probability": getattr(info, "language_probability", None),
            "engine": os.getenv("SECONDBRAIN_STT_ENGINE", "faster-whisper"),
            "model": model_name,
        }
    except VoiceTranscriptionError:
        raise
    except Exception as exc:
        raise VoiceTranscriptionError(f"Voice transcription failed: {exc}") from exc
    finally:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
