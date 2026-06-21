"""Workspace filesystem skill — read, write, append, and list files safely."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..safe_fs import (
    SafePathError,
    copy_file_within_workspace,
    append_text_within_workspace,
    ensure_workspace_root_allowed,
    list_entries_within_workspace,
    list_files_within_workspace,
    read_text_within_workspace,
    move_file_within_workspace,
    write_text_within_workspace,
)
from ..memory_manager import MemoryManager


class FileSystemSkill:
    """Safe workspace file operations for bot commands and helpers."""

    def __init__(self, workspace: str | Path, memory_manager: MemoryManager | None = None):
        self.workspace = ensure_workspace_root_allowed(workspace)
        self.mm = memory_manager

    def read(self, rel_path: str, *, from_line: Optional[int] = None, lines: Optional[int] = None) -> str:
        text = read_text_within_workspace(self.workspace, rel_path)
        if from_line is None:
            return text

        all_lines = text.splitlines()
        start = max(0, from_line - 1)
        end = len(all_lines)
        if lines is not None:
            end = min(end, start + lines)
        return "\n".join(all_lines[start:end])

    def write(self, rel_path: str, content: str) -> Path:
        path = write_text_within_workspace(self.workspace, rel_path, content)
        if self.mm and path.suffix.lower() == ".md":
            self.mm.index_file(path)
        return path

    def append(self, rel_path: str, content: str) -> Path:
        path = append_text_within_workspace(self.workspace, rel_path, content)
        if self.mm and path.suffix.lower() == ".md":
            self.mm.index_file(path)
        return path

    def copy(self, source: str, target: str) -> Path:
        path = copy_file_within_workspace(self.workspace, source, target)
        if self.mm and path.suffix.lower() == ".md":
            self.mm.index_file(path)
        return path

    def move(self, source: str, target: str) -> Path:
        path = move_file_within_workspace(self.workspace, source, target)
        if self.mm:
            self.mm.remove_indexed_file(source)
            if path.suffix.lower() == ".md":
                self.mm.index_file(path)
        return path

    def list(self, rel_path: str = ".", *, pattern: str = "*.md") -> list[str]:
        base = self.workspace / rel_path
        target_root = base.resolve()
        try:
            target_root.relative_to(self.workspace)
        except ValueError as exc:
            raise SafePathError(rel_path, "path escapes workspace") from exc

        files = list_files_within_workspace(target_root, pattern=pattern)
        return [p.relative_to(self.workspace).as_posix() for p in files]

    def tree(self, rel_path: str = ".", *, limit: int = 1000) -> list[dict[str, str]]:
        base = self.workspace / rel_path
        target_root = base.resolve()
        try:
            target_root.relative_to(self.workspace)
        except ValueError as exc:
            raise SafePathError(rel_path, "path escapes workspace") from exc

        entries = list_entries_within_workspace(target_root, limit=limit)
        prefix = "" if target_root == self.workspace else target_root.relative_to(self.workspace).as_posix()
        out: list[dict[str, str]] = []
        for entry in entries:
            path = f"{prefix}/{entry.path}" if prefix else entry.path
            out.append({"path": path, "name": entry.name, "type": entry.type})
        return out
