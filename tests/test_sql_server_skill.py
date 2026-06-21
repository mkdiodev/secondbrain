from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from secondbrain.skills.sql_server_skill import (
    SqlColumn,
    SqlQueryResult,
    SqlServerSkill,
    SqlSafetyError,
)


class FakeSqlAdapter:
    def __init__(self) -> None:
        self.schema_calls: list[str] = []
        self.query_calls: list[tuple[str, str, int]] = []

    def fetch_schema(self, connection_string: str, profile) -> list[SqlColumn]:
        self.schema_calls.append(connection_string)
        return [
            SqlColumn(schema="dbo", table="customers", column="id", data_type="int"),
            SqlColumn(schema="dbo", table="customers", column="name", data_type="nvarchar"),
            SqlColumn(schema="dbo", table="orders", column="id", data_type="int"),
            SqlColumn(schema="dbo", table="orders", column="customer_id", data_type="int"),
            SqlColumn(schema="audit", table="secrets", column="token", data_type="nvarchar"),
        ]

    def execute_query(self, connection_string: str, sql: str, timeout_seconds: int) -> SqlQueryResult:
        self.query_calls.append((connection_string, sql, timeout_seconds))
        return SqlQueryResult(
            columns=["id", "name"],
            rows=[{"id": 1, "name": "Ada"}],
            sql=sql,
            row_count=1,
            truncated=False,
        )


class FakeLLM:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls: list[list[dict[str, str]]] = []

    async def chat(self, messages: list[dict[str, str]], temperature: float = 0.0) -> str:
        self.calls.append(messages)
        return self.reply


class SqlServerSkillTests(unittest.TestCase):
    def _skill(self, *, llm: FakeLLM | None = None) -> tuple[SqlServerSkill, FakeSqlAdapter]:
        adapter = FakeSqlAdapter()
        env = {
            "SECOND_BRAIN_SQL_PROFILES": (
                '{"default":{"connection_env":"SECOND_BRAIN_SQL_DEFAULT_CONNECTION",'
                '"schemas":["dbo"],"max_rows":50,"timeout_seconds":7}}'
            ),
            "SECOND_BRAIN_SQL_DEFAULT_CONNECTION": "Server=localhost;Database=test;UID=reader;PWD=secret;",
        }
        patcher = patch.dict(os.environ, env, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        return SqlServerSkill.from_env(adapter=adapter, llm=llm), adapter

    def test_profiles_hide_connection_strings(self) -> None:
        skill, _adapter = self._skill()

        profiles = skill.list_profiles()

        self.assertEqual(profiles[0]["name"], "default")
        self.assertEqual(profiles[0]["connection_env"], "SECOND_BRAIN_SQL_DEFAULT_CONNECTION")
        self.assertNotIn("secret", str(profiles))
        self.assertNotIn("PWD", str(profiles))

    def test_schema_cache_uses_profile_whitelist(self) -> None:
        skill, adapter = self._skill()

        schema = skill.get_schema("default", refresh=True)

        self.assertEqual(adapter.schema_calls, ["Server=localhost;Database=test;UID=reader;PWD=secret;"])
        self.assertIn("dbo.customers", schema.tables)
        self.assertIn("dbo.orders", schema.tables)
        self.assertNotIn("audit.secrets", schema.tables)

    def test_run_allows_select_and_enforces_top_limit(self) -> None:
        skill, adapter = self._skill()
        skill.get_schema("default", refresh=True)

        result = skill.run("SELECT id, name FROM dbo.customers", profile_name="default")

        self.assertEqual(result.rows, [{"id": 1, "name": "Ada"}])
        self.assertIn("TOP (50)", adapter.query_calls[0][1])
        self.assertEqual(adapter.query_calls[0][2], 7)

    def test_run_rejects_destructive_sql(self) -> None:
        skill, _adapter = self._skill()
        skill.get_schema("default", refresh=True)

        with self.assertRaises(SqlSafetyError):
            skill.run("DROP TABLE dbo.customers", profile_name="default")

    def test_run_rejects_unknown_table(self) -> None:
        skill, _adapter = self._skill()
        skill.get_schema("default", refresh=True)

        with self.assertRaises(SqlSafetyError):
            skill.run("SELECT token FROM audit.secrets", profile_name="default")

    def test_explain_generates_grounded_sql_without_execution(self) -> None:
        llm = FakeLLM("```sql\nSELECT id, name FROM dbo.customers\n```")
        skill, adapter = self._skill(llm=llm)
        skill.get_schema("default", refresh=True)

        sql = skill.explain("show customers", profile_name="default")

        self.assertIn("TOP (50)", sql)
        self.assertEqual(adapter.query_calls, [])
        self.assertNotIn("secret", str(llm.calls))

    def test_ask_generates_and_executes_safe_sql(self) -> None:
        llm = FakeLLM('{"sql":"SELECT id, name FROM dbo.customers"}')
        skill, adapter = self._skill(llm=llm)
        skill.get_schema("default", refresh=True)

        result = skill.ask("show customers", profile_name="default")

        self.assertEqual(result.row_count, 1)
        self.assertIn("TOP (50)", adapter.query_calls[0][1])
        self.assertNotIn("secret", str(llm.calls))


if __name__ == "__main__":
    unittest.main()
