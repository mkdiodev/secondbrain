#!/usr/bin/env python3
"""Telegram bot adapter for SecondBrain.

Reads soul.md + user.md + agent.md + today's log before every reply,
queries a local LLM (Gemma4 via Ollama), returns the response to Telegram,
and appends every exchange to today's daily log.

Also starts the HeartbeatService on launch.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import List

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from .config import BotConfig
from .heartbeat import HeartbeatService
from .llm_client import LocalLLMClient
from .memory_manager import MemoryManager
from .skills import DocumentSkill, FileSystemSkill
from .safe_fs import SafePathError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("secondbrain.bot")


class SecondBrainBot:
    def __init__(self, config: BotConfig):
        self.cfg = config
        self.mm = MemoryManager(config.workspace)
        self.llm = LocalLLMClient(
            base_url=config.ollama_base_url,
            model=config.ollama_model,
        )
        self.app = (
            Application.builder()
            .token(config.telegram_token)
            .post_init(self._on_app_post_init)
            .post_shutdown(self._on_app_post_shutdown)
            .build()
        )

        # Skills
        self.doc_skill = DocumentSkill(self.mm, self.llm)
        self.fs_skill = FileSystemSkill(self.mm.workspace, memory_manager=self.mm)

        # Register handlers
        self.app.add_handler(CommandHandler("start", self._on_start))
        self.app.add_handler(CommandHandler("doc", self._on_doc_command))
        self.app.add_handler(CommandHandler("read", self._on_read_command))
        self.app.add_handler(CommandHandler("write", self._on_write_command))
        self.app.add_handler(CommandHandler("append", self._on_append_command))
        self.app.add_handler(CommandHandler("ls", self._on_ls_command))
        self.app.add_handler(CommandHandler("copy", self._on_copy_command))
        self.app.add_handler(CommandHandler("move", self._on_move_command))
        self.app.add_handler(CommandHandler("search", self._on_search_command))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_message))

        # Heartbeat service — auto-starts when the bot starts
        self.heartbeat = HeartbeatService(
            config=config,
            memory_manager=self.mm,
            llm_client=self.llm,
            telegram_app=self.app,
        )

    async def _on_app_post_init(self, app: Application) -> None:
        self.heartbeat.start()

    async def _on_app_post_shutdown(self, app: Application) -> None:
        await self.heartbeat.stop()

    # ------------------------------------------------------------------ #
    #  Handlers
    # ------------------------------------------------------------------ #
    async def _on_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if user is None:
            return
        if user.id != self.cfg.allowed_user_id:
            await update.message.reply_text("Access denied.")
            return
        await update.message.reply_text(
            f"Hello {user.first_name}! SecondBrain is online.\n"
            f"Model: {self.cfg.ollama_model}\n"
            f"Workspace: {self.mm.workspace}"
        )

    async def _on_doc_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /doc <topic> command."""
        user = update.effective_user
        if user is None or update.message is None:
            return
        if user.id != self.cfg.allowed_user_id:
            await update.message.reply_text("Access denied.")
            return

        topic = " ".join(context.args or []).strip()
        if not topic:
            await update.message.reply_text(
                "Usage: /doc <topic>\nExample: /doc How to build habits"
            )
            return

        await update.message.reply_text(f"📝 Creating document: *{topic}*...", parse_mode="Markdown")

        try:
            filepath, preview = await self.doc_skill.create(topic, user_request=f"/doc {topic}")
            rel_path = filepath.relative_to(self.mm.workspace).as_posix()
            reply = (
                f"✅ Document created!\n\n"
                f"📁 Path: `{rel_path}`\n\n"
                f"--- Preview ---\n{preview}\n"
            )
            await update.message.reply_text(reply, parse_mode="Markdown")
            self.mm.append_daily_log("Document Created", f"Created `{rel_path}` via /doc command.")
        except Exception as exc:
            logger.exception("Document creation failed")
            await update.message.reply_text(f"❌ Failed to create document: {exc}")

    async def _on_read_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if user is None or update.message is None:
            return
        if user.id != self.cfg.allowed_user_id:
            await update.message.reply_text("Access denied.")
            return

        if not context.args:
            await update.message.reply_text("Usage: /read <path> [from_line] [lines]")
            return

        rel_path = context.args[0]
        from_line = int(context.args[1]) if len(context.args) > 1 and context.args[1].isdigit() else None
        line_count = int(context.args[2]) if len(context.args) > 2 and context.args[2].isdigit() else None

        try:
            text = self.fs_skill.read(rel_path, from_line=from_line, lines=line_count)
        except SafePathError as exc:
            await update.message.reply_text(f"❌ {exc}")
            return
        except FileNotFoundError:
            await update.message.reply_text("❌ File not found.")
            return
        except IsADirectoryError:
            await update.message.reply_text("❌ That path points to a directory, not a file.")
            return

        await update.message.reply_text(text or "(empty file)")

    async def _on_write_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if user is None or update.message is None:
            return
        if user.id != self.cfg.allowed_user_id:
            await update.message.reply_text("Access denied.")
            return

        if len(context.args) < 2:
            await update.message.reply_text("Usage: /write <path> <content>")
            return

        rel_path = context.args[0]
        content = " ".join(context.args[1:])
        try:
            path = self.fs_skill.write(rel_path, content)
        except SafePathError as exc:
            await update.message.reply_text(f"❌ {exc}")
            return

        rel = path.relative_to(self.mm.workspace).as_posix()
        await update.message.reply_text(f"✅ Wrote `{rel}`", parse_mode="Markdown")
        self.mm.append_daily_log("File Written", f"Wrote `{rel}` via /write command.")

    async def _on_append_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if user is None or update.message is None:
            return
        if user.id != self.cfg.allowed_user_id:
            await update.message.reply_text("Access denied.")
            return

        if len(context.args) < 2:
            await update.message.reply_text("Usage: /append <path> <content>")
            return

        rel_path = context.args[0]
        content = " ".join(context.args[1:])
        try:
            path = self.fs_skill.append(rel_path, content)
        except SafePathError as exc:
            await update.message.reply_text(f"❌ {exc}")
            return

        rel = path.relative_to(self.mm.workspace).as_posix()
        await update.message.reply_text(f"✅ Appended to `{rel}`", parse_mode="Markdown")
        self.mm.append_daily_log("File Appended", f"Appended to `{rel}` via /append command.")

    async def _on_ls_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if user is None or update.message is None:
            return
        if user.id != self.cfg.allowed_user_id:
            await update.message.reply_text("Access denied.")
            return

        target = context.args[0] if context.args else "."
        try:
            files = self.fs_skill.list(target)
        except SafePathError as exc:
            await update.message.reply_text(f"❌ {exc}")
            return

        if not files:
            await update.message.reply_text("(no matching files)")
            return

        await update.message.reply_text("\n".join(files[:50]))

    async def _on_copy_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if user is None or update.message is None:
            return
        if user.id != self.cfg.allowed_user_id:
            await update.message.reply_text("Access denied.")
            return

        if len(context.args) < 2:
            await update.message.reply_text("Usage: /copy <source> <target>")
            return

        try:
            path = self.fs_skill.copy(context.args[0], context.args[1])
        except SafePathError as exc:
            await update.message.reply_text(f"❌ {exc}")
            return
        except FileNotFoundError:
            await update.message.reply_text("❌ Source file not found.")
            return
        except IsADirectoryError:
            await update.message.reply_text("❌ Source path points to a directory, not a file.")
            return

        rel = path.relative_to(self.mm.workspace).as_posix()
        await update.message.reply_text(f"✅ Copied to `{rel}`", parse_mode="Markdown")
        self.mm.append_daily_log("File Copied", f"Copied `{context.args[0]}` to `{rel}` via /copy command.")

    async def _on_move_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if user is None or update.message is None:
            return
        if user.id != self.cfg.allowed_user_id:
            await update.message.reply_text("Access denied.")
            return

        if len(context.args) < 2:
            await update.message.reply_text("Usage: /move <source> <target>")
            return

        try:
            path = self.fs_skill.move(context.args[0], context.args[1])
        except SafePathError as exc:
            await update.message.reply_text(f"❌ {exc}")
            return
        except FileNotFoundError:
            await update.message.reply_text("❌ Source file not found.")
            return
        except IsADirectoryError:
            await update.message.reply_text("❌ Source path points to a directory, not a file.")
            return

        rel = path.relative_to(self.mm.workspace).as_posix()
        await update.message.reply_text(f"✅ Moved to `{rel}`", parse_mode="Markdown")
        self.mm.append_daily_log("File Moved", f"Moved `{context.args[0]}` to `{rel}` via /move command.")

    async def _on_search_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if user is None or update.message is None:
            return
        if user.id != self.cfg.allowed_user_id:
            await update.message.reply_text("Access denied.")
            return

        query = " ".join(context.args or []).strip()
        if not query:
            await update.message.reply_text("Usage: /search <query>")
            return

        results = self.mm.search(query, max_results=5)
        if not results:
            await update.message.reply_text("No memory results found.")
            return

        reply = "\n\n".join(
            f"{item.path}:{item.start_line}-{item.end_line}\n{item.snippet}"
            for item in results
        )
        await update.message.reply_text(reply)

    async def _on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if user is None or update.message is None:
            return

        # Enforce single-user access
        if user.id != self.cfg.allowed_user_id:
            logger.warning("Ignored message from unauthorized user %s (id=%s)", user.username, user.id)
            return

        user_text = update.message.text or ""
        logger.info("Message from %s: %s", user.username, user_text[:80])

        # --- Skill routing ---
        doc_topic = self.doc_skill.detect(user_text)
        if doc_topic:
            await update.message.reply_text(f"📝 Creating document: *{doc_topic}*...", parse_mode="Markdown")
            try:
                filepath, preview = await self.doc_skill.create(doc_topic, user_request=user_text)
                rel_path = filepath.relative_to(self.mm.workspace).as_posix()
                reply = (
                    f"✅ Document created!\n\n"
                    f"📁 Path: `{rel_path}`\n\n"
                    f"--- Preview ---\n{preview}\n"
                )
                await update.message.reply_text(reply, parse_mode="Markdown")
                self.mm.append_daily_log("Document Created", f"Created `{rel_path}` via natural language trigger.")
            except Exception as exc:
                logger.exception("Document creation failed")
                await update.message.reply_text(f"❌ Failed to create document: {exc}")
            return

        # Build context from memory files
        context_blocks = self._build_context()
        system_prompt = self._build_system_prompt(context_blocks)

        messages: List[dict] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ]

        try:
            assistant_text = await self.llm.chat(messages)
        except Exception as exc:
            logger.exception("LLM call failed")
            await update.message.reply_text(f"LLM error: {exc}")
            return

        # Send reply to Telegram
        await update.message.reply_text(assistant_text)

        # Append exchange to today's log
        self._append_exchange(user_text, assistant_text)

    # ------------------------------------------------------------------ #
    #  Context building
    # ------------------------------------------------------------------ #
    def _build_context(self) -> dict:
        """Load soul.md, user.md, agent.md, and today's daily log."""
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
    def _build_system_prompt(ctx: dict) -> str:
        parts = [
            "You are the SecondBrain assistant. You have access to the user's persistent memory files.",
            "",
            "=== SOUL (core identity & values) ===",
            ctx["soul"] or "(empty)",
            "",
            "=== USER PROFILE ===",
            ctx["user"] or "(empty)",
            "",
            "=== AGENT PROFILE (your self-model) ===",
            ctx["agent"] or "(empty)",
            "",
            "=== TODAY'S LOG ===",
            ctx["today"] or "(empty)",
            "",
            "Instructions:",
            "- Be concise unless the user asks for detail.",
            "- Respect the user's preferences from the profile.",
            "- Reference past context when relevant.",
            "- Help the user think, plan, and remember.",
            "- If the user asks to create a document or write a note, tell them to use /doc or phrases like 'create a doc about...'",
        ]
        return "\n".join(parts)

    # ------------------------------------------------------------------ #
    #  Logging
    # ------------------------------------------------------------------ #
    def _append_exchange(self, user_text: str, assistant_text: str) -> None:
        now = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
        body = (
            f"**User ({now}):**\n{user_text}\n\n"
            f"**Assistant ({now}):**\n{assistant_text}\n"
        )
        self.mm.append_daily_log("Telegram Exchange", body)
        logger.info("Appended exchange to today's log")

    # ------------------------------------------------------------------ #
    #  Lifecycle
    # ------------------------------------------------------------------ #
    def run(self) -> None:
        logger.info("Starting SecondBrain Telegram bot...")
        logger.info("Workspace: %s", self.mm.workspace)
        logger.info("LLM: %s @ %s", self.cfg.ollama_model, self.cfg.ollama_base_url)
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)

    async def run_async(self) -> None:
        """Entry point for async runners."""
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        self.heartbeat.start()
        logger.info("Bot is polling. Press Ctrl+C to stop.")
        try:
            while True:
                await asyncio.sleep(3600)
        finally:
            await self.heartbeat.stop()


def main() -> None:
    cfg = BotConfig.from_env()
    bot = SecondBrainBot(cfg)
    bot.run()


if __name__ == "__main__":
    main()
