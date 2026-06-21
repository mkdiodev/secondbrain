# SecondBrain

A pure-Python memory system inspired by OpenClaw.

**Storage:** Markdown files  
**Search:** SQLite + FTS5

---

## Quick Start

```bash
# Install core + web UI dependencies
pip install -r requirements.txt

# Initialize workspace (creates soul.md, user.md, agent.md, memory/, memory.db)
python -m secondbrain.cli init

# Log a thought
python -m secondbrain.cli log "Idea" "What if we built a brain out of markdown?"

# Search everything
python -m secondbrain.cli sync
python -m secondbrain.cli search "markdown"

# Read a file
python -m secondbrain.cli read soul.md
```

For editable installs, you can also use:

```bash
pip install -e .
pip install -e ".[bot]"  # optional Telegram support
```

---

## Files

| File / Folder | Purpose |
|---------------|---------|
| `soul.md` | Core identity, values, purpose |
| `user.md` | Human user profile |
| `agent.md` | Assistant self-model |
| `memory/` | Daily logs (`YYYY-MM-DD.md`) |
| `memory.db` | SQLite + FTS5 search index |
| `secondbrain/` | Pure-Python package |

---

## Telegram Bot

### 1. Install extras

```bash
pip install "python-telegram-bot[aiohttp]" aiohttp python-dotenv
```

### 2. Configure

Copy `.env.example` to `.env` and fill in:

```bash
# Get this from @BotFather on Telegram
TELEGRAM_BOT_TOKEN=your-bot-token-here

# Your numeric Telegram user ID (from @userinfobot)
TELEGRAM_ALLOWED_USER_ID=your-telegram-user-id

# Optional — local LLM settings
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gemma4:e2b
SECONDBRAIN_WORKSPACE=.
```

### 3. Run

```bash
python -m secondbrain.cli bot
```

The bot will:
- Read `soul.md + user.md + agent.md + today's log` before every reply
- Send your messages to the local LLM (Gemma4 via Ollama)
- Return the response to Telegram
- Append every exchange to today's daily log
- Handle `/doc`, `/read`, `/write`, `/append`, `/ls`, `/copy`, `/move`, and `/search`
- **Only respond to your user ID** — all others are silently ignored
- **Auto-start heartbeat** — runs every 30 minutes in the background

### Web UI

Run the chat UI locally with:

```bash
python -m secondbrain.cli ui
```

The web UI gives you a Codex-style chat surface with:

- text chat with a local LLM from Ollama or LM Studio
- voice dictation in browsers that support SpeechRecognition
- toggleable workspace file tree for files and folders
- workspace commands like `/doc`, `/read`, `/write`, `/append`, `/ls`, and `/search`
  plus safe file moves/copies via `/copy` and `/move`
- read-only SQL Server queries via `/sql` and natural language questions grounded to a cached schema
- switch the active workspace in the UI or with `/workspace <path>`
- read-only natural language tool use for file listing, file reading, and memory search

Natural language tool use is intentionally read-only. File changes still require explicit slash
commands such as `/write`, `/append`, `/copy`, or `/move`.

### SQL Server Query Skill

SQL Server access is configured through environment variables, not workspace files. Store only
non-secret profile metadata in `SECOND_BRAIN_SQL_PROFILES`; keep the actual connection string in
a separate env var referenced by the profile.

```bash
export SECOND_BRAIN_SQL_PROFILES='{
  "default": {
    "connection_env": "SECOND_BRAIN_SQL_DEFAULT_CONNECTION",
    "schemas": ["reporting"],
    "max_rows": 100,
    "timeout_seconds": 20
  }
}'

export SECOND_BRAIN_SQL_DEFAULT_CONNECTION='Server=tcp:localhost,1433;Database=YourDb;UID=secondbrain_app_user;PWD=your-password;Encrypt=yes;TrustServerCertificate=no'
```

Available commands:

- `/sql profiles`
- `/sql schema [profile] [--refresh]`
- `/sql explain [profile] <question>`
- `/sql ask [profile] <question>`
- `/sql run [profile] <SELECT ...>`

Recommended SQL Server role:

```sql
CREATE ROLE secondbrain_reader;
GRANT SELECT ON SCHEMA::reporting TO secondbrain_reader;
GRANT VIEW DEFINITION ON SCHEMA::reporting TO secondbrain_reader;
ALTER ROLE secondbrain_reader ADD MEMBER secondbrain_app_user;
```

For production, prefer granting SELECT on curated reporting views instead of broad roles like
`db_datareader`. The app also rejects non-SELECT SQL, unknown tables/columns, multiple statements,
and destructive keywords before execution.

### Tests

Run the current smoke test suite with:

```bash
python -m unittest discover -s tests
```

### Heartbeat

Whenever the bot is running, a background heartbeat fires every 30 minutes:

1. Reads `soul.md + user.md + agent.md + today's log`
2. Asks the local LLM: "Is there anything worth notifying the user about?"
3. If the LLM replies `HEARTBEAT_OK` (or empty) → nothing happens
4. If the LLM finds something actionable → sends a Telegram notification
5. **24-hour deduplication** prevents re-notifying about the same content
6. Everything is logged to `heartbeat_debug.log`
7. Deduplication state is persisted in `heartbeat_debug.json`

---

## Architecture

```
secondbrain/
  __init__.py        # Package exports
  models.py          # MemoryChunk, MemoryEntry, MemorySearchResult
  memory_manager.py  # Core: SQLite schema, indexing, search, profiles, daily logs
  templates.py       # Default markdown for soul.md, user.md, agent.md
  config.py          # BotConfig from environment / .env
  llm_client.py      # Async Ollama-compatible HTTP client
  bot.py             # Telegram bot adapter + heartbeat auto-start
  heartbeat.py       # Periodic heartbeat (inspired by OpenClaw)
  safe_fs.py         # Workspace-bounded filesystem helpers
  skills/
    __init__.py      # Skill exports
    doc_skill.py     # Document creation skill (/doc, "create a doc about...")
    filesystem_skill.py # Safe file read/write/list/copy/move skill
ui/
  config.py          # UIConfig from environment
  server.py          # Thin Flask web UI + chat API routes
  runtime.py         # Coordinates workspace, commands, history, and LLM chat
  commands.py        # Slash command router
  tool_loop.py       # Read-only natural language tool loop
  workspace.py       # Active workspace resources and state
  history.py         # Per-workspace in-memory chat history
  static/            # Chat interface assets
  templates/         # Main UI template
tests/
  test_safe_fs.py    # Workspace path guard and file operation checks
  test_filesystem_skill.py # File skill indexing and copy/move checks
  test_ui_runtime.py # Workspace switching and runtime command checks
```

---

## Document Creation Skill

Create real markdown documents in the `documents/` folder:

**Telegram triggers:**
- `/doc <topic>` — explicit command
- "create a doc about..."
- "write a note on..."
- "make a document about..."
- "new doc: ..."

The bot will:
1. Ask the local LLM to write a well-structured markdown document
2. Save it to `documents/<slug>.md` with YAML frontmatter
3. Reply with the file path and a content preview
4. Auto-index it so it appears in `sync` / `search`

## Workspace Filesystem Skill

The bot and CLI now expose safe workspace-bounded file operations:

- `/read <path> [from_line] [lines]`
- `/write <path> <content>`
- `/append <path> <content>`
- `/ls [path]`
- `/copy <source> <target>`
- `/move <source> <target>`
- `/search <query>`

These commands only resolve paths inside the configured workspace, so reads and writes cannot escape into parent directories.

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `init` | Initialize workspace |
| `sync` | Re-index all markdown into SQLite |
| `search QUERY` | FTS5 search |
| `read PATH` | Read a memory file |
| `write PATH CONTENT` | Write a workspace file |
| `append PATH CONTENT` | Append to a workspace file |
| `copy SOURCE TARGET` | Copy a workspace file |
| `move SOURCE TARGET` | Move a workspace file |
| `ls [PATH]` | List markdown files inside the workspace |
| `log TITLE BODY` | Append to today's log |
| `profiles` | Show soul.md, user.md, agent.md |
| `bot` | Run Telegram bot |
