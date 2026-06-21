"""Data models for SecondBrain memory system."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class MemoryChunk:
    """A chunk of text from a memory file, ready for indexing."""

    start_line: int
    end_line: int
    text: str
    hash: str = field(default="")

    def __post_init__(self):
        if not self.hash:
            self.hash = hashlib.sha256(self.text.encode("utf-8")).hexdigest()


@dataclass
class MemoryEntry:
    """A single memory entry (e.g. a daily log or profile update)."""

    source: str          # e.g. "daily", "session", "user", "agent", "soul"
    path: str            # relative path within the workspace
    content: str         # raw markdown content
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    tags: list[str] = field(default_factory=list)
    title: str = ""

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


@dataclass
class MemorySearchResult:
    """Result from a memory search query."""

    path: str
    start_line: int
    end_line: int
    score: float
    snippet: str
    source: str
    title: str = ""
