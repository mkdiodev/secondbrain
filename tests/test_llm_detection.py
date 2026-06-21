from __future__ import annotations

import asyncio
import os
import unittest
from unittest.mock import patch

from secondbrain.llm_client import LocalLLMClient
from ui.config import LLMEndpoint, UIConfig


class LLMDetectionTests(unittest.TestCase):
    def test_auto_detects_lm_studio_when_available(self) -> None:
        def detector(candidates):
            return LLMEndpoint(
                provider="lmstudio",
                base_url="http://localhost:1234/v1",
                model="qwen2.5-coder",
            )

        with patch.dict(os.environ, {"SECONDBRAIN_LLM_PROVIDER": "auto"}, clear=True):
            config = UIConfig.from_env(detector=detector)

        self.assertEqual(config.llm_provider, "lmstudio")
        self.assertEqual(config.ollama_base_url, "http://localhost:1234/v1")
        self.assertEqual(config.ollama_model, "qwen2.5-coder")

    def test_explicit_ollama_uses_ollama_env(self) -> None:
        env = {
            "SECONDBRAIN_LLM_PROVIDER": "ollama",
            "OLLAMA_BASE_URL": "http://localhost:11434",
            "OLLAMA_MODEL": "llama3.2",
        }
        with patch.dict(os.environ, env, clear=True):
            config = UIConfig.from_env(detector=lambda candidates: None)

        self.assertEqual(config.llm_provider, "ollama")
        self.assertEqual(config.ollama_base_url, "http://localhost:11434")
        self.assertEqual(config.ollama_model, "llama3.2")

    def test_lm_studio_client_uses_openai_compatible_endpoint(self) -> None:
        captured: dict[str, object] = {}

        class FakeResponse:
            status = 200

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return None

            async def json(self):
                return {"choices": [{"message": {"content": "hello from lm studio"}}]}

        class FakeSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return None

            def post(self, url, json):
                captured["url"] = url
                captured["payload"] = json
                return FakeResponse()

        class FakeAiohttp:
            ClientSession = FakeSession

        with patch.dict("sys.modules", {"aiohttp": FakeAiohttp}):
            client = LocalLLMClient(
                base_url="http://localhost:1234/v1",
                model="qwen2.5-coder",
                provider="lmstudio",
            )
            result = asyncio.run(client.chat([{"role": "user", "content": "hi"}]))

        self.assertEqual(result, "hello from lm studio")
        self.assertEqual(captured["url"], "http://localhost:1234/v1/chat/completions")
        self.assertEqual(captured["payload"]["model"], "qwen2.5-coder")


if __name__ == "__main__":
    unittest.main()
