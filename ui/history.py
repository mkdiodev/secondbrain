"""In-memory chat history storage for the web UI."""

from __future__ import annotations

from threading import Lock


class HistoryStore:
    """Keeps separate chat histories for each selected workspace."""

    def __init__(self) -> None:
        self._histories: dict[str, list[dict[str, str]]] = {}
        self._lock = Lock()

    def ensure_workspace(self, workspace_key: str) -> None:
        with self._lock:
            self._histories.setdefault(workspace_key, [])

    def snapshot(self, workspace_key: str) -> list[dict[str, str]]:
        with self._lock:
            return list(self._histories.setdefault(workspace_key, []))

    def clear(self, workspace_key: str) -> None:
        with self._lock:
            self._histories.setdefault(workspace_key, []).clear()

    def append_exchange(self, workspace_key: str, user_text: str, assistant_text: str) -> None:
        with self._lock:
            history = self._histories.setdefault(workspace_key, [])
            history.append({"role": "user", "content": user_text})
            history.append({"role": "assistant", "content": assistant_text})

    def recent(self, workspace_key: str, limit: int) -> list[dict[str, str]]:
        with self._lock:
            return list(self._histories.setdefault(workspace_key, [])[-limit:])

    def count(self, workspace_key: str) -> int:
        with self._lock:
            return len(self._histories.setdefault(workspace_key, []))
