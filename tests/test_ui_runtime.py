from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ui.config import UIConfig
from ui.runtime import ChatRuntime


class FakeLLM:
    base_url = "fake://local"
    model = "fake-model"

    def __init__(self, replies: list[str]):
        self.replies = replies
        self.calls: list[list[dict[str, str]]] = []

    async def chat(self, messages: list[dict[str, str]], temperature: float = 0.7) -> str:
        self.calls.append(messages)
        if not self.replies:
            return "fallback reply"
        return self.replies.pop(0)


class ChatRuntimeTests(unittest.TestCase):
    def _config(self, workspace: Path) -> UIConfig:
        return UIConfig(
            workspace=str(workspace),
            ollama_base_url="http://localhost:11434",
            ollama_model="gemma4:e2b",
        )

    def test_workspace_histories_are_isolated(self) -> None:
        with TemporaryDirectory() as first_tmp, TemporaryDirectory() as second_tmp:
            first = Path(first_tmp)
            second = Path(second_tmp)
            (first / "first.md").write_text("first workspace", encoding="utf-8")
            (second / "second.md").write_text("second workspace", encoding="utf-8")

            runtime = ChatRuntime(self._config(first))
            first_reply = runtime.handle_message("/read first.md")
            self.assertEqual(first_reply["reply"], "first workspace")
            self.assertEqual(len(runtime.history_snapshot()), 2)

            runtime.set_workspace(str(second))
            self.assertEqual(runtime.history_snapshot(), [])

            second_reply = runtime.handle_message("/read second.md")
            self.assertEqual(second_reply["reply"], "second workspace")
            self.assertEqual(len(runtime.history_snapshot()), 2)

            runtime.set_workspace(str(first))
            self.assertEqual(len(runtime.history_snapshot()), 2)

    def test_excluded_dependency_directories_are_blocked(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "keep.md").write_text("keep", encoding="utf-8")
            (root / "survey.xlsx").write_bytes(b"excel-ish")
            (root / "assets").mkdir()
            (root / "assets" / "logo.png").write_text("png-ish", encoding="utf-8")
            (root / "empty-folder").mkdir()
            (root / ".venv" / "lib").mkdir(parents=True)
            (root / ".venv" / "bad.md").write_text("bad", encoding="utf-8")

            runtime = ChatRuntime(self._config(root))
            state = runtime.state()
            self.assertEqual(state["recent_files"], ["assets/logo.png", "keep.md", "survey.xlsx"])
            self.assertEqual(state["workspace_files"], ["assets/logo.png", "keep.md", "survey.xlsx"])
            entries = {(item["path"], item["type"]) for item in state["workspace_entries"]}
            self.assertIn(("assets", "directory"), entries)
            self.assertIn(("assets/logo.png", "file"), entries)
            self.assertIn(("empty-folder", "directory"), entries)
            self.assertNotIn((".venv", "directory"), entries)

            blocked = runtime.handle_message("/read .venv/bad.md")
            self.assertIn("error", blocked)
            self.assertIn("excluded", blocked["error"])

    def test_agent_tool_loop_lists_files_from_natural_language(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "alpha.md").write_text("alpha", encoding="utf-8")
            (root / "beta.md").write_text("beta", encoding="utf-8")
            (root / "survey.xlsx").write_bytes(b"excel-ish")
            llm = FakeLLM(
                [
                    '{"tool":"list_files","path":"."}',
                    "I found alpha.md, beta.md, and survey.xlsx.",
                ]
            )

            runtime = ChatRuntime(self._config(root), llm=llm)
            result = runtime.handle_message("can you list files in this workspace?")

            self.assertEqual(result["kind"], "tool-chat")
            self.assertEqual(result["tools"][0]["tool"], "list_files")
            self.assertIn("alpha.md", result["reply"])
            self.assertIn("survey.xlsx", llm.calls[1][-1]["content"])
            self.assertEqual(len(llm.calls), 2)

    def test_agent_tool_loop_reads_files_from_natural_language(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "note.md").write_text("important content", encoding="utf-8")
            llm = FakeLLM(
                [
                    '{"tool":"read_file","path":"note.md","lines":20}',
                    "note.md says important content.",
                ]
            )

            runtime = ChatRuntime(self._config(root), llm=llm)
            result = runtime.handle_message("please read note.md")

            self.assertEqual(result["kind"], "tool-chat")
            self.assertEqual(result["tools"][0]["tool"], "read_file")
            self.assertIn("important content", llm.calls[1][-1]["content"])

    def test_agent_tool_loop_validates_drillhole_file_from_natural_language(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "collar.csv").write_text("site_id,end_depth\nD001,100\n", encoding="utf-8")
            (root / "lithology.csv").write_text(
                "project,site_id,depth_from,depth_to,rock_type,lithology,recovery_m,logger\n"
                "P,D001,0,120,BAD,QV,10,AD\n",
                encoding="utf-8",
            )
            llm = FakeLLM(
                [
                    '{"tool":"validate_drillhole","inputs":{"collar":"collar.csv","lithology":"lithology.csv"}}',
                ]
            )

            runtime = ChatRuntime(self._config(root), llm=llm)
            result = runtime.handle_message("validate lithology.csv ini")

            self.assertEqual(result["kind"], "tool-chat")
            self.assertEqual(result["tools"][0]["tool"], "validate_drillhole")
            self.assertIn("## Ringkasan", result["reply"])
            self.assertIn("| Nama File | SITE_ID/HOLE_ID | Tipe Error | Kolom | Nilai/Penyebab |", result["reply"])
            self.assertIn("lithology.csv", result["reply"])
            self.assertIn("D001", result["reply"])
            self.assertIn("DEPTH_TO", result["reply"])
            self.assertIn("Invalid Code", result["reply"])
            self.assertEqual(len(llm.calls), 0)

    def test_agent_tool_loop_infers_drillhole_roles_from_folder(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data"
            data.mkdir()
            (data / "GB_SITE.csv").write_text("site_id,end_depth\nD001,100\n", encoding="utf-8")
            (data / "GB_LITHOLOGY.csv").write_text(
                "project,site_id,depth_from,depth_to,rock_type,lithology,recovery_m,logger\n"
                "P,D001,0,120,BAD,QV,10,AD\n",
                encoding="utf-8",
            )
            llm = FakeLLM([])

            runtime = ChatRuntime(self._config(root), llm=llm)
            result = runtime.handle_message("validasi lithology di folder data")

            self.assertEqual(result["kind"], "tool-chat")
            self.assertEqual(result["tools"][0]["tool"], "validate_drillhole")
            self.assertEqual(
                result["tools"][0]["args"]["inputs"],
                {"lithology": "data/GB_LITHOLOGY.csv", "collar": "data/GB_SITE.csv"},
            )
            self.assertIn("data/GB_LITHOLOGY.csv", result["reply"])
            self.assertEqual(len(llm.calls), 0)

    def test_agent_tool_loop_uses_editable_drillhole_role_aliases(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data"
            guidance = root / "drillhole_validation"
            data.mkdir()
            guidance.mkdir()
            (guidance / "default.md").write_text(
                "# Drillhole Validation Role Inference\n\n"
                "## Intent Aliases\n\n"
                "- validasi = validate_drillhole\n\n"
                "## File Role Aliases\n\n"
                "- collar_custom = collar\n"
                "- geologi = lithology\n\n"
                "## Required Companion Files\n\n"
                "- lithology requires collar\n",
                encoding="utf-8",
            )
            (data / "collar_custom.csv").write_text("site_id,end_depth\nD001,100\n", encoding="utf-8")
            (data / "geologi.csv").write_text(
                "project,site_id,depth_from,depth_to,rock_type,lithology,recovery_m,logger\n"
                "P,D001,0,120,BAD,QV,10,AD\n",
                encoding="utf-8",
            )
            llm = FakeLLM([])

            runtime = ChatRuntime(self._config(root), llm=llm)
            result = runtime.handle_message("validasi geologi di folder data")

            self.assertEqual(result["kind"], "tool-chat")
            self.assertEqual(result["tools"][0]["tool"], "validate_drillhole")
            self.assertEqual(
                result["tools"][0]["args"]["inputs"],
                {"collar": "data/collar_custom.csv", "lithology": "data/geologi.csv"},
            )
            self.assertEqual(len(llm.calls), 0)

    def test_normal_chat_skips_tool_planning(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            llm = FakeLLM(["hello there"])

            runtime = ChatRuntime(self._config(root), llm=llm)
            result = runtime.handle_message("hello")

            self.assertEqual(result["kind"], "chat")
            self.assertEqual(result["reply"], "hello there")
            self.assertEqual(len(llm.calls), 1)


if __name__ == "__main__":
    unittest.main()
