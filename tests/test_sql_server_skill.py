from __future__ import annotations

import os
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
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
        self.extra_columns: list[SqlColumn] = []
        self.result_columns = ["id", "name"]
        self.result_rows = [{"id": 1, "name": "Ada"}]

    def fetch_schema(self, connection_string: str, profile) -> list[SqlColumn]:
        self.schema_calls.append(connection_string)
        return [
            SqlColumn(schema="dbo", table="customers", column="id", data_type="int"),
            SqlColumn(schema="dbo", table="customers", column="name", data_type="nvarchar"),
            SqlColumn(schema="dbo", table="orders", column="id", data_type="int"),
            SqlColumn(schema="dbo", table="orders", column="customer_id", data_type="int"),
            SqlColumn(schema="audit", table="secrets", column="token", data_type="nvarchar"),
        ] + self.extra_columns

    def execute_query(self, connection_string: str, sql: str, timeout_seconds: int) -> SqlQueryResult:
        self.query_calls.append((connection_string, sql, timeout_seconds))
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
            columns=self.result_columns,
            rows=self.result_rows,
            sql=sql,
            row_count=len(self.result_rows),
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

    def test_schema_file_is_used_before_database_refresh(self) -> None:
        with TemporaryDirectory() as tmp:
            schema_file = Path(tmp) / "default.md"
            schema_file.write_text(
                "\n".join(
                    [
                        "# SQL Schema: default",
                        "",
                        "## dbo.customers",
                        "Columns:",
                        "- id int",
                        "- name nvarchar",
                    ]
                ),
                encoding="utf-8",
            )
            adapter = FakeSqlAdapter()
            env = {
                "SECOND_BRAIN_SQL_PROFILES": json.dumps(
                    {
                        "default": {
                            "connection_env": "SECOND_BRAIN_SQL_DEFAULT_CONNECTION",
                            "schemas": ["dbo"],
                            "schema_file": schema_file.as_posix(),
                        }
                    }
                ),
                "SECOND_BRAIN_SQL_DEFAULT_CONNECTION": "Server=localhost;Database=test;UID=reader;PWD=secret;",
            }
            with patch.dict(os.environ, env, clear=False):
                skill = SqlServerSkill.from_env(adapter=adapter)

                schema = skill.get_schema("default", refresh=True)

        self.assertEqual(adapter.schema_calls, [])
        self.assertEqual(set(schema.tables), {"dbo.customers"})
        self.assertEqual([column.column for column in schema.tables["dbo.customers"]], ["id", "name"])

    def test_schema_file_parses_query_guidance(self) -> None:
        with TemporaryDirectory() as tmp:
            schema_file = Path(tmp) / "default.md"
            schema_file.write_text(
                "\n".join(
                    [
                        "# SQL Schema: default",
                        "",
                        "## Query Guidance",
                        "",
                        "Default lookup table priority:",
                        "1. dbo.primary_collar",
                        "2. dbo.secondary_collar",
                        "",
                        "### Identifier Aliases",
                        "- lubang = SITE_ID",
                        "- hole id = SITE_ID",
                        "",
                        "### Column Aliases",
                        "- kedalaman akhir = END_DEPTH",
                        "- total depth = END_DEPTH",
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
                        }
                    }
                ),
                "SECOND_BRAIN_SQL_DEFAULT_CONNECTION": "Server=localhost;Database=test;UID=reader;PWD=secret;",
            }
            with patch.dict(os.environ, env, clear=False):
                skill = SqlServerSkill.from_env(adapter=FakeSqlAdapter())

                schema = skill.get_schema("default", refresh=True)

        self.assertEqual(schema.guidance.table_priority, ("dbo.primary_collar", "dbo.secondary_collar"))
        self.assertEqual(schema.guidance.identifier_aliases["lubang"], "SITE_ID")
        self.assertEqual(schema.guidance.column_aliases["kedalaman akhir"], "END_DEPTH")

    def test_lookup_record_uses_guidance_aliases_and_table_priority(self) -> None:
        with TemporaryDirectory() as tmp:
            schema_file = Path(tmp) / "default.md"
            schema_file.write_text(
                "\n".join(
                    [
                        "# SQL Schema: default",
                        "",
                        "## Query Guidance",
                        "",
                        "### Table Priority",
                        "- dbo.secondary_collar",
                        "- dbo.primary_collar",
                        "",
                        "### Identifier Aliases",
                        "- lubang = SITE_ID",
                        "",
                        "### Column Aliases",
                        "- kedalaman akhir = END_DEPTH",
                        "",
                        "## dbo.secondary_collar",
                        "Columns:",
                        "- SITE_ID nvarchar",
                        "- EASTING float",
                        "",
                        "## dbo.primary_collar",
                        "Columns:",
                        "- SITE_ID nvarchar",
                        "- END_DEPTH decimal",
                    ]
                ),
                encoding="utf-8",
            )
            adapter = FakeSqlAdapter()
            adapter.result_columns = ["END_DEPTH"]
            adapter.result_rows = [{"END_DEPTH": "12.70"}]
            env = {
                "SECOND_BRAIN_SQL_PROFILES": json.dumps(
                    {
                        "default": {
                            "connection_env": "SECOND_BRAIN_SQL_DEFAULT_CONNECTION",
                            "schemas": ["dbo"],
                            "schema_file": schema_file.as_posix(),
                        }
                    }
                ),
                "SECOND_BRAIN_SQL_DEFAULT_CONNECTION": "Server=localhost;Database=test;UID=reader;PWD=secret;",
            }
            with patch.dict(os.environ, env, clear=False):
                skill = SqlServerSkill.from_env(adapter=adapter)

                result = skill.lookup_record("berapa kedalaman akhir dari lubang 21536_2025?", profile_name="default")

        self.assertIsNotNone(result)
        self.assertEqual(result.rows, [{"END_DEPTH": "12.70"}])
        self.assertIn("FROM [dbo].[primary_collar]", adapter.query_calls[0][1])
        self.assertIn("[END_DEPTH]", adapter.query_calls[0][1])
        self.assertIn("[SITE_ID] = '21536_2025'", adapter.query_calls[0][1])

    def test_lookup_record_handles_multi_table_multi_column_request(self) -> None:
        with TemporaryDirectory() as tmp:
            schema_file = Path(tmp) / "default.md"
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
            adapter = FakeSqlAdapter()
            env = {
                "SECOND_BRAIN_SQL_PROFILES": json.dumps(
                    {
                        "default": {
                            "connection_env": "SECOND_BRAIN_SQL_DEFAULT_CONNECTION",
                            "schemas": ["dbo"],
                            "schema_file": schema_file.as_posix(),
                        }
                    }
                ),
                "SECOND_BRAIN_SQL_DEFAULT_CONNECTION": "Server=localhost;Database=test;UID=reader;PWD=secret;",
            }
            with patch.dict(os.environ, env, clear=False):
                skill = SqlServerSkill.from_env(adapter=adapter)

                result = skill.lookup_record(
                    "query ke database, ambil x, y dan z di tabel gb_site_survey dan ambil end_depth serta bit_coefficient di gb_site untuk hole id 21536_2025?",
                    profile_name="default",
                )

        self.assertIsNotNone(result)
        self.assertEqual(result.row_count, 1)
        self.assertEqual(
            result.rows,
            [
                {
                    "GB_SITE_SURVEY.EASTING": "100.1",
                    "GB_SITE_SURVEY.NORTHING": "200.2",
                    "GB_SITE_SURVEY.ELEVATION": "12.3",
                    "GB_SITE.END_DEPTH": "12.70",
                    "GB_SITE.BIT_COEFFICIENT": "0.889",
                }
            ],
        )
        self.assertEqual(len(adapter.query_calls), 2)
        self.assertIn("FROM [dbo].[GB_SITE_SURVEY]", adapter.query_calls[0][1])
        self.assertIn("FROM [dbo].[GB_SITE]", adapter.query_calls[1][1])

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

    def test_run_allows_schema_table_qualified_columns(self) -> None:
        skill, adapter = self._skill()
        skill.get_schema("default", refresh=True)

        result = skill.run("SELECT dbo.customers.name FROM dbo.customers", profile_name="default")

        self.assertEqual(result.row_count, 1)
        self.assertIn("[dbo].[customers].name", adapter.query_calls[0][1])

    def test_run_brackets_schema_table_references_before_execution(self) -> None:
        skill, adapter = self._skill()
        adapter.extra_columns.extend(
            [
                SqlColumn(schema="dbo", table="1_customers", column="name", data_type="nvarchar"),
            ]
        )
        skill.get_schema("default", refresh=True)

        result = skill.run("SELECT dbo.1_customers.name FROM dbo.1_customers", profile_name="default")

        self.assertEqual(result.row_count, 1)
        self.assertIn("[dbo].[1_customers].name", adapter.query_calls[0][1])
        self.assertIn("FROM [dbo].[1_customers]", adapter.query_calls[0][1])

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
