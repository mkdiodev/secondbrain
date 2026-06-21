"""Document creation skill — creates .md files in the documents/ folder."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

from ..llm_client import LocalLLMClient
from ..memory_manager import MemoryManager
from ..safe_fs import write_text_within_workspace


class DocumentSkill:
    """
    Detects document creation intent and generates + saves markdown files.

    Triggers:
      • /doc <topic>
      • "create a doc about <topic>"
      • "write a note on <topic>"
      • "make a document about <topic>"
      • "new doc: <topic>"
    """

    TRIGGERS = [
        re.compile(r"^/doc\s+(.+)", re.IGNORECASE),
        re.compile(r"create\s+a?\s*doc(?:ument)?\s+(?:about|on)\s+(.+)", re.IGNORECASE),
        re.compile(r"write\s+a?\s*note\s+(?:about|on)\s+(.+)", re.IGNORECASE),
        re.compile(r"make\s+a?\s*document\s+(?:about|on)\s+(.+)", re.IGNORECASE),
        re.compile(r"new\s+doc(?:ument)?[:\-]?\s+(.+)", re.IGNORECASE),
    ]

    def __init__(self, memory_manager: MemoryManager, llm_client: LocalLLMClient):
        self.mm = memory_manager
        self.llm = llm_client
        self.docs_dir = self.mm.workspace / "documents"
        self.docs_dir.mkdir(exist_ok=True)

    def detect(self, text: str) -> Optional[str]:
        """If the text is a doc-creation request, return the topic; else None."""
        for pattern in self.TRIGGERS:
            match = pattern.search(text)
            if match:
                return match.group(1).strip()
        return None

    async def create(self, topic: str, user_request: str) -> Tuple[Path, str]:
        """
        Ask the LLM to write a document, save it, and return (path, preview).
        """
        # Build a prompt that leverages memory context
        context = self._build_context()
        prompt = self._build_doc_prompt(topic, context, user_request)

        messages = [
            {"role": "system", "content": "You are a helpful writing assistant."},
            {"role": "user", "content": prompt},
        ]
        content = await self.llm.chat(messages, temperature=0.7)

        # Clean up any markdown code fences the LLM might wrap the doc in
        content = self._unwrap_code_fences(content)

        # Generate filename
        filename = self._slugify(topic) + ".md"
        filepath = self.docs_dir / filename

        # Add frontmatter
        final_content = self._add_frontmatter(topic, content)

        # Write file
        write_text_within_workspace(self.mm.workspace, filepath, final_content)

        # Re-index so it's searchable
        self.mm.index_file(filepath)

        return filepath, content[:600]

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #
    def _build_context(self) -> dict:
        return {
            "soul": self.mm.read_profile("soul"),
            "user": self.mm.read_profile("user"),
            "today": self._read_today_log(),
        }

    def _read_today_log(self) -> str:
        path = self.mm.daily_log_path()
        if path.exists():
            return path.read_text(encoding="utf-8")
        return "(No entries yet today)"

    @staticmethod
    def _build_doc_prompt(topic: str, ctx: dict, user_request: str) -> str:
        parts = [
            "Write a markdown document about the topic below.",
            "",
            f"Topic: {topic}",
            f"Original request: {user_request}",
            "",
            "=== SOUL (system identity) ===",
            ctx["soul"] or "(empty)",
            "",
            "=== USER PROFILE ===",
            ctx["user"] or "(empty)",
            "",
            "=== TODAY'S LOG ===",
            ctx["today"] or "(empty)",
            "",
            "Instructions:",
            "- Write a well-structured markdown document.",
            "- Use headings, bullet points, and paragraphs as appropriate.",
            "- Keep it concise but thorough (aim for 300–800 words).",
            "- Do NOT wrap the output in ```markdown fences.",
            "- Start directly with the document content (e.g. a # Heading).",
        ]
        return "\n".join(parts)

    @staticmethod
    def _unwrap_code_fences(text: str) -> str:
        """Remove ```markdown ... ``` wrappers if present."""
        stripped = text.strip()
        if stripped.startswith("```markdown"):
            stripped = stripped[len("```markdown"):].strip()
        elif stripped.startswith("```"):
            stripped = stripped[len("```"):].strip()
        if stripped.endswith("```"):
            stripped = stripped[:-3].strip()
        return stripped

    @staticmethod
    def _slugify(text: str) -> str:
        """Convert 'Hello World!' → 'hello-world'."""
        slug = re.sub(r"[^\w\s-]", "", text.lower())
        slug = re.sub(r"[-\s]+", "-", slug).strip("-")
        return slug or "untitled"

    @staticmethod
    def _add_frontmatter(topic: str, body: str) -> str:
        now = datetime.now(timezone.utc).isoformat()
        return (
            f"---\n"
            f"title: {topic}\n"
            f"created: {now}\n"
            f"source: secondbrain-doc-skill\n"
            f"---\n\n"
            f"{body}\n"
        )
