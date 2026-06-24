"""Workspace-bounded filesystem helpers for SecondBrain."""

from __future__ import annotations

import fnmatch
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


EXCLUDED_PATH_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".secondbrain",
    ".tox",
    ".venv",
    "__pycache__",
    "env",
    "node_modules",
    "venv",
}

EXCLUDED_FILE_NAMES = {
    "heartbeat_debug.json",
    "heartbeat_debug.log",
    "memory.db",
}


@dataclass(frozen=True)
class SafePathError(ValueError):
    """Raised when a path escapes the configured workspace."""

    path: str
    reason: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.reason}: {self.path}"


@dataclass(frozen=True)
class WorkspaceEntry:
    """A file or directory inside a workspace."""

    path: str
    name: str
    type: Literal["file", "directory"]


def _excluded_part(path: Path) -> str | None:
    for part in path.parts:
        if part in EXCLUDED_PATH_PARTS:
            return part
    return None


def _is_excluded_listing_path(path: Path) -> bool:
    return bool(_excluded_part(path) or path.name in EXCLUDED_FILE_NAMES)


def ensure_workspace_root_allowed(workspace: str | Path) -> Path:
    """Resolve a workspace root and reject dependency/cache directories."""
    root = Path(workspace).expanduser().resolve()
    excluded = _excluded_part(root)
    if excluded:
        raise SafePathError(str(workspace), f"workspace cannot be inside '{excluded}'")
    return root


def resolve_within_workspace(workspace: str | Path, target: str | Path) -> Path:
    """Resolve a path and ensure it stays inside the workspace root."""
    root = ensure_workspace_root_allowed(workspace)
    candidate = Path(target)
    resolved = candidate if candidate.is_absolute() else (root / candidate)
    resolved = resolved.resolve()

    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise SafePathError(str(target), "path escapes workspace") from exc

    excluded = _excluded_part(resolved)
    if excluded:
        raise SafePathError(str(target), f"path is inside excluded '{excluded}' directory")

    return resolved


def read_text_within_workspace(workspace: str | Path, target: str | Path, *, encoding: str = "utf-8") -> str:
    """Read a text file only if it is inside the workspace."""
    path = resolve_within_workspace(workspace, target)
    if not path.exists():
        raise FileNotFoundError(path)
    if not path.is_file():
        raise IsADirectoryError(path)
    return path.read_text(encoding=encoding)


def write_text_within_workspace(
    workspace: str | Path,
    target: str | Path,
    content: str,
    *,
    encoding: str = "utf-8",
    mkdir: bool = True,
) -> Path:
    """Write text to a file only if it is inside the workspace."""
    path = resolve_within_workspace(workspace, target)
    if mkdir:
        path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding=encoding)
    return path


def append_text_within_workspace(
    workspace: str | Path,
    target: str | Path,
    content: str,
    *,
    encoding: str = "utf-8",
    mkdir: bool = True,
) -> Path:
    """Append text to a file only if it is inside the workspace."""
    path = resolve_within_workspace(workspace, target)
    if mkdir:
        path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding=encoding) as handle:
        handle.write(content)
    return path


def copy_file_within_workspace(
    workspace: str | Path,
    source: str | Path,
    target: str | Path,
    *,
    mkdir: bool = True,
) -> Path:
    """Copy a file within the workspace."""
    src = resolve_within_workspace(workspace, source)
    dst = resolve_within_workspace(workspace, target)
    if not src.exists():
        raise FileNotFoundError(src)
    if not src.is_file():
        raise IsADirectoryError(src)
    if src == dst:
        return dst
    if mkdir:
        dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return dst


def move_file_within_workspace(
    workspace: str | Path,
    source: str | Path,
    target: str | Path,
    *,
    mkdir: bool = True,
) -> Path:
    """Move a file within the workspace."""
    src = resolve_within_workspace(workspace, source)
    dst = resolve_within_workspace(workspace, target)
    if not src.exists():
        raise FileNotFoundError(src)
    if not src.is_file():
        raise IsADirectoryError(src)
    if src == dst:
        return dst
    if mkdir:
        dst.parent.mkdir(parents=True, exist_ok=True)
    src.replace(dst)
    return dst


def list_files_within_workspace(
    workspace: str | Path,
    *,
    pattern: str = "*",
    include_hidden: bool = True,
) -> list[Path]:
    """List matching files below the workspace root."""
    root = ensure_workspace_root_allowed(workspace)
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        rel_dir = current.relative_to(root)
        dirnames[:] = [
            name
            for name in dirnames
            if not _is_excluded_listing_path(rel_dir / name)
            and (include_hidden or not name.startswith("."))
        ]
        for name in filenames:
            if not fnmatch.fnmatch(name, pattern):
                continue
            path = current / name
            rel = path.relative_to(root)
            if _is_excluded_listing_path(rel):
                continue
            if not include_hidden and any(part.startswith(".") for part in rel.parts):
                continue
            files.append(path)
    return sorted(files)


def list_entries_within_workspace(
    workspace: str | Path,
    *,
    include_hidden: bool = True,
    limit: int = 1000,
) -> list[WorkspaceEntry]:
    """List files and directories below the workspace root."""
    root = ensure_workspace_root_allowed(workspace)
    entries: list[WorkspaceEntry] = []
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        rel_dir = current.relative_to(root)
        kept_dirs: list[str] = []
        for name in dirnames:
            rel = rel_dir / name
            if _is_excluded_listing_path(rel):
                continue
            if not include_hidden and name.startswith("."):
                continue
            kept_dirs.append(name)
            entries.append(
                WorkspaceEntry(
                    path=rel.as_posix(),
                    name=name,
                    type="directory",
                )
            )
            if len(entries) >= limit:
                dirnames[:] = []
                return sorted(entries, key=lambda item: (item.path.count("/"), item.type != "directory", item.path.lower()))
        dirnames[:] = kept_dirs

        for name in filenames:
            rel = rel_dir / name
            if _is_excluded_listing_path(rel):
                continue
            if not include_hidden and any(part.startswith(".") for part in rel.parts):
                continue
            entries.append(
                WorkspaceEntry(
                    path=rel.as_posix(),
                    name=name,
                    type="file",
                )
            )
            if len(entries) >= limit:
                dirnames[:] = []
                return sorted(entries, key=lambda item: (item.path.count("/"), item.type != "directory", item.path.lower()))
    return sorted(entries, key=lambda item: (item.path.count("/"), item.type != "directory", item.path.lower()))
