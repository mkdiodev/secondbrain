"""Local/offline voice dictation backed by faster-whisper."""

from __future__ import annotations

import os
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any


class VoiceTranscriptionError(RuntimeError):
    """Raised when local voice transcription cannot be completed."""


def _get_env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@lru_cache(maxsize=1)
def get_stt_model() -> Any:
    model_name = os.getenv("SECONDBRAIN_STT_MODEL", "small").strip() or "small"
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

    model_name = os.getenv("SECONDBRAIN_STT_MODEL", "small").strip() or "small"
    default_language = os.getenv("SECONDBRAIN_STT_LANGUAGE", "id").strip()
    selected_language = language if language is not None else default_language
    suffix = Path(getattr(file_storage, "filename", "") or "audio.webm").suffix or ".webm"
    tmp_path = ""

    content_length = getattr(file_storage, "content_length", None)
    max_seconds = _get_env_int("SECONDBRAIN_STT_MAX_SECONDS", 60)
    max_upload_bytes = max_seconds * 512 * 1024
    if content_length and content_length > max_upload_bytes:
        raise VoiceTranscriptionError("Audio upload is too large for local transcription.")

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp_path = tmp.name
        file_storage.save(tmp_path)

    try:
        model = get_stt_model()
        whisper_language = None if selected_language in ("", "auto", None) else selected_language
        segments, info = model.transcribe(
            tmp_path,
            language=whisper_language,
            beam_size=5,
            vad_filter=True,
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
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
