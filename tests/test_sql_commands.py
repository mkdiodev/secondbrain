from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from secondbrain.skills.sql_server_skill import SqlColumn, SqlQueryResult
from ui.config import UIConfig
from ui.runtime import ChatRuntime


class FakeSqlAdapter:
    def __init__(self) -> None:
        self.query_calls: list[str] = []

    def fetch_schema(self, connection_string: str, profile) -> list[SqlColumn]:
        return [
            SqlColumn(schema="dbo", table="customers", column="id", data_type="int"),
            SqlColumn(schema="dbo", table="customers", column="name", data_type="nvarchar"),
        ]

    def execute_query(self, connection_string: str, sql: str, timeout_seconds: int) -> SqlQueryResult:
        self.query_calls.append(sql)
        return SqlQueryResult(
            columns=["id", "name"],
            rows=[{"id": 1, "name": "Ada"}],
            sql=sql,
            row_count=1,
            truncated=False,
        )


class FakeLLM:
    base_url = "fake://local"
    model = "fake-model"

    def __init__(self, replies: list[str]):
        self.replies = replies
        self.calls: list[list[dict[str, str]]] = []

    async def chat(self, messages: list[dict[str, str]], temperature: float = 0.7) -> str:
        self.calls.append(messages)
        if not self.replies:
            return "fallback reply"
        return self.replies.pop(0)


class SqlCommandTests(unittest.TestCase):
    def _runtime(self, workspace: Path, replies: list[str] | None = None) -> tuple[ChatRuntime, FakeSqlAdapter]:
        env = {
            "SECOND_BRAIN_SQL_PROFILES": (
                '{"default":{"connection_env":"SECOND_BRAIN_SQL_DEFAULT_CONNECTION",'
                '"schemas":["dbo"],"max_rows":25,"timeout_seconds":5}}'
            ),
            "SECOND_BRAIN_SQL_DEFAULT_CONNECTION": "Server=localhost;Database=test;UID=reader;PWD=secret;",
        }
        patcher = patch.dict(os.environ, env, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        adapter = FakeSqlAdapter()
        llm = FakeLLM(replies or [])
        config = UIConfig(
            workspace=str(workspace),
            ollama_base_url="http://localhost:11434",
            ollama_model="gemma4:e2b",
        )
        return ChatRuntime(config, llm=llm, sql_adapter=adapter), adapter

    def test_sql_profiles_command_hides_secret(self) -> None:
        with TemporaryDirectory() as tmp:
            runtime, _adapter = self._runtime(Path(tmp))

            result = runtime.handle_message("/sql profiles")

            self.assertEqual(result["kind"], "sql")
            self.assertIn("default", result["reply"])
            self.assertNotIn("secret", result["reply"])
            self.assertNotIn("PWD", result["reply"])

    def test_sql_schema_command_refreshes_cache(self) -> None:
        with TemporaryDirectory() as tmp:
            runtime, _adapter = self._runtime(Path(tmp))

            result = runtime.handle_message("/sql schema default --refresh")

            self.assertEqual(result["kind"], "sql")
            self.assertIn("dbo.customers", result["reply"])
            self.assertIn("id", result["reply"])

    def test_sql_run_command_executes_safe_select(self) -> None:
        with TemporaryDirectory() as tmp:
            runtime, adapter = self._runtime(Path(tmp))
            runtime.handle_message("/sql schema default --refresh")

            result = runtime.handle_message("/sql run default SELECT id, name FROM dbo.customers")

            self.assertEqual(result["kind"], "sql")
            self.assertIn("Ada", result["reply"])
            self.assertIn("TOP (25)", adapter.query_calls[0])

    def test_sql_run_command_rejects_drop(self) -> None:
        with TemporaryDirectory() as tmp:
            runtime, adapter = self._runtime(Path(tmp))
            runtime.handle_message("/sql schema default --refresh")

            result = runtime.handle_message("/sql run default DROP TABLE dbo.customers")

            self.assertIn("error", result)
            self.assertEqual(adapter.query_calls, [])

    def test_natural_language_sql_uses_read_only_tool(self) -> None:
        with TemporaryDirectory() as tmp:
            runtime, adapter = self._runtime(
                Path(tmp),
                replies=[
                    '{"tool":"query_sql_server","profile":"default","question":"show customers"}',
                    '{"sql":"SELECT id, name FROM dbo.customers"}',
                    "I found Ada.",
                ],
            )
            runtime.handle_message("/sql schema default --refresh")

            result = runtime.handle_message("query database tampilkan customers")

            self.assertEqual(result["kind"], "tool-chat")
            self.assertEqual(result["tools"][0]["tool"], "query_sql_server")
            self.assertIn("Ada", result["reply"])
            self.assertIn("TOP (25)", adapter.query_calls[0])


if __name__ == "__main__":
    unittest.main()
