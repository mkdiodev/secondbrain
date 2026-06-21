"""Application runtime facade for the SecondBrain web UI."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from secondbrain.llm_client import LocalLLMClient
from secondbrain.safe_fs import SafePathError
from secondbrain.skills.sql_server_skill import SqlServerAdapter

from .commands import CommandRouter
from .config import UIConfig
from .history import HistoryStore
from .tool_loop import AgentToolLoop
from .workspace import WorkspaceResources, WorkspaceService

logger = logging.getLogger("secondbrain.ui")


class ChatRuntime:
    """Coordinates workspace state, command routing, history, and LLM chat."""

    def __init__(
        self,
        config: UIConfig,
        llm: LocalLLMClient | None = None,
        *,
        sql_adapter: SqlServerAdapter | None = None,
    ):
        self.config = config
        self.llm = llm or LocalLLMClient(
            base_url=config.ollama_base_url,
            model=config.ollama_model,
            provider=config.llm_provider,
        )
        self.history = HistoryStore()
        self.workspace = WorkspaceService(config.workspace, self.llm, sql_adapter=sql_adapter)
        self.history.ensure_workspace(self.workspace.key)
        self.commands = CommandRouter(
            self.workspace,
            record_exchange=self._record_exchange,
            switch_workspace=self.set_workspace,
        )
        self.tool_loop = AgentToolLoop(self.workspace, self.llm)

    def state(self) -> dict[str, Any]:
        return self.workspace.state(
            model=self.llm.model,
            base_url=self.llm.base_url,
            provider=getattr(self.llm, "provider", self.config.llm_provider),
            history_count=self.history.count(self.workspace.key),
        )

    def set_workspace(self, workspace: str) -> dict[str, Any]:
        resources = self.workspace.switch(workspace)
        self.history.ensure_workspace(resources.key)
        return self.state()

    def history_snapshot(self) -> list[dict[str, str]]:
        return self.history.snapshot(self.workspace.key)

    def clear_history(self) -> None:
        self.history.clear(self.workspace.key)

    def search_memory(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        return self.workspace.search_memory(query, limit=limit)

    def handle_message(self, message: str) -> dict[str, Any]:
        message = message.strip()
        if not message:
            return {"error": "Empty message"}

        try:
            if message.startswith("/"):
                command_result = self.commands.handle(message)
                if command_result is not None:
                    return command_result
            return self._handle_chat(message)
        except SafePathError as exc:
            return {"error": str(exc)}
        except ValueError as exc:
            return {"error": str(exc)}
        except Exception as exc:  # pragma: no cover - surfaced in UI
            logger.exception("Message handling failed")
            return {"error": str(exc)}

    def _handle_chat(self, message: str) -> dict[str, Any]:
        resources = self.workspace.resources
        system_prompt = self._build_system_prompt(resources)
        history = self.history.recent(resources.key, limit=16)
        tool_result = self.tool_loop.run(
            message,
            system_prompt=system_prompt,
            history=history,
        )
        if tool_result is not None:
            self._record_exchange(message, tool_result["reply"])
            return tool_result

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": message})

        try:
            reply = asyncio.run(self.llm.chat(messages))
        except Exception as exc:  # pragma: no cover - surfaced in UI
            logger.exception("LLM chat failed")
            return {"error": str(exc)}

        self._record_exchange(message, reply)
        return {"reply": reply, "kind": "chat"}

    def _record_exchange(self, user_text: str, assistant_text: str) -> None:
        resources = self.workspace.resources
        self.history.append_exchange(resources.key, user_text, assistant_text)

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        resources.mm.append_daily_log(
            "Web Chat",
            f"**User ({now}):**\n{user_text}\n\n**Assistant ({now}):**\n{assistant_text}\n",
        )

    def _build_system_prompt(self, resources: WorkspaceResources) -> str:
        return "\n".join(
            [
                "You are SecondBrain, a compact local assistant with a calm, Codex-inspired chat UI.",
                "",
                "=== SOUL ===",
                resources.mm.read_profile("soul") or "(empty)",
                "",
                "=== USER ===",
                resources.mm.read_profile("user") or "(empty)",
                "",
                "=== AGENT ===",
                resources.mm.read_profile("agent") or "(empty)",
                "",
                "=== TODAY'S LOG ===",
                self.workspace.read_today_log() or "(empty)",
                "",
                "Reply naturally and be useful.",
                "If the user asks to create a document, you can use /doc.",
                "If they ask about files, /read, /write, /append, /copy, /move, /ls, and /search are available.",
                "For drillhole data validation, use explicit /dh commands; do not write validation reports without a slash command.",
                "For SQL Server questions, use /sql or the read-only SQL Server tool; never invent tables or columns outside the cached schema.",
            ]
        )
