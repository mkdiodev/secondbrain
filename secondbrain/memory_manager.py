"""Core memory manager: indexes markdown files into SQLite + FTS5."""

from __future__ import annotations

import hashlib
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Iterable, List, Optional

from .models import MemoryChunk, MemoryEntry, MemorySearchResult
from .safe_fs import (
    ensure_workspace_root_allowed,
    read_text_within_workspace,
    resolve_within_workspace,
    write_text_within_workspace,
)


class MemoryManager:
    """
    Manages a SecondBrain workspace:
      • soul.md, user.md, agent.md   — persistent identity files
      • memory/YYYY-MM-DD-*.md       — daily logs
      • memory.db                    — SQLite + FTS5 index
    """

    # Files that are always considered memory sources
    ROOT_MEMORY_FILES = ("soul.md", "user.md", "agent.md")
    MEMORY_DIR = "memory"
    DB_NAME = "memory.db"

    def __init__(self, workspace_dir: str | Path):
        self.workspace = ensure_workspace_root_allowed(workspace_dir)
        self.memory_dir = self.workspace / self.MEMORY_DIR
        self.db_path = self.workspace / self.DB_NAME

        self._ensure_dirs()
        self._init_db()

    @contextmanager
    def _connect(self, *, row_factory=None) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        if row_factory is not None:
            conn.row_factory = row_factory
        try:
            yield conn
        finally:
            conn.close()

    # --------------------------------------------------------------------- #
    #  Directory layout
    # --------------------------------------------------------------------- #
    def _ensure_dirs(self) -> None:
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.memory_dir.mkdir(exist_ok=True)

    # --------------------------------------------------------------------- #
    #  SQLite schema
    # --------------------------------------------------------------------- #
    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA foreign_keys=ON;")

            # Meta table (schema version, last sync, etc.)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )

            # Files table — one row per markdown file
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS files (
                    path TEXT PRIMARY KEY,
                    source TEXT NOT NULL DEFAULT 'memory',
                    hash TEXT NOT NULL,
                    mtime INTEGER NOT NULL,
                    size INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                """
            )

            # Chunks table — one row per chunk
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY,
                    path TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'memory',
                    start_line INTEGER NOT NULL,
                    end_line INTEGER NOT NULL,
                    hash TEXT NOT NULL,
                    text TEXT NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks(path);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source);"
            )

            # FTS5 virtual table for full-text search
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                    text,
                    id UNINDEXED,
                    path UNINDEXED,
                    source UNINDEXED,
                    start_line UNINDEXED,
                    end_line UNINDEXED,
                    tokenize='unicode61'
                );
                """
            )

            # Insert schema version if absent
            cur = conn.execute(
                "SELECT value FROM meta WHERE key = 'schema_version';"
            )
            if cur.fetchone() is None:
                conn.execute(
                    "INSERT INTO meta (key, value) VALUES (?, ?);",
                    ("schema_version", "1"),
                )
            conn.commit()

    # --------------------------------------------------------------------- #
    #  Root profile files (soul.md, user.md, agent.md)
    # --------------------------------------------------------------------- #
    def _profile_path(self, name: str) -> Path:
        """soul.md, user.md, agent.md live at workspace root."""
        return self.workspace / f"{name}.md"

    def read_profile(self, name: str) -> str:
        """Read a profile markdown file (soul, user, agent)."""
        path = self._profile_path(name)
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def write_profile(self, name: str, content: str) -> None:
        """Write (or overwrite) a profile markdown file."""
        path = self._profile_path(name)
        write_text_within_workspace(self.workspace, path, content)
        self.index_file(path)

    def ensure_profile(self, name: str, template: str = "") -> str:
        """Create profile file from template if it does not exist."""
        path = self._profile_path(name)
        if not path.exists():
            write_text_within_workspace(self.workspace, path, template)
            self.index_file(path)
        return read_text_within_workspace(self.workspace, path)

    # --------------------------------------------------------------------- #
    #  Daily logs
    # --------------------------------------------------------------------- #
    def daily_log_path(self, date: Optional[datetime] = None) -> Path:
        """Return path for a daily log, e.g. memory/2025-04-25.md"""
        when = date or datetime.now(timezone.utc)
        filename = when.strftime("%Y-%m-%d") + ".md"
        return self.memory_dir / filename

    def append_daily_log(self, title: str, body: str, tags: Optional[List[str]] = None) -> Path:
        """Append an entry to today's daily log (creates the file if needed)."""
        path = self.daily_log_path()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        tag_line = ""
        if tags:
            tag_line = " " + " ".join(f"#{t}" for t in tags)

        entry = f"\n## {title}{tag_line}\n\n*{now}*\n\n{body}\n"

        if path.exists():
            existing = read_text_within_workspace(self.workspace, path)
            # Add header on first write
            if not existing.strip():
                existing = f"# Daily Log: {path.stem}\n"
            content = existing + entry
        else:
            content = f"# Daily Log: {path.stem}\n" + entry

        write_text_within_workspace(self.workspace, path, content)
        self.index_file(path)
        return path

    # --------------------------------------------------------------------- #
    #  Markdown → chunks
    # --------------------------------------------------------------------- #
    @staticmethod
    def chunk_markdown(content: str, max_chars: int = 800, overlap_chars: int = 80) -> List[MemoryChunk]:
        """Split markdown into overlapping chunks by line."""
        lines = content.splitlines()
        if not lines:
            return []

        chunks: List[MemoryChunk] = []
        current_lines: List[str] = []
        current_chars = 0

        def flush() -> None:
            if not current_lines:
                return
            text = "\n".join(current_lines)
            start = 1  # 1-based line numbers
            # Find original line numbers
            # current_lines holds contiguous lines from original
            # We can map by counting from the first line we pushed
            # Simpler: track indices as we go

        # Better approach: track indices explicitly
        buf: List[tuple[int, str]] = []  # (1-based line_no, line)
        buf_chars = 0

        def _flush() -> None:
            nonlocal buf, buf_chars
            if not buf:
                return
            first = buf[0][0]
            last = buf[-1][0]
            text = "\n".join(ln for _, ln in buf)
            chunks.append(MemoryChunk(start_line=first, end_line=last, text=text))
            # Carry overlap
            if overlap_chars > 0 and buf:
                acc = 0
                kept: List[tuple[int, str]] = []
                for idx, ln in reversed(buf):
                    acc += len(ln) + 1
                    kept.insert(0, (idx, ln))
                    if acc >= overlap_chars:
                        break
                buf = kept
                buf_chars = sum(len(ln) + 1 for _, ln in buf)
            else:
                buf = []
                buf_chars = 0

        for i, line in enumerate(lines, start=1):
            line_size = len(line) + 1  # +1 for newline
            if buf_chars + line_size > max_chars and buf:
                _flush()
            buf.append((i, line))
            buf_chars += line_size

        if buf:
            _flush()

        return chunks

    # --------------------------------------------------------------------- #
    #  Indexing
    # --------------------------------------------------------------------- #
    def list_memory_files(self) -> List[Path]:
        """All .md files under workspace root + memory/ directory."""
        files: List[Path] = []
        # Root profiles
        for name in self.ROOT_MEMORY_FILES:
            p = self.workspace / name
            if p.is_file():
                files.append(p)
        # memory/ dir
        if self.memory_dir.exists():
            files.extend(self.memory_dir.rglob("*.md"))
        # documents/ dir
        docs_dir = self.workspace / "documents"
        if docs_dir.exists():
            files.extend(docs_dir.rglob("*.md"))
        # Deduplicate by resolved path
        seen: set[str] = set()
        out: List[Path] = []
        for p in files:
            rp = str(p.resolve())
            if rp not in seen:
                seen.add(rp)
                out.append(p)
        return out

    def index_file(self, file_path: Path) -> None:
        """Index (or re-index) a single markdown file into SQLite + FTS5."""
        abs_path = resolve_within_workspace(self.workspace, file_path)
        rel_path = self._rel_path(abs_path)
        stat = abs_path.stat()
        content = read_text_within_workspace(self.workspace, abs_path)
        file_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        with self._connect() as conn:
            # Check if unchanged
            row = conn.execute(
                "SELECT hash FROM files WHERE path = ?;", (rel_path,)
            ).fetchone()
            if row and row[0] == file_hash:
                return  # no change

            source = self._infer_source(rel_path)

            # Delete old chunks / fts rows
            conn.execute("DELETE FROM chunks WHERE path = ?;", (rel_path,))
            conn.execute("DELETE FROM memory_fts WHERE path = ?;", (rel_path,))

            # Insert / update files row
            conn.execute(
                """
                INSERT INTO files (path, source, hash, mtime, size, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    source=excluded.source,
                    hash=excluded.hash,
                    mtime=excluded.mtime,
                    size=excluded.size,
                    updated_at=excluded.updated_at;
                """,
                (rel_path, source, file_hash, int(stat.st_mtime), stat.st_size, int(datetime.now(timezone.utc).timestamp())),
            )

            # Chunk and insert
            chunks = self.chunk_markdown(content)
            for ch in chunks:
                chunk_id = hashlib.sha256(
                    f"{rel_path}:{ch.start_line}:{ch.end_line}:{ch.hash}".encode()
                ).hexdigest()
                conn.execute(
                    """
                    INSERT INTO chunks (id, path, source, start_line, end_line, hash, text, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (chunk_id, rel_path, source, ch.start_line, ch.end_line, ch.hash, ch.text, int(datetime.now(timezone.utc).timestamp())),
                )
                conn.execute(
                    """
                    INSERT INTO memory_fts (text, id, path, source, start_line, end_line)
                    VALUES (?, ?, ?, ?, ?, ?);
                    """,
                    (ch.text, chunk_id, rel_path, source, ch.start_line, ch.end_line),
                )

            conn.commit()

    def remove_indexed_file(self, file_path: Path) -> None:
        """Remove a file and its chunks from the search index."""
        rel_path = self._rel_path(resolve_within_workspace(self.workspace, file_path))
        with self._connect() as conn:
            conn.execute("DELETE FROM chunks WHERE path = ?;", (rel_path,))
            conn.execute("DELETE FROM memory_fts WHERE path = ?;", (rel_path,))
            conn.execute("DELETE FROM files WHERE path = ?;", (rel_path,))
            conn.commit()

    def sync(self) -> None:
        """Full sync: index every markdown file in the workspace."""
        for p in self.list_memory_files():
            self.index_file(p)
        # Remove entries for deleted files
        current = {self._rel_path(p.resolve()) for p in self.list_memory_files()}
        with self._connect() as conn:
            cur = conn.execute("SELECT path FROM files;")
            for (path,) in cur.fetchall():
                if path not in current:
                    conn.execute("DELETE FROM chunks WHERE path = ?;", (path,))
                    conn.execute("DELETE FROM memory_fts WHERE path = ?;", (path,))
                    conn.execute("DELETE FROM files WHERE path = ?;", (path,))
            conn.commit()

    # --------------------------------------------------------------------- #
    #  Search
    # --------------------------------------------------------------------- #
    def search(
        self,
        query: str,
        *,
        max_results: int = 10,
        source: Optional[str] = None,
    ) -> List[MemorySearchResult]:
        """FTS5 search across all indexed chunks."""
        if not query.strip():
            return []

        # Escape FTS5 special chars
        safe_query = query.replace('"', '""')
        match_expr = f'"{safe_query}"'

        sql = """
            SELECT
                memory_fts.path,
                memory_fts.source,
                memory_fts.start_line,
                memory_fts.end_line,
                memory_fts.text,
                rank
            FROM memory_fts
            WHERE memory_fts MATCH ?
        """
        params: list = [match_expr]
        if source:
            sql += " AND source = ?"
            params.append(source)
        sql += " ORDER BY rank LIMIT ?;"
        params.append(max_results)

        results: List[MemorySearchResult] = []
        with self._connect(row_factory=sqlite3.Row) as conn:
            for row in conn.execute(sql, params):
                snippet = self._snippet(row["text"], query, width=200)
                results.append(
                    MemorySearchResult(
                        path=row["path"],
                        start_line=row["start_line"],
                        end_line=row["end_line"],
                        score=row["rank"] or 0.0,
                        snippet=snippet,
                        source=row["source"],
                    )
                )
        return results

    def read_file(
        self, rel_path: str, from_line: Optional[int] = None, lines: Optional[int] = None
    ) -> str:
        """Read a memory file by relative path, optionally slicing lines."""
        path = resolve_within_workspace(self.workspace, rel_path)
        if not path.exists():
            return ""
        content = read_text_within_workspace(self.workspace, path)
        if from_line is None:
            return content
        all_lines = content.splitlines()
        start = max(0, from_line - 1)
        end = len(all_lines)
        if lines is not None:
            end = min(end, start + lines)
        return "\n".join(all_lines[start:end])

    # --------------------------------------------------------------------- #
    #  Helpers
    # --------------------------------------------------------------------- #
    def _rel_path(self, abs_path: Path) -> str:
        """Path relative to workspace, forward slashes."""
        try:
            return abs_path.relative_to(self.workspace).as_posix()
        except ValueError:
            return abs_path.name

    def _infer_source(self, rel_path: str) -> str:
        """Guess source type from relative path."""
        lowered = rel_path.lower()
        if lowered in ("soul.md", "user.md", "agent.md"):
            return lowered.replace(".md", "")
        if lowered.startswith("memory/"):
            return "daily" if lowered.endswith(".md") else "memory"
        return "memory"

    @staticmethod
    def _snippet(text: str, query: str, width: int = 200) -> str:
        """Return a snippet around first query match, or start of text."""
        low = text.lower()
        qlow = query.lower()
        idx = low.find(qlow)
        if idx == -1:
            return text[:width]
        start = max(0, idx - width // 2)
        end = min(len(text), idx + len(query) + width // 2)
        snippet = text[start:end]
        if start > 0:
            snippet = "…" + snippet
        if end < len(text):
            snippet = snippet + "…"
        return snippet
