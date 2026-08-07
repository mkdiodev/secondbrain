from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ui.server import create_app


class FakeFileStorage:
    filename = "dictation.webm"

    def __init__(self, payload: bytes = b"audio") -> None:
        self.payload = payload
        self.saved_path: str | None = None

    def save(self, path: str) -> None:
        self.saved_path = path
        Path(path).write_bytes(self.payload)


class FakeSegment:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeInfo:
    language = "id"
    language_probability = 0.98


class FakeModel:
    def transcribe(self, path: str, **kwargs):
        self.path_seen = path
        self.kwargs_seen = kwargs
        self.path_exists_during_transcribe = Path(path).exists()
        return [FakeSegment(" halo "), FakeSegment(" dunia ")], FakeInfo()


class VoiceTests(unittest.TestCase):
    def test_transcribe_audio_cleans_up_temporary_file(self) -> None:
        from secondbrain import voice

        fake_model = FakeModel()
        storage = FakeFileStorage()

        with patch.dict(
            os.environ,
            {
                "SECONDBRAIN_STT_MODEL": "tiny",
                "SECONDBRAIN_STT_LANGUAGE": "id",
                "SECONDBRAIN_STT_BEAM_SIZE": "9",
                "SECONDBRAIN_STT_INITIAL_PROMPT": "Percakapan dalam bahasa Indonesia.",
                "SECONDBRAIN_STT_HOTWORDS": "litologi collar assay",
            },
            clear=False,
        ), patch.object(voice, "get_stt_model", return_value=fake_model):
            result = voice.transcribe_audio(storage)

        self.assertEqual(result["text"], "halo dunia")
        self.assertEqual(result["language"], "id")
        self.assertEqual(result["language_probability"], 0.98)
        self.assertEqual(result["engine"], "faster-whisper")
        self.assertEqual(result["model"], "tiny")
        self.assertTrue(fake_model.path_exists_during_transcribe)
        self.assertIsNotNone(storage.saved_path)
        self.assertFalse(Path(storage.saved_path).exists())
        self.assertEqual(fake_model.kwargs_seen["vad_filter"], True)
        self.assertEqual(fake_model.kwargs_seen["language"], "id")
        self.assertEqual(fake_model.kwargs_seen["beam_size"], 9)
        self.assertEqual(fake_model.kwargs_seen["temperature"], 0.0)
        self.assertIn("bahasa Indonesia", fake_model.kwargs_seen["initial_prompt"])
        self.assertIn("litologi", fake_model.kwargs_seen["hotwords"])
        self.assertEqual(
            fake_model.kwargs_seen["vad_parameters"]["min_silence_duration_ms"],
            500,
        )

    def test_indonesian_language_alias_and_transcript_spacing(self) -> None:
        from secondbrain.voice import normalize_language, normalize_transcript

        self.assertEqual(normalize_language("id-ID"), "id")
        self.assertEqual(normalize_language("Bahasa Indonesia"), "id")
        self.assertIsNone(normalize_language("auto"))
        self.assertEqual(
            normalize_transcript("  halo   dunia  , apa kabar ? "),
            "halo dunia, apa kabar?",
        )

    def test_voice_endpoint_requires_audio(self) -> None:
        with TemporaryDirectory() as tmp:
            previous = os.environ.get("SECONDBRAIN_WORKSPACE")
            os.environ["SECONDBRAIN_WORKSPACE"] = str(Path(tmp))
            try:
                app, _runtime = create_app()
            finally:
                if previous is None:
                    os.environ.pop("SECONDBRAIN_WORKSPACE", None)
                else:
                    os.environ["SECONDBRAIN_WORKSPACE"] = previous

            response = app.test_client().post("/api/voice/transcribe", data={})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Missing audio file")

    def test_frontend_uses_media_recorder_not_web_speech_api(self) -> None:
        js = Path("ui/static/app.js").read_text(encoding="utf-8")

        self.assertIn("MediaRecorder", js)
        self.assertIn("/api/voice/transcribe", js)
        self.assertIn("noiseSuppression: true", js)
        self.assertIn("echoCancellation: true", js)
        self.assertIn("audioBitsPerSecond: 128000", js)
        self.assertNotIn("SpeechRecognition", js)
        self.assertNotIn("webkitSpeechRecognition", js)


if __name__ == "__main__":
    unittest.main()
