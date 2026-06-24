"""Small controlled tool loop for natural-language file questions."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Any

from secondbrain.llm_client import LocalLLMClient

from .dh_format import format_drillhole_summary
from .dh_routing import infer_drillhole_validation_action
from .workspace import WorkspaceResources, WorkspaceService


READ_ONLY_TOOLS = {
    "list_files",
    "read_file",
    "search_memory",
    "validate_drillhole",
    "query_sql_server",
    "none",
}
TOOL_INTENT_PATTERN = re.compile(
    r"\b("
    r"list|show|read|open|lihat|baca|daftar|tampilkan|cari|search|find|file|folder|"
    r"workspace|directory|direktori|validate|validasi|validator|drillhole|collar|survey|"
    r"lithology|assay|mineralization|oxidation|geotech|rqd|vein|alteration|density|xlsx|csv|"
    r"sql|database|db|query|tabel|table|kolom|column|server|site_id|hole_id|end_depth|depth|"
    r"lubang|lobang|kedalaman|elevasi|koordinat"
    r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ToolObservation:
    tool: str
    args: dict[str, Any]
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


class AgentToolLoop:
    """Lets the LLM choose one safe read-only workspace tool before replying."""

    def __init__(self, workspace: WorkspaceService, llm: LocalLLMClient):
        self.workspace = workspace
        self.llm = llm

    def should_consider_tools(self, message: str) -> bool:
        return bool(TOOL_INTENT_PATTERN.search(message))

    def run(
        self,
        message: str,
        *,
        system_prompt: str,
        history: list[dict[str, str]],
    ) -> dict[str, Any] | None:
        if not self.should_consider_tools(message):
            return None

        resources = self.workspace.resources
        action = infer_drillhole_validation_action(
            message,
            workspace=str(resources.mm.workspace),
            workspace_files=self.workspace.workspace_files(limit=1000),
        ) or self._plan_action(message, resources)
        if action["tool"] == "none":
            return None
        action = dict(action)
        action["_user_message"] = message

        observation = self._execute_action(action)
        if observation.tool == "validate_drillhole":
            return {
                "reply": observation.content,
                "kind": "tool-chat",
                "summary": observation.metadata.get("summary"),
                "tools": [
                    {
                        "tool": observation.tool,
                        "args": observation.args,
                    }
                ],
            }
        if observation.tool == "query_sql_server":
            direct_reply = self._direct_sql_reply(message, observation)
            if direct_reply is not None:
                return {
                    "reply": direct_reply,
                    "kind": "tool-chat",
                    "sql_result": observation.metadata.get("sql_result"),
                    "tools": [
                        {
                            "tool": observation.tool,
                            "args": observation.args,
                        }
                    ],
                }
        reply = self._final_reply(
            message,
            system_prompt=system_prompt,
            history=history,
            observation=observation,
        )
        return {
            "reply": reply,
            "kind": "tool-chat",
            "sql_result": observation.metadata.get("sql_result") if observation.tool == "query_sql_server" else None,
            "tools": [
                {
                    "tool": observation.tool,
                    "args": observation.args,
                }
            ],
        }

    def _plan_action(self, message: str, resources: WorkspaceResources) -> dict[str, Any]:
        prompt = "\n".join(
            [
                "Choose at most one read-only workspace tool for the user request.",
                "Return JSON only. Do not add prose.",
                "",
                "Available tools:",
                '- {"tool":"list_files","path":"."}',
                '- {"tool":"read_file","path":"notes/example.md","from_line":1,"lines":80}',
                '- {"tool":"search_memory","query":"topic"}',
                '- {"tool":"validate_drillhole","inputs":{"collar":"collar.csv","lithology":"lithology.xlsx"}}',
                '- {"tool":"query_sql_server","profile":"default","question":"show the latest customers"}',
                '- {"tool":"none"}',
                "",
                "Rules:",
                "- Use only read-only tools.",
                "- Never choose write, append, copy, move, delete, or overwrite.",
                "- Natural drillhole validation may read CSV/XLSX files and return a summary.",
                "- Do not create validation report files from natural language; report writing requires an explicit /dh command.",
                "- SQL Server queries are read-only and must use the SQL tool; never invent database results yourself.",
                "- Use query_sql_server only when the user explicitly asks about SQL, database, tables, or database records.",
                "- Also use query_sql_server when the user asks for a value by database-like fields such as SITE_ID, HOLE_ID, END_DEPTH, DEPTH_FROM, or DEPTH_TO.",
                "- If a user asks 'berapa <column> dari <id column> <value>', treat it as a database record lookup.",
                "- If the user asks to modify non-validation files, choose none.",
                "- Paths must be workspace-relative.",
                "- For validate_drillhole, infer table names from words or filenames such as collar, survey, lithology, assay, mineralization, oxidation, geotech, rqd, vein, alteration, density.",
                f"Workspace: {resources.mm.workspace}",
                f"Recent files: {', '.join(self.workspace.recent_files(limit=20)) or '(none)'}",
                f"SQL profiles: {', '.join(resources.sql_skill.profiles) or '(none configured)'}",
                "",
                f"User request: {message}",
            ]
        )
        raw = asyncio.run(
            self.llm.chat(
                [
                    {"role": "system", "content": "You are a strict JSON tool planner."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
            )
        )
        action = self._parse_action(raw)
        if action["tool"] == "none" and self._looks_like_sql_record_lookup(message) and resources.sql_skill.profiles:
            return {"tool": "query_sql_server", "profile": "default", "question": message}
        if action["tool"] not in READ_ONLY_TOOLS:
            return {"tool": "none"}
        if action["tool"] == "read_file" and not str(action.get("path") or "").strip():
            return {"tool": "none"}
        if action["tool"] == "search_memory" and not str(action.get("query") or "").strip():
            return {"tool": "none"}
        if action["tool"] == "validate_drillhole":
            inputs = action.get("inputs")
            if not isinstance(inputs, dict) or not inputs:
                return {"tool": "none"}
        if action["tool"] == "query_sql_server":
            if not resources.sql_skill.profiles:
                return {"tool": "none"}
            if not str(action.get("question") or "").strip():
                return {"tool": "none"}
        return action

    def _execute_action(self, action: dict[str, Any]) -> ToolObservation:
        tool = action["tool"]
        resources = self.workspace.resources

        if tool == "list_files":
            path = str(action.get("path") or ".")
            files = resources.fs_skill.list(path)
            content = "\n".join(files) if files else "(no matching files)"
            return ToolObservation(tool=tool, args={"path": path}, content=content)

        if tool == "read_file":
            path = str(action.get("path") or "")
            from_line = self._optional_int(action.get("from_line"))
            lines = self._optional_int(action.get("lines")) or 80
            text = resources.fs_skill.read(path, from_line=from_line, lines=min(lines, 200))
            return ToolObservation(
                tool=tool,
                args={"path": path, "from_line": from_line, "lines": min(lines, 200)},
                content=text[:12000] or "(empty file)",
            )

        if tool == "search_memory":
            query = str(action.get("query") or "").strip()
            results = self.workspace.search_memory(query, limit=5)
            if not results:
                content = "No memory results found."
            else:
                content = "\n\n".join(
                    f"{item['path']}:{item['start_line']}-{item['end_line']}\n{item['snippet']}"
                    for item in results
                )
            return ToolObservation(tool=tool, args={"query": query}, content=content)

        if tool == "validate_drillhole":
            validation_error = str(action.get("_validation_error") or "").strip()
            if validation_error:
                return ToolObservation(
                    tool=tool,
                    args={"inputs": action.get("inputs") or {}},
                    content=validation_error,
                )
            inputs = {
                str(table): str(path)
                for table, path in (action.get("inputs") or {}).items()
                if str(table).strip() and str(path).strip()
            }
            summary = resources.dh_skill.validate(inputs)
            content = format_drillhole_summary(summary)
            return ToolObservation(
                tool=tool,
                args={"inputs": inputs},
                content=content,
                metadata={"summary": summary.to_dict()},
            )

        if tool == "query_sql_server":
            profile = str(action.get("profile") or "default").strip()
            question = str(action.get("question") or "").strip()
            user_message = str(action.get("_user_message") or question).strip()
            result = resources.sql_skill.lookup_record(user_message, profile_name=profile)
            if result is None:
                result = resources.sql_skill.ask(question, profile_name=profile)
            content = self._format_sql_result(result)
            sql_result = self._sql_result_payload(result, profile=profile, question=question)
            return ToolObservation(
                tool=tool,
                args={
                    "profile": profile,
                    "question": question,
                    "columns": result.columns,
                    "rows": result.rows,
                },
                content=content,
                metadata={"sql_result": sql_result},
            )

        return ToolObservation(tool="none", args={}, content="")

    def _final_reply(
        self,
        message: str,
        *,
        system_prompt: str,
        history: list[dict[str, str]],
        observation: ToolObservation,
    ) -> str:
        tool_context = "\n".join(
            [
                "A read-only workspace tool was used for this user request.",
                f"Tool: {observation.tool}",
                f"Arguments: {json.dumps(observation.args, ensure_ascii=False)}",
                "",
                "Tool result:",
                observation.content,
                "",
                "Answer the user naturally. If the result is a file listing or file content, summarize it clearly.",
            ]
        )
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": message})
        messages.append({"role": "system", "content": tool_context})
        return asyncio.run(self.llm.chat(messages))

    @staticmethod
    def _parse_action(raw: str) -> dict[str, Any]:
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text).strip()
            text = re.sub(r"```$", "", text).strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, flags=re.DOTALL)
            if not match:
                return {"tool": "none"}
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                return {"tool": "none"}

        if not isinstance(data, dict):
            return {"tool": "none"}
        tool = str(data.get("tool") or "none")
        data["tool"] = tool
        return data

    @staticmethod
    def _looks_like_sql_record_lookup(message: str) -> bool:
        text = message.lower()
        has_identifier = re.search(r"\b(site_id|hole_id)\b", text) is not None
        has_requested_field = re.search(r"\b(end_depth|depth_from|depth_to|easting|northing|elevation|project|iup)\b", text) is not None
        has_lookup_word = re.search(r"\b(berapa|apa|tampilkan|show|nilai|value)\b", text) is not None
        return has_identifier and has_requested_field and has_lookup_word

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    @staticmethod
    def _format_sql_result(result: Any) -> str:
        lines = [
            "SQL Server query result:",
            f"SQL: {result.sql}",
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

    @staticmethod
    def _sql_result_payload(result: Any, *, profile: str, question: str) -> dict[str, Any]:
        return {
            "profile": profile,
            "question": question,
            "sql": result.sql,
            "columns": result.columns or (list(result.rows[0].keys()) if result.rows else []),
            "rows": result.rows,
            "row_count": result.row_count,
            "truncated": getattr(result, "truncated", False),
        }

    @staticmethod
    def _direct_sql_reply(message: str, observation: ToolObservation) -> str | None:
        columns = observation.args.get("columns") or []
        rows = observation.args.get("rows") or []
        if len(rows) != 1:
            return None
        site_match = re.search(r"\b(site_id|hole_id|lubang|lobang)\b\s*(?:=|adalah|is|:)?\s*'?([\w/-]+)'?", message, re.IGNORECASE)
        if len(columns) > 1:
            heading = "Hasil query"
            if site_match:
                heading = f"Hasil query untuk {site_match.group(1).lower()} {site_match.group(2)}"
            lines = [f"{heading}:"]
            for column in columns:
                lines.append(f"- {column}: {rows[0].get(column)}")
            return "\n".join(lines)
        if len(columns) != 1:
            return None
        column = str(columns[0])
        value = rows[0].get(column)
        if value is None:
            return None
        if site_match:
            id_label = site_match.group(1).lower()
            site_id = site_match.group(2)
            return f"{column.lower()} dari {id_label} {site_id} adalah {value}"
        return f"{column} adalah {value}"
