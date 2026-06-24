from __future__ import annotations

import os
import json
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
        self.table_count = 1
        self.rows = [{"id": 1, "name": "Ada"}]
        self.columns = ["id", "name"]

    def fetch_schema(self, connection_string: str, profile) -> list[SqlColumn]:
        columns = []
        for index in range(self.table_count):
            table = "customers" if index == 0 else f"extra_{index}"
            columns.extend(
                [
                    SqlColumn(schema="dbo", table=table, column="id", data_type="int"),
                    SqlColumn(schema="dbo", table=table, column="name", data_type="nvarchar"),
                    SqlColumn(schema="dbo", table=table, column="END_DEPTH", data_type="decimal"),
                ]
            )
        return columns

    def execute_query(self, connection_string: str, sql: str, timeout_seconds: int) -> SqlQueryResult:
        self.query_calls.append(sql)
        if "GB_SITE_SURVEY" in sql:
            return SqlQueryResult(
                columns=["EASTING", "NORTHING", "ELEVATION"],
                rows=[{"EASTING": "100.1", "NORTHING": "200.2", "ELEVATION": "12.3"}],
                sql=sql,
                row_count=1,
                truncated=False,
            )
        if "GB_SITE" in sql:
            return SqlQueryResult(
                columns=["END_DEPTH", "BIT_COEFFICIENT"],
                rows=[{"END_DEPTH": "12.70", "BIT_COEFFICIENT": "0.889"}],
                sql=sql,
                row_count=1,
                truncated=False,
            )
        return SqlQueryResult(
            columns=self.columns,
            rows=self.rows,
            sql=sql,
            row_count=len(self.rows),
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

    def test_sql_schema_command_returns_compact_summary(self) -> None:
        with TemporaryDirectory() as tmp:
            runtime, adapter = self._runtime(Path(tmp))
            adapter.table_count = 80

            result = runtime.handle_message("/sql schema default --refresh")

            self.assertEqual(result["kind"], "sql")
            self.assertIn("Tables/views: 80", result["reply"])
            self.assertIn("dbo.customers", result["reply"])
            self.assertNotIn("dbo.extra_79", result["reply"])
            self.assertIn("more tables/views", result["reply"])

    def test_sql_run_command_executes_safe_select(self) -> None:
        with TemporaryDirectory() as tmp:
            runtime, adapter = self._runtime(Path(tmp))
            runtime.handle_message("/sql schema default --refresh")

            result = runtime.handle_message("/sql run default SELECT id, name FROM dbo.customers")

            self.assertEqual(result["kind"], "sql")
            self.assertIn("Ada", result["reply"])
            self.assertEqual(result["sql_result"]["columns"], ["id", "name"])
            self.assertEqual(result["sql_result"]["rows"], [{"id": 1, "name": "Ada"}])
            self.assertEqual(result["sql_result"]["row_count"], 1)
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
            self.assertEqual(result["sql_result"]["columns"], ["id", "name"])
            self.assertEqual(result["sql_result"]["rows"], [{"id": 1, "name": "Ada"}])
            self.assertIn("Ada", result["reply"])
            self.assertIn("TOP (25)", adapter.query_calls[0])

    def test_site_id_question_uses_sql_tool_and_returns_answer(self) -> None:
        with TemporaryDirectory() as tmp:
            runtime, adapter = self._runtime(
                Path(tmp),
                replies=[
                    '{"tool":"query_sql_server","profile":"default","question":"berapa end_depth dari site_id 21536_2025?"}',
                    '{"sql":"SELECT END_DEPTH FROM dbo.customers WHERE id = 21536"}',
                    "end_depth dari site_id 21536_2025 adalah 12.70",
                ],
            )
            adapter.columns = ["END_DEPTH"]
            adapter.rows = [{"END_DEPTH": "12.70"}]
            runtime.handle_message("/sql schema default --refresh")

            result = runtime.handle_message("berapa end_depth dari site_id 21536_2025?")

            self.assertEqual(result["kind"], "tool-chat")
            self.assertEqual(result["tools"][0]["tool"], "query_sql_server")
            self.assertEqual(result["reply"], "end_depth dari site_id 21536_2025 adalah 12.70")
            self.assertTrue(adapter.query_calls)

    def test_site_id_question_falls_back_to_sql_tool_when_planner_returns_sql_text(self) -> None:
        with TemporaryDirectory() as tmp:
            runtime, adapter = self._runtime(
                Path(tmp),
                replies=[
                    "/sql SELECT end_depth FROM dbo.customers WHERE id = 21536;",
                    '{"sql":"SELECT END_DEPTH FROM dbo.customers WHERE id = 21536"}',
                ],
            )
            adapter.columns = ["END_DEPTH"]
            adapter.rows = [{"END_DEPTH": "12.70"}]
            runtime.handle_message("/sql schema default --refresh")

            result = runtime.handle_message("berapa end_depth dari site_id 21536_2025?")

            self.assertEqual(result["kind"], "tool-chat")
            self.assertEqual(result["reply"], "end_depth dari site_id 21536_2025 adalah 12.70")
            self.assertTrue(adapter.query_calls)

    def test_guided_lookup_uses_schema_file_without_sql_generation(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            schema_file = root / "default.md"
            schema_file.write_text(
                "\n".join(
                    [
                        "# SQL Schema: default",
                        "",
                        "## Query Guidance",
                        "",
                        "### Table Priority",
                        "- dbo.primary_collar",
                        "",
                        "### Identifier Aliases",
                        "- lubang = SITE_ID",
                        "",
                        "### Column Aliases",
                        "- kedalaman akhir = END_DEPTH",
                        "",
                        "## dbo.primary_collar",
                        "Columns:",
                        "- SITE_ID nvarchar",
                        "- END_DEPTH decimal",
                    ]
                ),
                encoding="utf-8",
            )
            env = {
                "SECOND_BRAIN_SQL_PROFILES": json.dumps(
                    {
                        "default": {
                            "connection_env": "SECOND_BRAIN_SQL_DEFAULT_CONNECTION",
                            "schemas": ["dbo"],
                            "schema_file": schema_file.as_posix(),
                            "max_rows": 25,
                            "timeout_seconds": 5,
                        }
                    }
                ),
                "SECOND_BRAIN_SQL_DEFAULT_CONNECTION": "Server=localhost;Database=test;UID=reader;PWD=secret;",
            }
            with patch.dict(os.environ, env, clear=False):
                adapter = FakeSqlAdapter()
                adapter.columns = ["END_DEPTH"]
                adapter.rows = [{"END_DEPTH": "12.70"}]
                llm = FakeLLM(
                    [
                        '{"tool":"query_sql_server","profile":"default","question":"show DEPTH_FROM for this site"}',
                    ]
                )
                config = UIConfig(
                    workspace=str(root),
                    ollama_base_url="http://localhost:11434",
                    ollama_model="gemma4:e2b",
                )
                runtime = ChatRuntime(config, llm=llm, sql_adapter=adapter)

                result = runtime.handle_message("berapa kedalaman akhir dari lubang 21536_2025?")

        self.assertEqual(result["kind"], "tool-chat")
        self.assertEqual(result["reply"], "end_depth dari lubang 21536_2025 adalah 12.70")
        self.assertIn("FROM [dbo].[primary_collar]", adapter.query_calls[0])
        self.assertEqual(len(llm.calls), 1)

    def test_guided_multi_table_lookup_returns_all_requested_values(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            schema_file = root / "default.md"
            schema_file.write_text(
                "\n".join(
                    [
                        "# SQL Schema: default",
                        "",
                        "## Query Guidance",
                        "",
                        "### Identifier Aliases",
                        "- hole id = SITE_ID",
                        "",
                        "### Column Aliases",
                        "- x = EASTING",
                        "- y = NORTHING",
                        "- z = ELEVATION",
                        "- kb = BIT_COEFFICIENT",
                        "",
                        "## dbo.GB_SITE_SURVEY",
                        "Columns:",
                        "- SITE_ID nvarchar",
                        "- EASTING float",
                        "- NORTHING float",
                        "- ELEVATION float",
                        "",
                        "## dbo.GB_SITE",
                        "Columns:",
                        "- SITE_ID nvarchar",
                        "- END_DEPTH decimal",
                        "- BIT_COEFFICIENT decimal",
                    ]
                ),
                encoding="utf-8",
            )
            env = {
                "SECOND_BRAIN_SQL_PROFILES": json.dumps(
                    {
                        "default": {
                            "connection_env": "SECOND_BRAIN_SQL_DEFAULT_CONNECTION",
                            "schemas": ["dbo"],
                            "schema_file": schema_file.as_posix(),
                            "max_rows": 25,
                            "timeout_seconds": 5,
                        }
                    }
                ),
                "SECOND_BRAIN_SQL_DEFAULT_CONNECTION": "Server=localhost;Database=test;UID=reader;PWD=secret;",
            }
            with patch.dict(os.environ, env, clear=False):
                adapter = FakeSqlAdapter()
                llm = FakeLLM(
                    [
                        '{"tool":"query_sql_server","profile":"default","question":"show requested fields"}',
                    ]
                )
                config = UIConfig(
                    workspace=str(root),
                    ollama_base_url="http://localhost:11434",
                    ollama_model="gemma4:e2b",
                )
                runtime = ChatRuntime(config, llm=llm, sql_adapter=adapter)

                result = runtime.handle_message(
                    "query ke database, ambil x, y dan z di tabel gb_site_survey dan ambil end_depth serta bit_coefficient di gb_site untuk hole id 21536_2025?"
                )

        self.assertEqual(result["kind"], "tool-chat")
        self.assertIn("GB_SITE_SURVEY.EASTING", result["reply"])
        self.assertIn("GB_SITE_SURVEY.NORTHING", result["reply"])
        self.assertIn("GB_SITE_SURVEY.ELEVATION", result["reply"])
        self.assertIn("GB_SITE.END_DEPTH", result["reply"])
        self.assertIn("GB_SITE.BIT_COEFFICIENT", result["reply"])
        self.assertEqual(len(llm.calls), 1)


if __name__ == "__main__":
    unittest.main()
