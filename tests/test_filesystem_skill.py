from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from secondbrain.memory_manager import MemoryManager
from secondbrain.skills import FileSystemSkill


class FileSystemSkillTests(unittest.TestCase):
    def test_tree_lists_files_and_directories(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / "docs" / "note.txt").write_text("note", encoding="utf-8")
            (root / "image.png").write_text("image", encoding="utf-8")
            (root / "empty").mkdir()

            fs = FileSystemSkill(root)
            entries = {(item["path"], item["type"]) for item in fs.tree(".")}

            self.assertIn(("docs", "directory"), entries)
            self.assertIn(("docs/note.txt", "file"), entries)
            self.assertIn(("image.png", "file"), entries)
            self.assertIn(("empty", "directory"), entries)

    def test_list_includes_excel_files_by_default(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "collar.xlsx").write_bytes(b"excel-ish")
            (root / "notes.md").write_text("note", encoding="utf-8")

            fs = FileSystemSkill(root)

            self.assertEqual(fs.list("."), ["collar.xlsx", "notes.md"])

    def test_write_append_copy_move_update_search_index(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            mm = MemoryManager(root)
            fs = FileSystemSkill(root, memory_manager=mm)

            fs.write("notes/source.md", "alpha")
            fs.append("notes/source.md", "\nbeta")
            self.assertIn("notes/source.md", fs.list("."))
            self.assertEqual(fs.read("notes/source.md"), "alpha\nbeta")
            self.assertEqual(mm.search("beta")[0].path, "notes/source.md")

            fs.copy("notes/source.md", "notes/copied.md")
            copied_results = {item.path for item in mm.search("beta", max_results=5)}
            self.assertIn("notes/source.md", copied_results)
            self.assertIn("notes/copied.md", copied_results)

            fs.move("notes/copied.md", "notes/moved.md")
            moved_results = {item.path for item in mm.search("beta", max_results=5)}
            self.assertIn("notes/source.md", moved_results)
            self.assertIn("notes/moved.md", moved_results)
            self.assertNotIn("notes/copied.md", moved_results)


if __name__ == "__main__":
    unittest.main()
