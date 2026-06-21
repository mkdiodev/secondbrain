"""Workspace state and helpers for the web UI runtime."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

from secondbrain.llm_client import LocalLLMClient
from secondbrain.memory_manager import MemoryManager
from secondbrain.skills import DocumentSkill, DrillholeValidationSkill, FileSystemSkill, SqlServerSkill
from secondbrain.skills.sql_server_skill import SqlServerAdapter


@dataclass(frozen=True)
class WorkspaceResources:
    key: str
    mm: MemoryManager
    doc_skill: DocumentSkill
    dh_skill: DrillholeValidationSkill
    fs_skill: FileSystemSkill
    sql_skill: SqlServerSkill


class WorkspaceService:
    """Owns the active workspace and derived skill instances."""

    def __init__(
        self,
        initial_workspace: str,
        llm: LocalLLMClient,
        *,
        sql_adapter: SqlServerAdapter | None = None,
    ):
        self._llm = llm
        self._sql_adapter = sql_adapter
        self._lock = Lock()
        self._resources = self._create_resources(initial_workspace)

    @property
    def resources(self) -> WorkspaceResources:
        with self._lock:
            return self._resources

    @property
    def key(self) -> str:
        return self.resources.key

    def switch(self, workspace: str) -> WorkspaceResources:
        resources = self._create_resources(workspace)
        with self._lock:
            self._resources = resources
        return resources

    def state(
        self,
        *,
        model: str,
        base_url: str,
        provider: str,
        history_count: int,
    ) -> dict[str, Any]:
        resources = self.resources
        return {
            "workspace": str(resources.mm.workspace),
            "model": model,
            "base_url": base_url,
            "llm_provider": provider,
            "recent_files": self.recent_files(),
            "workspace_files": self.workspace_files(),
            "workspace_entries": self.workspace_entries(),
            "profiles": {
                "soul": resources.mm.read_profile("soul"),
                "user": resources.mm.read_profile("user"),
                "agent": resources.mm.read_profile("agent"),
            },
            "today_log": self.read_today_log(),
            "history_count": history_count,
        }

    def recent_files(self, limit: int = 12) -> list[str]:
        return self.resources.fs_skill.list(".")[:limit]

    def workspace_files(self, limit: int = 300) -> list[str]:
        return self.resources.fs_skill.list(".")[:limit]

    def workspace_entries(self, limit: int = 1000) -> list[dict[str, str]]:
        return self.resources.fs_skill.tree(".", limit=limit)

    def search_memory(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        results = self.resources.mm.search(query, max_results=limit)
        return [
            {
                "path": item.path,
                "source": item.source,
                "start_line": item.start_line,
                "end_line": item.end_line,
                "score": item.score,
                "snippet": item.snippet,
            }
            for item in results
        ]

    def read_today_log(self) -> str:
        path = self.resources.mm.daily_log_path()
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    def _create_resources(self, workspace: str) -> WorkspaceResources:
        resolved = str(Path(workspace).expanduser().resolve())
        mm = MemoryManager(resolved)
        doc_skill = DocumentSkill(mm, self._llm)
        dh_skill = DrillholeValidationSkill(mm.workspace)
        fs_skill = FileSystemSkill(mm.workspace, memory_manager=mm)
        sql_skill = SqlServerSkill.from_env(adapter=self._sql_adapter, llm=self._llm)
        return WorkspaceResources(
            key=str(mm.workspace),
            mm=mm,
            doc_skill=doc_skill,
            dh_skill=dh_skill,
            fs_skill=fs_skill,
            sql_skill=sql_skill,
        )
