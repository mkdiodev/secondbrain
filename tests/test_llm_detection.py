from __future__ import annotations

import asyncio
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from secondbrain.llm_client import LocalLLMClient
from secondbrain.skills.sql_server_skill import SqlServerSkill
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

    def test_ui_config_loads_local_dotenv_for_ui_and_sql(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env").write_text(
                "\n".join(
                    [
                        "SECONDBRAIN_UI_PORT=3999",
                        "SECOND_BRAIN_SQL_DEFAULT_CONNECTION=Server=localhost;Database=test;UID=reader;PWD=secret;",
                    ]
                ),
                encoding="utf-8",
            )
            old_cwd = Path.cwd()
            try:
                os.chdir(root)
                with patch.dict(os.environ, {}, clear=True):
                    config = UIConfig.from_env(detector=lambda candidates: None)
                    sql = SqlServerSkill.from_env()
            finally:
                os.chdir(old_cwd)

        self.assertEqual(config.port, 3999)
        self.assertIn("default", sql.profiles)
        self.assertEqual(sql.profiles["default"].connection_env, "SECOND_BRAIN_SQL_DEFAULT_CONNECTION")

    def test_ui_config_loads_project_dotenv_even_when_cwd_differs(self) -> None:
        env_path = Path(r"D:\CodexProject\secondbrain\.env")
        original = env_path.read_text(encoding="utf-8") if env_path.exists() else None
        with TemporaryDirectory() as tmp:
            other_cwd = Path(tmp)
            env_path.write_text(
                "\n".join(
                    [
                        "SECONDBRAIN_UI_PORT=4555",
                        "SECOND_BRAIN_SQL_DEFAULT_CONNECTION=Server=localhost;Database=test;Trusted_Connection=yes;Encrypt=yes;TrustServerCertificate=yes",
                    ]
                ),
                encoding="utf-8",
            )
            old_cwd = Path.cwd()
            try:
                os.chdir(other_cwd)
                with patch.dict(os.environ, {}, clear=True):
                    config = UIConfig.from_env(detector=lambda candidates: None)
                    sql = SqlServerSkill.from_env()
            finally:
                os.chdir(old_cwd)
                if original is None:
                    env_path.unlink(missing_ok=True)
                else:
                    env_path.write_text(original, encoding="utf-8")

        self.assertEqual(config.port, 4555)
        self.assertIn("default", sql.profiles)
        self.assertEqual(sql.profiles["default"].connection_env, "SECOND_BRAIN_SQL_DEFAULT_CONNECTION")

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

    def test_client_returns_only_final_channel_text(self) -> None:
        raw_reply = """<|channel>thought
Thinking Process:

1. Analyze the request.
<channel|>Hello. How may I assist you today?"""

        class FakeResponse:
            status = 200

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return None

            async def json(self):
                return {"message": {"content": raw_reply}}

        class FakeSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return None

            def post(self, url, json):
                return FakeResponse()

        class FakeAiohttp:
            ClientSession = FakeSession

        with patch.dict("sys.modules", {"aiohttp": FakeAiohttp}):
            client = LocalLLMClient()
            result = asyncio.run(client.chat([{"role": "user", "content": "hallo"}]))

        self.assertEqual(result, "Hello. How may I assist you today?")


if __name__ == "__main__":
    unittest.main()
