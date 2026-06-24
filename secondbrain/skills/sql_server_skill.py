"""Read-only SQL Server skill with schema-grounded query safety."""

from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
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
    schema_file: str | None = None


@dataclass(frozen=True)
class SqlQueryGuidance:
    table_priority: tuple[str, ...] = ()
    identifier_aliases: dict[str, str] = field(default_factory=dict)
    column_aliases: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SqlSchema:
    profile: str
    columns: tuple[SqlColumn, ...]
    guidance: SqlQueryGuidance = field(default_factory=SqlQueryGuidance)

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
        for index, (table, columns) in enumerate(self.tables.items()):
            if index >= max_tables:
                lines.append(f"... {len(self.tables) - max_tables} more tables/views")
                break
            col_text = ", ".join(f"{col.column} {col.data_type}" for col in columns)
            lines.append(f"{table}: {col_text}")
        return "\n".join(lines)

    def compact_summary(self, *, max_tables: int = 12, max_columns: int = 8) -> str:
        if not self.columns:
            return "Tables/views: 0\nNo schema metadata cached."
        lines = [
            f"Tables/views: {len(self.tables)}",
            f"Columns: {len(self.columns)}",
            "",
            "Preview:",
        ]
        for index, (table, columns) in enumerate(self.tables.items()):
            if index >= max_tables:
                lines.append(f"... {len(self.tables) - max_tables} more tables/views")
                break
            visible = columns[:max_columns]
            col_text = ", ".join(f"{col.column} {col.data_type}" for col in visible)
            if len(columns) > max_columns:
                col_text += f", ... {len(columns) - max_columns} more columns"
            lines.append(f"- {table}: {col_text}")
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
                "schema_file": profile.schema_file,
                "configured": bool(os.environ.get(profile.connection_env)),
            }
            for profile in self.profiles.values()
        ]

    def get_schema(self, profile_name: str = "default", *, refresh: bool = False) -> SqlSchema:
        profile = self._profile(profile_name)
        if not refresh and profile.name in self._schema_cache:
            return self._schema_cache[profile.name]
        schema_file_payload = self._schema_file_payload(profile)
        guidance = SqlQueryGuidance()
        if schema_file_payload is None:
            connection = self._connection(profile)
            columns = self.adapter.fetch_schema(connection, profile)
        else:
            columns, guidance = schema_file_payload
        filtered = tuple(column for column in columns if self._column_allowed(column, profile))
        schema = SqlSchema(profile=profile.name, columns=filtered, guidance=guidance)
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

    def lookup_record(self, question: str, *, profile_name: str = "default") -> SqlQueryResult | None:
        profile = self._profile(profile_name)
        schema = self.get_schema(profile.name)
        multi_lookup = _parse_guided_multi_lookup(question, schema)
        if multi_lookup is not None:
            identifier_column, identifier_value, requests = multi_lookup
            merged_row: dict[str, Any] = {}
            sql_parts: list[str] = []
            for table_name, target_columns in requests:
                schema_name, _, object_name = table_name.partition(".")
                select_columns = ", ".join(f"[{column}]" for column in target_columns)
                sql = (
                    f"SELECT TOP (1) {select_columns} "
                    f"FROM [{schema_name}].[{object_name}] "
                    f"WHERE [{identifier_column}] = {_sql_string_literal(identifier_value)}"
                )
                result = self.run(sql, profile_name=profile.name)
                sql_parts.append(result.sql)
                if result.rows:
                    for column in target_columns:
                        key = f"{object_name}.{column}"
                        merged_row[key] = result.rows[0].get(column)
                else:
                    for column in target_columns:
                        key = f"{object_name}.{column}"
                        merged_row[key] = None
            columns = list(merged_row)
            return SqlQueryResult(
                columns=columns,
                rows=[merged_row] if merged_row else [],
                sql="\n".join(sql_parts),
                row_count=1 if merged_row else 0,
                truncated=False,
            )
        lookup = _parse_guided_lookup(question, schema)
        if lookup is None:
            return None
        table_name, identifier_column, identifier_value, target_column = lookup
        schema_name, _, object_name = table_name.partition(".")
        sql = (
            f"SELECT TOP (1) [{target_column}] "
            f"FROM [{schema_name}].[{object_name}] "
            f"WHERE [{identifier_column}] = {_sql_string_literal(identifier_value)}"
        )
        return self.run(sql, profile_name=profile.name)

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
        limited = _ensure_top_limit(candidate, profile.max_rows)
        return _quote_known_table_references(limited, schema)

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
                schema.compact_summary(max_tables=16, max_columns=12),
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
    def _schema_file_payload(profile: SqlServerProfile) -> tuple[list[SqlColumn], SqlQueryGuidance] | None:
        if not profile.schema_file:
            return None
        path = Path(profile.schema_file).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.exists():
            return None
        return _parse_schema_file(path)

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
                    schema_file=os.environ.get("SECOND_BRAIN_SQL_DEFAULT_SCHEMA_FILE") or None,
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
            schema_file=str(item.get("schema_file") or "").strip() or None,
        )
    return profiles


def _parse_schema_file(path: Path) -> tuple[list[SqlColumn], SqlQueryGuidance]:
    columns: list[SqlColumn] = []
    table_priority: list[str] = []
    identifier_aliases: dict[str, str] = {}
    column_aliases: dict[str, str] = {}
    current_schema = "dbo"
    current_table = ""
    section = ""
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        heading = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
        if heading:
            heading_text = heading.group(1).strip()
            lower_heading = heading_text.lower()
            if lower_heading in {"query guidance", "guidance"}:
                current_table = ""
                section = "guidance"
                continue
            if lower_heading in {"table priority", "default lookup table priority"}:
                current_table = ""
                section = "table_priority"
                continue
            if lower_heading in {"identifier aliases", "identifier alias"}:
                current_table = ""
                section = "identifier_aliases"
                continue
            if lower_heading in {"column aliases", "column alias"}:
                current_table = ""
                section = "column_aliases"
                continue
            table_name = _schema_file_table_name(heading_text)
            if table_name:
                current_schema, current_table = table_name
                section = "columns"
            continue
        lower_label = line.rstrip(":").strip().lower()
        if lower_label in {"table priority", "default lookup table priority"}:
            current_table = ""
            section = "table_priority"
            continue
        if lower_label in {"identifier aliases", "identifier alias"}:
            current_table = ""
            section = "identifier_aliases"
            continue
        if lower_label in {"column aliases", "column alias"}:
            current_table = ""
            section = "column_aliases"
            continue
        guidance_item = re.match(r"^\s*(?:[-*]|\d+\.)\s+(.+)$", line)
        if section in {"table_priority", "identifier_aliases", "column_aliases"} and guidance_item:
            item = guidance_item.group(1).strip()
            if section == "table_priority":
                table = re.sub(r"^\d+\.\s*", "", item).strip()
                parsed_table = _schema_file_table_name(table)
                if parsed_table:
                    table_priority.append(".".join(parsed_table))
            elif section == "identifier_aliases":
                alias = _schema_file_alias(item)
                if alias:
                    identifier_aliases[alias[0]] = alias[1]
            elif section == "column_aliases":
                alias = _schema_file_alias(item)
                if alias:
                    column_aliases[alias[0]] = alias[1]
            continue
        inline_table = re.match(r"^((?:\[[^\]]+\]|\w+)\.(?:\[[^\]]+\]|\w+))\s*:\s*(.+)$", line)
        if inline_table:
            schema, table = _schema_file_table_name(inline_table.group(1)) or ("dbo", "")
            for item in inline_table.group(2).split(","):
                column = _schema_file_column(item)
                if column:
                    columns.append(SqlColumn(schema=schema, table=table, column=column[0], data_type=column[1]))
            continue
        if current_table and section == "columns" and line.startswith(("-", "*")):
            column = _schema_file_column(line[1:])
            if column:
                columns.append(
                    SqlColumn(
                        schema=current_schema,
                        table=current_table,
                        column=column[0],
                        data_type=column[1],
                    )
                )
    return columns, SqlQueryGuidance(
        table_priority=tuple(table_priority),
        identifier_aliases=identifier_aliases,
        column_aliases=column_aliases,
    )


def _schema_file_table_name(value: str) -> tuple[str, str] | None:
    cleaned = _normalize_identifier(value.strip().strip("`"))
    if cleaned.lower().startswith("sqlschema:"):
        return None
    if "." not in cleaned:
        return None
    schema, table = cleaned.split(".", 1)
    if not schema or not table:
        return None
    return schema, table


def _schema_file_column(value: str) -> tuple[str, str] | None:
    cleaned = value.strip()
    if not cleaned or cleaned.lower() == "columns:":
        return None
    cleaned = re.sub(r"^\s*[-*]\s+", "", cleaned)
    cleaned = cleaned.strip()
    if cleaned.startswith("["):
        match = re.match(r"^(\[[^\]]+\])\s*(.*)$", cleaned)
    elif cleaned.startswith("`"):
        match = re.match(r"^`([^`]+)`\s*(.*)$", cleaned)
    else:
        match = re.match(r"^(\S+)\s*(.*)$", cleaned)
    if not match:
        return None
    column = _normalize_identifier(match.group(1).strip())
    if not column or column.lower() in {"columns", "column"}:
        return None
    data_type = match.group(2).strip(" :-") or "unknown"
    return column, data_type


def _schema_file_alias(value: str) -> tuple[str, str] | None:
    match = re.match(r"^(.+?)\s*(?:=|->|:)\s*`?(\[[^\]]+\]|\w+)`?\s*$", value.strip())
    if not match:
        return None
    alias = _normalize_phrase(match.group(1))
    column = _normalize_identifier(match.group(2))
    if not alias or not column:
        return None
    return alias, column


def _parse_guided_lookup(question: str, schema: SqlSchema) -> tuple[str, str, str, str] | None:
    text = _normalize_phrase(question)
    target_column = _match_requested_column(text, schema)
    identifier = _match_identifier(question, schema)
    if target_column is None or identifier is None:
        return None
    identifier_column, identifier_value = identifier
    table = _choose_lookup_table(schema, identifier_column, target_column)
    if table is None:
        return None
    return table, identifier_column, identifier_value, target_column


def _parse_guided_multi_lookup(question: str, schema: SqlSchema) -> tuple[str, str, list[tuple[str, list[str]]]] | None:
    identifier = _match_identifier(question, schema)
    if identifier is None:
        return None
    table_mentions = _mentioned_tables(question, schema)
    if len(table_mentions) < 2:
        return None
    identifier_column, identifier_value = identifier
    requests: list[tuple[str, list[str]]] = []
    for index, (table, start) in enumerate(table_mentions):
        segment_start = table_mentions[index - 1][1] if index > 0 else 0
        end = table_mentions[index + 1][1] if index + 1 < len(table_mentions) else len(question)
        segment = question[segment_start:end]
        columns = _requested_columns_for_table(segment, table, schema)
        if columns:
            table_columns = {column.column.lower() for column in schema.tables[table]}
            if identifier_column.lower() in table_columns:
                requests.append((table, columns))
    return (identifier_column, identifier_value, requests) if len(requests) >= 2 else None


def _match_requested_column(text: str, schema: SqlSchema) -> str | None:
    aliases: dict[str, str] = {}
    aliases.update({key: value for key, value in schema.guidance.column_aliases.items()})
    for column in schema.columns:
        aliases.setdefault(_normalize_phrase(column.column), column.column)
        aliases.setdefault(_normalize_phrase(column.column.replace("_", " ")), column.column)
    for alias, column in sorted(aliases.items(), key=lambda item: len(item[0]), reverse=True):
        if _phrase_in_text(alias, text):
            return column
    return None


def _requested_columns_for_table(text: str, table: str, schema: SqlSchema) -> list[str]:
    normalized = _normalize_phrase(text)
    table_columns = {column.column.lower(): column.column for column in schema.tables[table]}
    requested: list[str] = []
    aliases: dict[str, str] = {}
    aliases.update(schema.guidance.column_aliases)
    for column in schema.tables[table]:
        aliases.setdefault(_normalize_phrase(column.column), column.column)
        aliases.setdefault(_normalize_phrase(column.column.replace("_", " ")), column.column)
    for alias, column in sorted(aliases.items(), key=lambda item: len(item[0]), reverse=True):
        if column.lower() not in table_columns:
            continue
        if _phrase_in_text(alias, normalized) and column not in requested:
            requested.append(column)
    return requested


def _mentioned_tables(question: str, schema: SqlSchema) -> list[tuple[str, int]]:
    mentions: list[tuple[str, int]] = []
    lowered = question.lower()
    for table in schema.tables:
        _schema_name, _, object_name = table.partition(".")
        candidates = {
            table.lower(),
            object_name.lower(),
            object_name.lower().replace("_", " "),
        }
        positions: list[int] = []
        for candidate in candidates:
            if not candidate:
                continue
            pattern = re.compile(rf"(?<![\w]){re.escape(candidate)}(?![\w])", flags=re.IGNORECASE)
            positions.extend(match.start() for match in pattern.finditer(lowered))
        if positions:
            mentions.append((table, min(positions)))
    return sorted(mentions, key=lambda item: item[1])


def _match_identifier(text: str, schema: SqlSchema) -> tuple[str, str] | None:
    aliases = {
        "site_id": "SITE_ID",
        "site id": "SITE_ID",
        "hole_id": "SITE_ID",
        "hole id": "SITE_ID",
    }
    aliases.update(schema.guidance.identifier_aliases)
    for alias, column in sorted(aliases.items(), key=lambda item: len(item[0]), reverse=True):
        value = _value_after_alias(text, alias)
        if value:
            return column, value
    return None


def _choose_lookup_table(schema: SqlSchema, identifier_column: str, target_column: str) -> str | None:
    table_columns = {
        table: {column.column.lower() for column in columns}
        for table, columns in schema.tables.items()
    }
    priority = [table for table in schema.guidance.table_priority if table in table_columns]
    remaining = [table for table in schema.tables if table not in priority]
    for table in priority + remaining:
        columns = table_columns[table]
        if identifier_column.lower() in columns and target_column.lower() in columns:
            return table
    return None


def _value_after_alias(text: str, alias: str) -> str | None:
    pattern = re.compile(
        rf"(?:^|\b){re.escape(_normalize_phrase(alias))}\b\s*(?:=|:|adalah|is)?\s*'?(?P<value>[\w./-]+)'?",
        flags=re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        return None
    value = match.group("value").strip("'\" ")
    return value or None


def _phrase_in_text(phrase: str, text: str) -> bool:
    return re.search(rf"(?:^|\b){re.escape(_normalize_phrase(phrase))}(?:\b|$)", text, flags=re.IGNORECASE) is not None


def _normalize_phrase(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _sql_string_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


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
            parts = column.split(".")
            if len(parts) >= 3:
                table = ".".join(parts[:-1]).lower()
                name = parts[-1]
                if name.lower() not in table_columns.get(table, set()):
                    raise SqlSafetyError(f"Column is not in cached schema: {column}")
            elif len(parts) == 2 and parts[0].lower() in aliases:
                owner, name = parts
                table = aliases[owner.lower()].lower()
                if name.lower() not in table_columns.get(table, set()):
                    raise SqlSafetyError(f"Column is not in cached schema: {column}")
            elif len(parts) == 2:
                _owner, name = parts
                if name.lower() not in allowed:
                    raise SqlSafetyError(f"Column is not in cached schema: {column}")
            elif parts[0].lower() not in allowed:
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


def _quote_known_table_references(sql: str, schema: SqlSchema) -> str:
    quoted = sql
    for table in sorted(schema.tables, key=len, reverse=True):
        schema_name, _, table_name = table.partition(".")
        if not schema_name or not table_name:
            continue
        replacement = f"[{schema_name}].[{table_name}]"
        pattern = re.compile(rf"(?<![\]\w]){re.escape(table)}(?!\w)", flags=re.IGNORECASE)
        quoted = pattern.sub(replacement, quoted)
    return quoted
