"""Read-only SQL Server skill with schema-grounded query safety."""

from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Protocol

from secondbrain.llm_client import LocalLLMClient


class SqlSafetyError(ValueError):
    """Raised when a SQL statement fails the read-only safety guard."""


@dataclass(frozen=True)
class SqlColumn:
    schema: str
    table: str
    column: str
    data_type: str
    nullable: bool = True


@dataclass(frozen=True)
class SqlServerProfile:
    name: str
    connection_env: str
    schemas: tuple[str, ...] = ("dbo",)
    objects: tuple[str, ...] = ()
    max_rows: int = 100
    timeout_seconds: int = 20


@dataclass(frozen=True)
class SqlSchema:
    profile: str
    columns: tuple[SqlColumn, ...]

    @property
    def tables(self) -> dict[str, list[SqlColumn]]:
        grouped: dict[str, list[SqlColumn]] = {}
        for column in self.columns:
            key = f"{column.schema}.{column.table}"
            grouped.setdefault(key, []).append(column)
        return grouped

    def summary(self, *, max_tables: int = 40) -> str:
        if not self.columns:
            return "No schema metadata cached."
        lines: list[str] = []
        for index, (table, columns) in enumerate(sorted(self.tables.items())):
            if index >= max_tables:
                lines.append(f"... {len(self.tables) - max_tables} more tables/views")
                break
            col_text = ", ".join(f"{col.column} {col.data_type}" for col in columns)
            lines.append(f"{table}: {col_text}")
        return "\n".join(lines)


@dataclass(frozen=True)
class SqlQueryResult:
    columns: list[str]
    rows: list[dict[str, Any]]
    sql: str
    row_count: int
    truncated: bool = False


class SqlServerAdapter(Protocol):
    def fetch_schema(self, connection_string: str, profile: SqlServerProfile) -> list[SqlColumn]:
        ...

    def execute_query(
        self,
        connection_string: str,
        sql: str,
        timeout_seconds: int,
    ) -> SqlQueryResult:
        ...


class MssqlPythonAdapter:
    """Production adapter using Microsoft's mssql-python DB-API driver."""

    def _connect(self, connection_string: str):
        try:
            from mssql_python import connect
        except ImportError as exc:  # pragma: no cover - depends on optional system setup
            raise RuntimeError(
                "mssql-python is not installed. Install dependencies with: pip install -r requirements.txt"
            ) from exc
        return connect(connection_string)

    def fetch_schema(self, connection_string: str, profile: SqlServerProfile) -> list[SqlColumn]:
        where_parts: list[str] = []
        params: list[str] = []
        if profile.schemas:
            placeholders = ", ".join("?" for _ in profile.schemas)
            where_parts.append(f"c.TABLE_SCHEMA IN ({placeholders})")
            params.extend(profile.schemas)
        if profile.objects:
            object_clauses = []
            for item in profile.objects:
                schema, _, table = item.partition(".")
                if schema and table:
                    object_clauses.append("(c.TABLE_SCHEMA = ? AND c.TABLE_NAME = ?)")
                    params.extend([schema, table])
            if object_clauses:
                where_parts.append("(" + " OR ".join(object_clauses) + ")")
        where = " AND ".join(where_parts) if where_parts else "c.TABLE_SCHEMA = 'dbo'"
        sql = f"""
            SELECT c.TABLE_SCHEMA, c.TABLE_NAME, c.COLUMN_NAME, c.DATA_TYPE, c.IS_NULLABLE
            FROM INFORMATION_SCHEMA.COLUMNS AS c
            JOIN INFORMATION_SCHEMA.TABLES AS t
              ON c.TABLE_SCHEMA = t.TABLE_SCHEMA AND c.TABLE_NAME = t.TABLE_NAME
            WHERE t.TABLE_TYPE IN ('BASE TABLE', 'VIEW') AND {where}
            ORDER BY c.TABLE_SCHEMA, c.TABLE_NAME, c.ORDINAL_POSITION
        """
        conn = self._connect(connection_string)
        try:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            return [
                SqlColumn(
                    schema=str(row[0]),
                    table=str(row[1]),
                    column=str(row[2]),
                    data_type=str(row[3]),
                    nullable=str(row[4]).upper() == "YES",
                )
                for row in rows
            ]
        finally:
            conn.close()

    def execute_query(
        self,
        connection_string: str,
        sql: str,
        timeout_seconds: int,
    ) -> SqlQueryResult:
        conn = self._connect(connection_string)
        try:
            try:
                conn.autocommit = False
            except Exception:
                pass
            cursor = conn.cursor()
            try:
                cursor.timeout = timeout_seconds
            except Exception:
                pass
            cursor.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
            cursor.execute(sql)
            column_names = [col[0] for col in (cursor.description or [])]
            rows = [
                {column_names[index]: value for index, value in enumerate(row)}
                for row in cursor.fetchall()
            ]
            try:
                conn.rollback()
            except Exception:
                pass
            return SqlQueryResult(
                columns=column_names,
                rows=rows,
                sql=sql,
                row_count=len(rows),
                truncated=False,
            )
        finally:
            conn.close()


class SqlServerSkill:
    """Grounded, read-only SQL Server querying for chat and slash commands."""

    DANGEROUS_PATTERN = re.compile(
        r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|CREATE|TRUNCATE|EXEC|EXECUTE|"
        r"GRANT|DENY|REVOKE|BACKUP|RESTORE|KILL|DBCC|BULK|OPENROWSET|OPENQUERY|XP_)\b",
        re.IGNORECASE,
    )

    def __init__(
        self,
        profiles: dict[str, SqlServerProfile],
        *,
        adapter: SqlServerAdapter | None = None,
        llm: LocalLLMClient | None = None,
    ):
        self.profiles = profiles
        self.adapter = adapter or MssqlPythonAdapter()
        self.llm = llm
        self._schema_cache: dict[str, SqlSchema] = {}

    @classmethod
    def from_env(
        cls,
        *,
        adapter: SqlServerAdapter | None = None,
        llm: LocalLLMClient | None = None,
    ) -> "SqlServerSkill":
        return cls(_profiles_from_env(), adapter=adapter, llm=llm)

    def list_profiles(self) -> list[dict[str, Any]]:
        return [
            {
                "name": profile.name,
                "connection_env": profile.connection_env,
                "schemas": list(profile.schemas),
                "objects": list(profile.objects),
                "max_rows": profile.max_rows,
                "timeout_seconds": profile.timeout_seconds,
                "configured": bool(os.environ.get(profile.connection_env)),
            }
            for profile in self.profiles.values()
        ]

    def get_schema(self, profile_name: str = "default", *, refresh: bool = False) -> SqlSchema:
        profile = self._profile(profile_name)
        if not refresh and profile.name in self._schema_cache:
            return self._schema_cache[profile.name]
        connection = self._connection(profile)
        columns = self.adapter.fetch_schema(connection, profile)
        filtered = tuple(column for column in columns if self._column_allowed(column, profile))
        schema = SqlSchema(profile=profile.name, columns=filtered)
        self._schema_cache[profile.name] = schema
        return schema

    def run(self, sql: str, *, profile_name: str = "default") -> SqlQueryResult:
        profile = self._profile(profile_name)
        schema = self.get_schema(profile.name)
        safe_sql = self.validate_sql(sql, profile=profile, schema=schema)
        return self.adapter.execute_query(
            self._connection(profile),
            safe_sql,
            profile.timeout_seconds,
        )

    def explain(self, question: str, *, profile_name: str = "default") -> str:
        sql = self._generate_sql(question, profile_name=profile_name)
        profile = self._profile(profile_name)
        schema = self.get_schema(profile.name)
        return self.validate_sql(sql, profile=profile, schema=schema)

    def ask(self, question: str, *, profile_name: str = "default") -> SqlQueryResult:
        sql = self.explain(question, profile_name=profile_name)
        return self.run(sql, profile_name=profile_name)

    def validate_sql(self, sql: str, *, profile: SqlServerProfile, schema: SqlSchema) -> str:
        candidate = _strip_sql_fences(sql)
        if not candidate:
            raise SqlSafetyError("SQL is empty.")
        if ";" in candidate.rstrip(";"):
            raise SqlSafetyError("Multiple SQL statements are not allowed.")
        candidate = candidate.rstrip(";").strip()
        if self.DANGEROUS_PATTERN.search(candidate):
            raise SqlSafetyError("Only read-only SELECT queries are allowed.")
        if re.search(r"\bINTO\s+[#\[\]\w.]+", candidate, flags=re.IGNORECASE):
            raise SqlSafetyError("SELECT INTO is not allowed.")
        if not re.match(r"^\s*(WITH\b.*?\bSELECT\b|SELECT\b)", candidate, flags=re.IGNORECASE | re.DOTALL):
            raise SqlSafetyError("Only SELECT or WITH ... SELECT queries are allowed.")

        tables = _extract_tables(candidate)
        if not tables:
            raise SqlSafetyError("Query must reference at least one cached table or view.")
        known_tables = {name.lower() for name in schema.tables}
        for table in tables:
            if table.lower() not in known_tables:
                raise SqlSafetyError(f"Table is not in the cached schema whitelist: {table}")

        _validate_columns(candidate, schema, tables)
        return _ensure_top_limit(candidate, profile.max_rows)

    def _generate_sql(self, question: str, *, profile_name: str) -> str:
        if self.llm is None:
            raise RuntimeError("SQL natural-language generation requires an LLM client.")
        profile = self._profile(profile_name)
        schema = self.get_schema(profile.name)
        prompt = "\n".join(
            [
                "Generate one read-only SQL Server SELECT query for the user's question.",
                "Return JSON only in this exact shape: {\"sql\":\"SELECT ...\"}.",
                "Rules:",
                "- Use only tables and columns listed in the schema.",
                "- Do not use INSERT, UPDATE, DELETE, MERGE, DROP, ALTER, CREATE, TRUNCATE, EXEC, SELECT INTO, temp table writes, or multiple statements.",
                f"- Limit results to at most {profile.max_rows} rows.",
                "- Prefer fully qualified schema.table names.",
                "",
                "Schema:",
                schema.summary(),
                "",
                f"User question: {question}",
            ]
        )
        raw = asyncio.run(
            self.llm.chat(
                [
                    {"role": "system", "content": "You are a strict SQL Server query generator."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
            )
        )
        return _extract_sql_from_model(raw)

    def _profile(self, profile_name: str) -> SqlServerProfile:
        key = (profile_name or "default").strip()
        try:
            return self.profiles[key]
        except KeyError as exc:
            raise ValueError(f"Unknown SQL profile: {key}") from exc

    @staticmethod
    def _connection(profile: SqlServerProfile) -> str:
        connection = os.environ.get(profile.connection_env, "").strip()
        if not connection:
            raise ValueError(f"Missing SQL Server connection env var: {profile.connection_env}")
        return connection

    @staticmethod
    def _column_allowed(column: SqlColumn, profile: SqlServerProfile) -> bool:
        schema = column.schema.lower()
        table = f"{column.schema}.{column.table}".lower()
        allowed_schemas = {item.lower() for item in profile.schemas}
        allowed_objects = {item.lower() for item in profile.objects}
        return (not allowed_schemas or schema in allowed_schemas) and (
            not allowed_objects or table in allowed_objects
        )


def _profiles_from_env() -> dict[str, SqlServerProfile]:
    raw = os.environ.get("SECOND_BRAIN_SQL_PROFILES", "").strip()
    if not raw:
        if os.environ.get("SECOND_BRAIN_SQL_DEFAULT_CONNECTION"):
            return {
                "default": SqlServerProfile(
                    name="default",
                    connection_env="SECOND_BRAIN_SQL_DEFAULT_CONNECTION",
                    schemas=("dbo",),
                )
            }
        return {}
    data = json.loads(raw)
    if isinstance(data, list):
        items = {str(item["name"]): item for item in data if isinstance(item, dict) and item.get("name")}
    elif isinstance(data, dict):
        items = data
    else:
        raise ValueError("SECOND_BRAIN_SQL_PROFILES must be a JSON object or array.")

    profiles: dict[str, SqlServerProfile] = {}
    for name, item in items.items():
        if not isinstance(item, dict):
            raise ValueError(f"Invalid SQL profile: {name}")
        profile_name = str(item.get("name") or name)
        connection_env = str(item.get("connection_env") or "").strip()
        if not connection_env:
            raise ValueError(f"SQL profile {profile_name} is missing connection_env.")
        max_rows = max(1, min(int(item.get("max_rows", 100)), 1000))
        timeout_seconds = max(1, min(int(item.get("timeout_seconds", 20)), 120))
        profiles[profile_name] = SqlServerProfile(
            name=profile_name,
            connection_env=connection_env,
            schemas=tuple(str(value) for value in item.get("schemas", ["dbo"])),
            objects=tuple(str(value) for value in item.get("objects", [])),
            max_rows=max_rows,
            timeout_seconds=timeout_seconds,
        )
    return profiles


def _strip_sql_fences(sql: str) -> str:
    text = str(sql or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:sql)?", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text).strip()
    return text


def _extract_sql_from_model(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json|sql)?", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict) and data.get("sql"):
            return str(data["sql"])
    except json.JSONDecodeError:
        pass
    match = re.search(r"SELECT\b.*", text, flags=re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(0).strip()
    raise SqlSafetyError("Model did not return a SQL query.")


def _extract_tables(sql: str) -> list[str]:
    tables: list[str] = []
    for match in re.finditer(r"\b(?:FROM|JOIN)\s+((?:\[[^\]]+\]|\w+)(?:\s*\.\s*(?:\[[^\]]+\]|\w+))?)", sql, flags=re.IGNORECASE):
        name = _normalize_identifier(match.group(1))
        if "." not in name:
            name = f"dbo.{name}"
        if name.lower() not in {item.lower() for item in tables}:
            tables.append(name)
    return tables


def _validate_columns(sql: str, schema: SqlSchema, tables: list[str]) -> None:
    table_columns = {
        table.lower(): {column.column.lower() for column in columns}
        for table, columns in schema.tables.items()
    }
    if len(tables) == 1:
        allowed = table_columns[tables[0].lower()]
        aliases = _extract_aliases(sql)
        for column in _extract_select_columns(sql):
            if column == "*":
                continue
            owner, _, name = column.partition(".")
            if name and owner.lower() in aliases:
                table = aliases[owner.lower()].lower()
                if name.lower() not in table_columns.get(table, set()):
                    raise SqlSafetyError(f"Column is not in cached schema: {column}")
            elif name:
                if name.lower() not in allowed:
                    raise SqlSafetyError(f"Column is not in cached schema: {column}")
            elif owner.lower() not in allowed:
                raise SqlSafetyError(f"Column is not in cached schema: {column}")


def _extract_aliases(sql: str) -> dict[str, str]:
    aliases: dict[str, str] = {}
    pattern = re.compile(
        r"\b(?:FROM|JOIN)\s+((?:\[[^\]]+\]|\w+)(?:\s*\.\s*(?:\[[^\]]+\]|\w+))?)"
        r"(?:\s+(?:AS\s+)?(\w+))?",
        flags=re.IGNORECASE,
    )
    for match in pattern.finditer(sql):
        table = _normalize_identifier(match.group(1))
        if "." not in table:
            table = f"dbo.{table}"
        alias = match.group(2)
        if alias and alias.upper() not in {"WHERE", "JOIN", "LEFT", "RIGHT", "INNER", "OUTER", "GROUP", "ORDER"}:
            aliases[alias.lower()] = table
    return aliases


def _extract_select_columns(sql: str) -> list[str]:
    match = re.search(r"\bSELECT\b\s+(?:TOP\s*\(\s*\d+\s*\)\s+|TOP\s+\d+\s+)?(.*?)\bFROM\b", sql, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return []
    columns: list[str] = []
    for part in match.group(1).split(","):
        expr = part.strip()
        if not expr or "(" in expr:
            continue
        expr = re.sub(r"\s+AS\s+\w+$", "", expr, flags=re.IGNORECASE)
        expr = re.sub(r"\s+\w+$", "", expr).strip()
        columns.append(_normalize_identifier(expr))
    return columns


def _normalize_identifier(value: str) -> str:
    return re.sub(r"\s+", "", value).replace("[", "").replace("]", "")


def _ensure_top_limit(sql: str, max_rows: int) -> str:
    match = re.search(r"\bSELECT\s+TOP\s*(?:\(\s*(\d+)\s*\)|(\d+))", sql, flags=re.IGNORECASE)
    if match:
        current = int(match.group(1) or match.group(2))
        if current <= max_rows:
            return sql
        return re.sub(
            r"\bSELECT\s+TOP\s*(?:\(\s*\d+\s*\)|\d+)",
            f"SELECT TOP ({max_rows})",
            sql,
            count=1,
            flags=re.IGNORECASE,
        )
    return re.sub(r"\bSELECT\b", f"SELECT TOP ({max_rows})", sql, count=1, flags=re.IGNORECASE)
