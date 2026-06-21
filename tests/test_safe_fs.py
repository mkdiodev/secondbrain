from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from secondbrain.safe_fs import (
    SafePathError,
    copy_file_within_workspace,
    list_files_within_workspace,
    move_file_within_workspace,
    read_text_within_workspace,
    resolve_within_workspace,
    write_text_within_workspace,
)


class SafeFsTests(unittest.TestCase):
    def test_resolve_blocks_parent_escape_and_absolute_escape(self) -> None:
        with TemporaryDirectory() as tmp, TemporaryDirectory() as outside_tmp:
            root = Path(tmp)
            outside = Path(outside_tmp) / "outside.md"
            outside.write_text("outside", encoding="utf-8")

            with self.assertRaises(SafePathError):
                resolve_within_workspace(root, "../outside.md")

            with self.assertRaises(SafePathError):
                resolve_within_workspace(root, outside)

    def test_dependency_directories_are_excluded(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "notes").mkdir()
            (root / "notes" / "keep.md").write_text("keep", encoding="utf-8")
            (root / "node_modules").mkdir()
            (root / "node_modules" / "skip.md").write_text("skip", encoding="utf-8")

            listed = [path.relative_to(root).as_posix() for path in list_files_within_workspace(root)]
            self.assertEqual(listed, ["notes/keep.md"])

            with self.assertRaises(SafePathError):
                read_text_within_workspace(root, "node_modules/skip.md")

    def test_copy_and_move_stay_inside_workspace(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            write_text_within_workspace(root, "source.md", "hello")

            copied = copy_file_within_workspace(root, "source.md", "nested/copy.md")
            self.assertEqual(copied.relative_to(root).as_posix(), "nested/copy.md")
            self.assertEqual(copied.read_text(encoding="utf-8"), "hello")

            moved = move_file_within_workspace(root, "nested/copy.md", "moved.md")
            self.assertEqual(moved.relative_to(root).as_posix(), "moved.md")
            self.assertFalse((root / "nested" / "copy.md").exists())
            self.assertEqual(moved.read_text(encoding="utf-8"), "hello")

            with self.assertRaises(SafePathError):
                copy_file_within_workspace(root, "source.md", "../escape.md")


if __name__ == "__main__":
    unittest.main()
