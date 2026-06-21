#!/usr/bin/env python3
"""CLI for SecondBrain memory system."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .memory_manager import MemoryManager
from .safe_fs import SafePathError
from .templates import AGENT_TEMPLATE, SOUL_TEMPLATE, USER_TEMPLATE
from .skills import FileSystemSkill


def cmd_init(args: argparse.Namespace) -> int:
    """Initialize a new SecondBrain workspace."""
    workspace = Path(args.workspace).resolve()
    mm = MemoryManager(workspace)

    # Ensure profile files exist with templates
    mm.ensure_profile("soul", SOUL_TEMPLATE)
    mm.ensure_profile("user", USER_TEMPLATE)
    mm.ensure_profile("agent", AGENT_TEMPLATE)

    print(f"SecondBrain initialized at: {workspace}")
    print(f"  Profiles:  soul.md, user.md, agent.md")
    print(f"  Daily log: memory/")
    print(f"  Database:  memory.db")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    """Re-index all markdown files into SQLite + FTS5."""
    mm = MemoryManager(args.workspace)
    mm.sync()
    print("Sync complete.")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    """Search the memory index."""
    mm = MemoryManager(args.workspace)
    results = mm.search(
        args.query,
        max_results=args.limit,
        source=args.source,
    )
    if not results:
        print("No results found.")
        return 0
    for r in results:
        print(f"---\n[{r.source}] {r.path}:{r.start_line}-{r.end_line}  (score={r.score:.4f})")
        print(r.snippet)
    return 0


def cmd_read(args: argparse.Namespace) -> int:
    """Read a memory file by relative path."""
    mm = MemoryManager(args.workspace)
    try:
        text = mm.read_file(args.path, from_line=args.from_line, lines=args.lines)
    except SafePathError as exc:
        print(f"Error: {exc}")
        return 1
    print(text)
    return 0


def cmd_write(args: argparse.Namespace) -> int:
    """Write a file within the workspace."""
    mm = MemoryManager(args.workspace)
    fs = FileSystemSkill(args.workspace, memory_manager=mm)
    try:
        path = fs.write(args.path, args.content)
    except SafePathError as exc:
        print(f"Error: {exc}")
        return 1
    print(f"Wrote {path}")
    return 0


def cmd_append(args: argparse.Namespace) -> int:
    """Append to a file within the workspace."""
    mm = MemoryManager(args.workspace)
    fs = FileSystemSkill(args.workspace, memory_manager=mm)
    try:
        path = fs.append(args.path, args.content)
    except SafePathError as exc:
        print(f"Error: {exc}")
        return 1
    print(f"Appended {path}")
    return 0


def cmd_ls(args: argparse.Namespace) -> int:
    """List markdown files within the workspace."""
    fs = FileSystemSkill(args.workspace)
    try:
        files = fs.list(args.path)
    except SafePathError as exc:
        print(f"Error: {exc}")
        return 1
    for item in files:
        print(item)
    return 0


def cmd_copy(args: argparse.Namespace) -> int:
    """Copy a file within the workspace."""
    mm = MemoryManager(args.workspace)
    fs = FileSystemSkill(args.workspace, memory_manager=mm)
    try:
        path = fs.copy(args.source, args.target)
    except (SafePathError, FileNotFoundError, IsADirectoryError) as exc:
        print(f"Error: {exc}")
        return 1
    print(f"Copied to {path}")
    return 0


def cmd_move(args: argparse.Namespace) -> int:
    """Move a file within the workspace."""
    mm = MemoryManager(args.workspace)
    fs = FileSystemSkill(args.workspace, memory_manager=mm)
    try:
        path = fs.move(args.source, args.target)
    except (SafePathError, FileNotFoundError, IsADirectoryError) as exc:
        print(f"Error: {exc}")
        return 1
    print(f"Moved to {path}")
    return 0


def cmd_log(args: argparse.Namespace) -> int:
    """Append an entry to today's daily log."""
    mm = MemoryManager(args.workspace)
    tags = [t.strip() for t in args.tags.split(",")] if args.tags else None
    path = mm.append_daily_log(args.title, args.body, tags=tags)
    print(f"Logged to {path.relative_to(mm.workspace)}")
    return 0


def cmd_profiles(args: argparse.Namespace) -> int:
    """Print current profile contents."""
    mm = MemoryManager(args.workspace)
    for name in ("soul", "user", "agent"):
        print(f"\n========== {name.upper()}.md ==========\n")
        print(mm.read_profile(name) or "(empty)")
    return 0


def cmd_ui(args: argparse.Namespace) -> int:
    """Run the web chat UI."""
    from ui.server import run_server

    run_server(host=args.host, port=args.port, debug=args.debug)
    return 0


def cmd_bot(args: argparse.Namespace) -> int:
    """Run the Telegram bot."""
    try:
        from .bot import SecondBrainBot
        from .config import BotConfig
    except ImportError as exc:
        print(f"Missing dependency: {exc}")
        print("Install bot extras:  pip install 'python-telegram-bot[aiohttp]' aiohttp")
        return 1
    cfg = BotConfig.from_env()
    bot = SecondBrainBot(cfg)
    bot.run()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="secondbrain",
        description="SecondBrain — markdown + SQLite memory system",
    )
    parser.add_argument(
        "--workspace", "-w",
        default=".",
        help="Workspace directory (default: current dir)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # init
    p_init = sub.add_parser("init", help="Initialize a new workspace")
    p_init.set_defaults(func=cmd_init)

    # sync
    p_sync = sub.add_parser("sync", help="Re-index all markdown files")
    p_sync.set_defaults(func=cmd_sync)

    # search
    p_search = sub.add_parser("search", help="Search memory index")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--limit", "-n", type=int, default=10)
    p_search.add_argument("--source", "-s", default=None, help="Filter by source (soul, user, agent, daily)")
    p_search.set_defaults(func=cmd_search)

    # read
    p_read = sub.add_parser("read", help="Read a memory file")
    p_read.add_argument("path", help="Relative path, e.g. soul.md or memory/2025-04-25.md")
    p_read.add_argument("--from-line", type=int, default=None)
    p_read.add_argument("--lines", type=int, default=None)
    p_read.set_defaults(func=cmd_read)

    # write
    p_write = sub.add_parser("write", help="Write a file within the workspace")
    p_write.add_argument("path", help="Relative path, e.g. notes/today.md")
    p_write.add_argument("content", help="File content")
    p_write.set_defaults(func=cmd_write)

    # append
    p_append = sub.add_parser("append", help="Append to a file within the workspace")
    p_append.add_argument("path", help="Relative path, e.g. notes/today.md")
    p_append.add_argument("content", help="Content to append")
    p_append.set_defaults(func=cmd_append)

    # copy
    p_copy = sub.add_parser("copy", help="Copy a file within the workspace")
    p_copy.add_argument("source", help="Source path")
    p_copy.add_argument("target", help="Destination path")
    p_copy.set_defaults(func=cmd_copy)

    # move
    p_move = sub.add_parser("move", help="Move a file within the workspace")
    p_move.add_argument("source", help="Source path")
    p_move.add_argument("target", help="Destination path")
    p_move.set_defaults(func=cmd_move)

    # ls
    p_ls = sub.add_parser("ls", help="List markdown files within the workspace")
    p_ls.add_argument("path", nargs="?", default=".", help="Workspace-relative directory")
    p_ls.set_defaults(func=cmd_ls)

    # log
    p_log = sub.add_parser("log", help="Append to today's daily log")
    p_log.add_argument("title", help="Entry title")
    p_log.add_argument("body", help="Entry body (markdown supported)")
    p_log.add_argument("--tags", "-t", default=None, help="Comma-separated tags")
    p_log.set_defaults(func=cmd_log)

    # profiles
    p_prof = sub.add_parser("profiles", help="Show soul.md, user.md, agent.md")
    p_prof.set_defaults(func=cmd_profiles)

    # bot
    p_bot = sub.add_parser("bot", help="Run the Telegram bot")
    p_bot.set_defaults(func=cmd_bot)

    # ui
    p_ui = sub.add_parser("ui", help="Run the web chat UI")
    p_ui.add_argument("--host", default=None, help="Bind host (default: 127.0.0.1)")
    p_ui.add_argument("--port", type=int, default=None, help="Port (default: 3000)")
    p_ui.add_argument("--debug", action="store_true", help="Enable Flask debug mode")
    p_ui.set_defaults(func=cmd_ui)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
