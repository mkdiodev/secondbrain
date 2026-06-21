"""Slash command routing for the web chat runtime."""

from __future__ import annotations

import asyncio
import shlex
from collections.abc import Callable
from typing import Any

from .workspace import WorkspaceService


RecordExchange = Callable[[str, str], None]
WorkspaceSwitch = Callable[[str], dict[str, Any]]


class CommandRouter:
    """Handles explicit slash commands before normal LLM chat."""

    def __init__(
        self,
        workspace: WorkspaceService,
        *,
        record_exchange: RecordExchange,
        switch_workspace: WorkspaceSwitch,
    ):
        self.workspace = workspace
        self.record_exchange = record_exchange
        self.switch_workspace = switch_workspace

    def handle(self, message: str) -> dict[str, Any] | None:
        parts = shlex.split(message)
        if not parts:
            return {"error": "Empty message"}

        command = parts[0].lower()
        resources = self.workspace.resources
        mm = resources.mm
        fs = resources.fs_skill
        doc = resources.doc_skill
        dh = resources.dh_skill
        sql = resources.sql_skill

        if command == "/doc":
            topic = " ".join(parts[1:]).strip()
            if not topic:
                return {"error": "Usage: /doc <topic>"}
            filepath, preview = asyncio.run(doc.create(topic, user_request=message))
            rel = filepath.relative_to(mm.workspace).as_posix()
            reply = f"Document created.\n\nPath: {rel}\n\nPreview:\n{preview}"
            self.record_exchange(message, reply)
            return {"reply": reply, "kind": "document", "path": rel}

        if command == "/read":
            if len(parts) < 2:
                return {"error": "Usage: /read <path> [from_line] [lines]"}
            from_line = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
            lines = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else None
            text = fs.read(parts[1], from_line=from_line, lines=lines)
            self.record_exchange(message, text)
            return {"reply": text or "(empty file)", "kind": "file-read", "path": parts[1]}

        if command == "/write":
            if len(parts) < 3:
                return {"error": "Usage: /write <path> <content>"}
            path = fs.write(parts[1], " ".join(parts[2:]))
            rel = path.relative_to(mm.workspace).as_posix()
            reply = f"Wrote {rel}"
            self.record_exchange(message, reply)
            return {"reply": reply, "kind": "file-write", "path": rel}

        if command == "/append":
            if len(parts) < 3:
                return {"error": "Usage: /append <path> <content>"}
            path = fs.append(parts[1], " ".join(parts[2:]))
            rel = path.relative_to(mm.workspace).as_posix()
            reply = f"Appended to {rel}"
            self.record_exchange(message, reply)
            return {"reply": reply, "kind": "file-append", "path": rel}

        if command == "/copy":
            if len(parts) < 3:
                return {"error": "Usage: /copy <source> <target>"}
            path = fs.copy(parts[1], parts[2])
            rel = path.relative_to(mm.workspace).as_posix()
            reply = f"Copied to {rel}"
            self.record_exchange(message, reply)
            return {"reply": reply, "kind": "file-copy", "path": rel}

        if command == "/move":
            if len(parts) < 3:
                return {"error": "Usage: /move <source> <target>"}
            path = fs.move(parts[1], parts[2])
            rel = path.relative_to(mm.workspace).as_posix()
            reply = f"Moved to {rel}"
            self.record_exchange(message, reply)
            return {"reply": reply, "kind": "file-move", "path": rel}

        if command == "/ls":
            target = parts[1] if len(parts) > 1 else "."
            files = fs.list(target)
            reply = "\n".join(files) if files else "(no matching files)"
            self.record_exchange(message, reply)
            return {"reply": reply, "kind": "file-list", "files": files}

        if command == "/search":
            query = " ".join(parts[1:]).strip()
            if not query:
                return {"error": "Usage: /search <query>"}
            results = self.workspace.search_memory(query)
            if not results:
                reply = "No memory results found."
            else:
                reply = "\n\n".join(
                    f"{item['path']}:{item['start_line']}-{item['end_line']}\n{item['snippet']}"
                    for item in results
                )
            self.record_exchange(message, reply)
            return {"reply": reply, "kind": "search", "results": results}

        if command == "/workspace":
            if len(parts) < 2:
                return {"error": "Usage: /workspace <path>"}
            state = self.switch_workspace(" ".join(parts[1:]))
            reply = f"Workspace switched to {state['workspace']}"
            return {
                "reply": reply,
                "kind": "workspace-switch",
                "workspace": state["workspace"],
                "recent_files": state["recent_files"],
            }

        if command == "/dh":
            return self._handle_drillhole(parts, message, dh)

        if command == "/sql":
            return self._handle_sql(parts, message, sql)

        return None

    def _handle_sql(self, parts: list[str], message: str, sql: Any) -> dict[str, Any]:
        if len(parts) < 2:
            return {
                "error": (
                    "Usage: /sql profiles | /sql schema [profile] [--refresh] | "
                    "/sql explain [profile] <question> | /sql ask [profile] <question> | "
                    "/sql run [profile] <SELECT ...>"
                )
            }

        action = parts[1].lower()
        if action == "profiles":
            profiles = sql.list_profiles()
            if not profiles:
                reply = "No SQL Server profiles configured. Set SECOND_BRAIN_SQL_PROFILES and connection env vars."
            else:
                lines = ["SQL Server profiles:"]
                for profile in profiles:
                    status = "configured" if profile["configured"] else "missing connection env"
                    scopes = ", ".join(profile["objects"] or profile["schemas"] or ["dbo"])
                    lines.append(
                        f"- {profile['name']} ({status}) env={profile['connection_env']} "
                        f"scope={scopes} max_rows={profile['max_rows']} timeout={profile['timeout_seconds']}s"
                    )
                reply = "\n".join(lines)
            self.record_exchange(message, reply)
            return {"reply": reply, "kind": "sql", "profiles": profiles}

        if action == "schema":
            profile, rest = self._parse_sql_profile_and_text(parts[2:])
            refresh = "--refresh" in rest.split()
            schema = sql.get_schema(profile, refresh=refresh)
            reply = f"SQL schema cache for profile '{profile}':\n\n{schema.summary()}"
            self.record_exchange(message, reply)
            return {"reply": reply, "kind": "sql"}

        if action == "run":
            profile, query = self._parse_sql_profile_and_text(parts[2:])
            if not query:
                return {"error": "Usage: /sql run [profile] <SELECT ...>"}
            result = sql.run(query, profile_name=profile)
            reply = self._format_sql_result(result)
            self.record_exchange(message, reply)
            return {"reply": reply, "kind": "sql", "sql": result.sql, "rows": result.rows}

        if action == "explain":
            profile, question = self._parse_sql_profile_and_text(parts[2:])
            if not question:
                return {"error": "Usage: /sql explain [profile] <question>"}
            generated = sql.explain(question, profile_name=profile)
            reply = f"Generated read-only SQL:\n\n```sql\n{generated}\n```"
            self.record_exchange(message, reply)
            return {"reply": reply, "kind": "sql", "sql": generated}

        if action == "ask":
            profile, question = self._parse_sql_profile_and_text(parts[2:])
            if not question:
                return {"error": "Usage: /sql ask [profile] <question>"}
            result = sql.ask(question, profile_name=profile)
            reply = self._format_sql_result(result)
            self.record_exchange(message, reply)
            return {"reply": reply, "kind": "sql", "sql": result.sql, "rows": result.rows}

        return {
            "error": (
                "Usage: /sql profiles | /sql schema [profile] [--refresh] | "
                "/sql explain [profile] <question> | /sql ask [profile] <question> | "
                "/sql run [profile] <SELECT ...>"
            )
        }

    def _parse_sql_profile_and_text(self, args: list[str]) -> tuple[str, str]:
        if not args:
            return "default", ""
        known_profiles = set(self.workspace.resources.sql_skill.profiles)
        if args[0] in known_profiles:
            return args[0], " ".join(args[1:]).strip()
        return "default", " ".join(args).strip()

    @staticmethod
    def _format_sql_result(result: Any) -> str:
        lines = [
            "SQL Server query complete.",
            "",
            "SQL:",
            f"```sql\n{result.sql}\n```",
            "",
            f"Rows: {result.row_count}",
        ]
        if not result.rows:
            lines.append("(no rows)")
            return "\n".join(lines)
        columns = result.columns or list(result.rows[0].keys())
        lines.append(" | ".join(columns))
        lines.append(" | ".join("---" for _ in columns))
        for row in result.rows[:20]:
            lines.append(" | ".join(str(row.get(column, "")) for column in columns))
        if result.row_count > 20:
            lines.append(f"... {result.row_count - 20} more rows")
        return "\n".join(lines)

    def _handle_drillhole(self, parts: list[str], message: str, dh: Any) -> dict[str, Any]:
        if len(parts) < 2:
            return {
                "error": (
                    "Usage: /dh config init [path] | /dh config show [path] | "
                    "/dh validate --collar <file> [--survey <file>] [--lithology <file>] "
                    "[--assay <file>] [--config <file>] [--out <file>]"
                )
            }

        section = parts[1].lower()
        if section == "config":
            if len(parts) < 3:
                return {"error": "Usage: /dh config init [path] | /dh config show [path]"}
            action = parts[2].lower()
            path = parts[3] if len(parts) > 3 else None
            if action == "init":
                config_path = dh.init_config()
                reply = f"No init needed. Embedded app userConfig.json is already active.\n\nPath: {config_path}"
                self.record_exchange(message, reply)
                return {"reply": reply, "kind": "dh-validation", "path": config_path.as_posix()}
            if action == "show":
                reply = dh.show_config(path)
                self.record_exchange(message, reply)
                return {"reply": reply, "kind": "dh-validation"}
            return {"error": "Usage: /dh config init [path] | /dh config show [path]"}

        if section == "validate":
            try:
                parsed = self._parse_drillhole_validate_args(parts[2:])
            except ValueError as exc:
                return {"error": str(exc)}
            summary = dh.validate(
                parsed["inputs"],
                config_path=parsed.get("config"),
                out_path=parsed.get("out"),
            )
            reply = self._format_drillhole_summary(summary)
            self.record_exchange(message, reply)
            return {
                "reply": reply,
                "kind": "dh-validation",
                "summary": summary.to_dict(),
                "report_path": summary.report_path,
            }

        return {
            "error": (
                "Usage: /dh config init [path] | /dh config show [path] | "
                "/dh validate --collar <file> [--survey <file>] [--lithology <file>] "
                "[--assay <file>] [--config <file>] [--out <file>]"
            )
        }

    @staticmethod
    def _parse_drillhole_validate_args(args: list[str]) -> dict[str, Any]:
        table_flags = {
            "collar",
            "survey",
            "lithology",
            "assay",
            "mineralization",
            "oxidation",
            "geotech",
            "rqd",
            "vein",
            "alteration",
            "density",
        }
        inputs: dict[str, str] = {}
        parsed: dict[str, Any] = {"inputs": inputs}
        index = 0
        while index < len(args):
            token = args[index]
            if not token.startswith("--"):
                raise ValueError(f"Unexpected argument: {token}")
            key = token[2:].lower().replace("-", "_")
            if index + 1 >= len(args) or args[index + 1].startswith("--"):
                raise ValueError(f"Missing value for {token}")
            value = args[index + 1]
            if key in table_flags:
                inputs[key] = value
            elif key in {"config", "out"}:
                parsed[key] = value
            else:
                raise ValueError(f"Unsupported /dh validate option: {token}")
            index += 2

        if "collar" not in inputs:
            raise ValueError("Usage: /dh validate --collar <file> [--survey <file>] [--lithology <file>] [--assay <file>] [--config <file>] [--out <file>]")
        return parsed

    @staticmethod
    def _format_drillhole_summary(summary: Any) -> str:
        lines = [
            "Drillhole validation complete.",
            "",
            f"Critical errors: {summary.total_errors}",
            f"Warnings: {summary.total_warnings}",
        ]
        if summary.report_path:
            lines.append(f"Report: {summary.report_path}")
        if summary.errors:
            lines.extend(["", "Top findings:"])
            for error in summary.errors[:8]:
                location = f"{error.table} {error.site_id}"
                if error.column:
                    location = f"{location} {error.column}"
                lines.append(f"- [{error.severity}] {location}: {error.message}")
        else:
            lines.extend(["", "No validation issues found."])
        return "\n".join(lines)
