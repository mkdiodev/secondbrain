from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ui.config import UIConfig
from ui.runtime import ChatRuntime


class DrillholeCommandTests(unittest.TestCase):
    def _runtime(self, workspace: Path) -> ChatRuntime:
        return ChatRuntime(
            UIConfig(
                workspace=str(workspace),
                ollama_base_url="http://localhost:11434",
                ollama_model="gemma4:e2b",
            )
        )

    def test_dh_config_init_reports_embedded_config_already_active(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = self._runtime(root)

            result = runtime.handle_message("/dh config init")
            self.assertEqual(result["kind"], "dh-validation")
            self.assertIn("No init needed", result["reply"])
            self.assertFalse((root / ".secondbrain" / "dh-validation" / "config.json").exists())

            shown = runtime.handle_message("/dh config show")
            self.assertEqual(shown["kind"], "dh-validation")
            self.assertIn("COLLAR", shown["reply"])
            self.assertIn("alt_group_bb2q", shown["reply"])

    def test_dh_validate_command_returns_summary_and_writes_report(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "collar.csv").write_text("site_id,end_depth\nDH001,100\n", encoding="utf-8")
            (root / "assay.csv").write_text(
                "site_id,depth_from,depth_to,au_ppm\nDH001,0,120,1200\n",
                encoding="utf-8",
            )
            runtime = self._runtime(root)

            result = runtime.handle_message(
                "/dh validate --collar collar.csv --assay assay.csv --out reports/dh-report.json"
            )

            self.assertEqual(result["kind"], "dh-validation")
            self.assertEqual(result["report_path"], "reports/dh-report.json")
            self.assertGreaterEqual(result["summary"]["totalErrors"], 1)
            self.assertIn("## Ringkasan", result["reply"])
            self.assertIn("| Nama File | SITE_ID/HOLE_ID | Tipe Error | Kolom | Nilai/Penyebab |", result["reply"])
            self.assertIn("assay.csv", result["reply"])
            self.assertIn("DH001", result["reply"])
            self.assertIn("DEPTH_TO", result["reply"])
            self.assertIn("Depth Exceeded", result["reply"])
            payload = json.loads((root / "reports" / "dh-report.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["totalErrors"], result["summary"]["totalErrors"])
            self.assertIn("assay.csv", {error["fileName"] for error in payload["errors"]})

    def test_dh_validate_rejects_output_path_outside_workspace(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "collar.csv").write_text("site_id,end_depth\nDH001,100\n", encoding="utf-8")
            runtime = self._runtime(root)

            result = runtime.handle_message(
                "/dh validate --collar collar.csv --out ../outside.json"
            )

            self.assertIn("error", result)
            self.assertIn("escapes workspace", result["error"])


if __name__ == "__main__":
    unittest.main()
