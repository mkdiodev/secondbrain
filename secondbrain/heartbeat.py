#!/usr/bin/env python3
"""Heartbeat system for SecondBrain — inspired by OpenClaw.

Runs every 30 minutes, reads memory files, asks the local LLM if anything
is worth notifying the user about. Only sends Telegram messages when the
LLM returns actionable content (not HEARTBEAT_OK / empty). Prevents
re-notifying about the same content within 24 hours.

Logs all activity to heartbeat_debug.log and persistence to heartbeat_debug.json.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .config import BotConfig
from .llm_client import LocalLLMClient
from .memory_manager import MemoryManager

# Debug logger — always writes to heartbeat_debug.log
heartbeat_logger = logging.getLogger("secondbrain.heartbeat")
heartbeat_logger.setLevel(logging.DEBUG)

# Prevent duplicate handlers if module is reloaded
if not heartbeat_logger.handlers:
    _debug_handler = logging.FileHandler("heartbeat_debug.log", mode="a")
    _debug_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    heartbeat_logger.addHandler(_debug_handler)

# Persistence file for deduplication state
DEBUG_STATE_FILE = "heartbeat_debug.json"
HEARTBEAT_INTERVAL_SECONDS = 30 * 60  # 30 minutes
DEDUPE_WINDOW_SECONDS = 24 * 60 * 60  # 24 hours
HEARTBEAT_OK_PATTERN = re.compile(r"^\s*HEARTBEAT_OK\s*$", re.IGNORECASE)


@dataclass
class HeartbeatState:
    """Persistent state to prevent re-notifying within 24h."""

    last_notification_hash: Optional[str] = None
    last_notification_time: Optional[float] = None
    notification_history: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "last_notification_hash": self.last_notification_hash,
            "last_notification_time": self.last_notification_time,
            "notification_history": self.notification_history,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "HeartbeatState":
        return cls(
            last_notification_hash=data.get("last_notification_hash"),
            last_notification_time=data.get("last_notification_time"),
            notification_history=data.get("notification_history", []),
        )


class HeartbeatService:
    """
    Periodic heartbeat that checks whether the user should be notified.

    Flow (inspired by OpenClaw):
      1. Build context from soul.md + user.md + agent.md + today's log
      2. Ask LLM: "Given this context, is there anything worth notifying me about?"
      3. If response is empty / HEARTBEAT_OK → skip silently
      4. If response is meaningful → check 24h deduplication window
      5. If not a duplicate → send Telegram message
      6. Append heartbeat run to daily log (internal housekeeping)
      7. Log everything to heartbeat_debug.log
    """

    def __init__(
        self,
        config: BotConfig,
        memory_manager: MemoryManager,
        llm_client: LocalLLMClient,
        telegram_app=None,  # python-telegram-bot Application
    ):
        self.cfg = config
        self.mm = memory_manager
        self.llm = llm_client
        self.app = telegram_app
        self._running = False
        self._task: Optional[asyncio.Task] = None

        self.state_path = Path(config.workspace) / DEBUG_STATE_FILE
        self.state = self._load_state()

    # ------------------------------------------------------------------ #
    #  State persistence (deduplication)
    # ------------------------------------------------------------------ #
    def _load_state(self) -> HeartbeatState:
        if self.state_path.exists():
            try:
                with self.state_path.open("r", encoding="utf-8") as f:
                    return HeartbeatState.from_dict(json.load(f))
            except Exception as exc:
                heartbeat_logger.warning("Failed to load heartbeat state: %s", exc)
        return HeartbeatState()

    def _save_state(self) -> None:
        try:
            with self.state_path.open("w", encoding="utf-8") as f:
                json.dump(self.state.to_dict(), f, indent=2, default=str)
        except Exception as exc:
            heartbeat_logger.warning("Failed to save heartbeat state: %s", exc)

    @staticmethod
    def _content_hash(text: str) -> str:
        """Stable hash for deduplication."""
        normalized = re.sub(r"\s+", " ", text.strip().lower())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _is_duplicate(self, text: str) -> bool:
        """Check if this notification was already sent within 24h."""
        if self.state.last_notification_hash is None:
            return False
        if self.state.last_notification_time is None:
            return False
        now = time.time()
        age = now - self.state.last_notification_time
        if age > DEDUPE_WINDOW_SECONDS:
            heartbeat_logger.debug("Previous notification older than 24h; allowing new one.")
            return False
        current_hash = self._content_hash(text)
        if current_hash == self.state.last_notification_hash:
            heartbeat_logger.info(
                "Duplicate notification suppressed (same hash, age=%.1fh).", age / 3600
            )
            return True
        return False

    def _record_notification(self, text: str) -> None:
        now = time.time()
        h = self._content_hash(text)
        self.state.last_notification_hash = h
        self.state.last_notification_time = now
        self.state.notification_history.append(
            {
                "hash": h,
                "time": now,
                "iso": datetime.now(timezone.utc).isoformat(),
                "preview": text[:200],
            }
        )
        # Trim history to last 100 entries
        self.state.notification_history = self.state.notification_history[-100:]
        self._save_state()

    # ------------------------------------------------------------------ #
    #  Context building
    # ------------------------------------------------------------------ #
    def _build_context(self) -> dict:
        return {
            "soul": self.mm.read_profile("soul"),
            "user": self.mm.read_profile("user"),
            "agent": self.mm.read_profile("agent"),
            "today": self._read_today_log(),
        }

    def _read_today_log(self) -> str:
        path = self.mm.daily_log_path()
        if path.exists():
            return path.read_text(encoding="utf-8")
        return "(No entries yet today)"

    @staticmethod
    def _build_heartbeat_prompt(ctx: dict) -> str:
        parts = [
            "You are the SecondBrain heartbeat monitor. Your job is to decide whether the user needs a notification right now.",
            "",
            "=== SOUL (core identity & values) ===",
            ctx["soul"] or "(empty)",
            "",
            "=== USER PROFILE ===",
            ctx["user"] or "(empty)",
            "",
            "=== AGENT PROFILE ===",
            ctx["agent"] or "(empty)",
            "",
            "=== TODAY'S LOG ===",
            ctx["today"] or "(empty)",
            "",
            "Instructions:",
            "- Review the context above.",
            "- Is there anything urgent, time-sensitive, or important the user should know?",
            "- If nothing needs attention, reply with exactly: HEARTBEAT_OK",
            "- If there IS something to notify, write a concise, actionable message (1-3 sentences).",
            "- Do not invent fake reminders. Only notify if context genuinely suggests it.",
        ]
        return "\n".join(parts)

    # ------------------------------------------------------------------ #
    #  Core heartbeat run
    # ------------------------------------------------------------------ #
    async def run_once(self) -> None:
        started_at = time.time()
        heartbeat_logger.info("Heartbeat started.")

        context = self._build_context()
        prompt = self._build_heartbeat_prompt(context)

        messages = [{"role": "system", "content": prompt}]

        try:
            response = await self.llm.chat(messages, temperature=0.3)
        except Exception as exc:
            heartbeat_logger.exception("LLM call failed during heartbeat")
            self._append_heartbeat_log(started_at, success=False, error=str(exc))
            return

        heartbeat_logger.debug("LLM raw response: %r", response)

        # Determine if response is effectively empty / HEARTBEAT_OK
        stripped = response.strip()
        if not stripped or HEARTBEAT_OK_PATTERN.match(stripped):
            heartbeat_logger.info("Heartbeat returned HEARTBEAT_OK — nothing to notify.")
            self._append_heartbeat_log(started_at, success=True, notified=False, response=stripped)
            return

        # Check 24h deduplication
        if self._is_duplicate(stripped):
            heartbeat_logger.info("Heartbeat content is duplicate within 24h — skipping Telegram.")
            self._append_heartbeat_log(
                started_at, success=True, notified=False, reason="duplicate", response=stripped
            )
            return

        # Send Telegram notification
        if self.app is not None:
            try:
                await self.app.bot.send_message(
                    chat_id=self.cfg.allowed_user_id,
                    text=f"🔔 *Heartbeat*\n\n{stripped}",
                    parse_mode="Markdown",
                )
                heartbeat_logger.info("Telegram notification sent.")
                self._record_notification(stripped)
                self._append_heartbeat_log(
                    started_at, success=True, notified=True, response=stripped
                )
            except Exception as exc:
                heartbeat_logger.exception("Failed to send Telegram notification")
                self._append_heartbeat_log(
                    started_at, success=False, error=f"telegram: {exc}", response=stripped
                )
        else:
            heartbeat_logger.warning("No Telegram app configured — notification would have been: %s", stripped)
            self._append_heartbeat_log(
                started_at, success=True, notified=False, reason="no-telegram-app", response=stripped
            )

    def _append_heartbeat_log(
        self,
        started_at: float,
        success: bool,
        notified: Optional[bool] = None,
        response: Optional[str] = None,
        reason: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        duration_ms = int((time.time() - started_at) * 1000)
        entry = {
            "type": "heartbeat_run",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration_ms": duration_ms,
            "success": success,
        }
        if notified is not None:
            entry["notified"] = notified
        if response is not None:
            entry["response_preview"] = response[:500]
        if reason is not None:
            entry["reason"] = reason
        if error is not None:
            entry["error"] = error

        # Also append to today's daily log for visibility
        body_lines = [f"- **Success:** {success}", f"- **Duration:** {duration_ms}ms"]
        if notified is not None:
            body_lines.append(f"- **Notified:** {notified}")
        if reason:
            body_lines.append(f"- **Reason:** {reason}")
        if error:
            body_lines.append(f"- **Error:** {error}")
        if response:
            body_lines.append(f"- **Response:** {response[:300]}")
        self.mm.append_daily_log("Heartbeat Run", "\n".join(body_lines))

    # ------------------------------------------------------------------ #
    #  Scheduling loop
    # ------------------------------------------------------------------ #
    async def _loop(self) -> None:
        """Run heartbeat every 30 minutes."""
        heartbeat_logger.info("Heartbeat scheduler started (interval=%ds).", HEARTBEAT_INTERVAL_SECONDS)
        while self._running:
            try:
                await self.run_once()
            except Exception:
                heartbeat_logger.exception("Unexpected error in heartbeat loop")
            # Sleep in 1-second increments so we can stop cleanly
            slept = 0
            while self._running and slept < HEARTBEAT_INTERVAL_SECONDS:
                await asyncio.sleep(1)
                slept += 1

    def start(self) -> None:
        """Start the background heartbeat task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        heartbeat_logger.info("Heartbeat service started.")

    async def stop(self) -> None:
        """Stop the heartbeat gracefully."""
        if not self._running:
            return
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        heartbeat_logger.info("Heartbeat service stopped.")
