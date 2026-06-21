from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from secondbrain.safe_fs import SafePathError
from secondbrain.skills import DrillholeValidationSkill
from secondbrain.skills.drillhole_validation_skill import default_config


class DrillholeValidationSkillTests(unittest.TestCase):
    def test_default_config_uses_uploaded_user_config(self) -> None:
        config = default_config()
        table_counts = {item["tableType"]: len(item.get("columns", [])) for item in config["configs"]}

        self.assertEqual(len(config["libraries"]), 54)
        self.assertEqual(len(config["configs"]), 11)
        self.assertEqual(table_counts["COLLAR"], 15)
        self.assertEqual(table_counts["ALTERATION"], 34)
        self.assertTrue(any(library["name"] == "ALT_GROUP" for library in config["libraries"]))

    def test_validates_core_drillhole_rules_from_workspace_csv_files(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "collar.csv").write_text(
                "Hole ID,End Depth\n"
                "DH001,100\n"
                "DH002,0\n",
                encoding="utf-8",
            )
            (root / "lithology.csv").write_text(
                "project,site_id,from,to,rock_type,lithology,recovery_m,logger\n"
                "P,DH001,0,40,QZV,QV,40,AD\n"
                "P,DH001,35,60,BAD,QV,25,AD\n"
                "P,DH001,80,80,QZV,QV,0,AD\n"
                "P,MISSING,0,10,QZV,QV,10,AD\n",
                encoding="utf-8",
            )

            skill = DrillholeValidationSkill(root)
            skill.init_config()
            summary = skill.validate(
                {
                    "collar": "collar.csv",
                    "lithology": "lithology.csv",
                }
            )

            messages = [error.message for error in summary.errors]
            self.assertGreaterEqual(summary.total_errors, 1)
            self.assertTrue(any("END_DEPTH" in message for message in messages))
            self.assertTrue(any("Orphan Record" in message for message in messages))
            self.assertTrue(any("Overlap" in message for message in messages))
            self.assertTrue(any("Zero Length" in message for message in messages))
            self.assertTrue(any("Invalid Code" in message for message in messages))

    def test_reads_xlsx_and_applies_numeric_range_rules(self) -> None:
        from openpyxl import Workbook

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            wb = Workbook()
            ws = wb.active
            ws.append(["site_id", "depth", "direction", "inclination"])
            ws.append(["DH001", 10, 400, -95])
            wb.save(root / "survey.xlsx")

            (root / "collar.csv").write_text("site_id,end_depth\nDH001,100\n", encoding="utf-8")

            skill = DrillholeValidationSkill(root)
            skill.init_config()
            summary = skill.validate({"collar": "collar.csv", "survey": "survey.xlsx"})

            messages = [error.message for error in summary.errors]
            self.assertTrue(any("above maximum 360" in message for message in messages))
            self.assertTrue(any("below minimum -90" in message for message in messages))

    def test_writes_json_and_markdown_reports_inside_workspace(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "collar.csv").write_text("site_id,end_depth\nDH001,100\n", encoding="utf-8")
            (root / "lithology.csv").write_text(
                "site_id,depth_from,depth_to\nDH001,0,120\n",
                encoding="utf-8",
            )

            skill = DrillholeValidationSkill(root)
            skill.init_config()
            json_summary = skill.validate(
                {"collar": "collar.csv", "lithology": "lithology.csv"},
                out_path="reports/validation.json",
            )
            markdown_summary = skill.validate(
                {"collar": "collar.csv", "lithology": "lithology.csv"},
                out_path="reports/validation.md",
            )

            payload = json.loads((root / "reports" / "validation.json").read_text(encoding="utf-8"))
            markdown = (root / "reports" / "validation.md").read_text(encoding="utf-8")
            self.assertEqual(payload["totalErrors"], json_summary.total_errors)
            self.assertEqual(markdown_summary.report_path, "reports/validation.md")
            self.assertIn("# Drillhole Validation Report", markdown)
            self.assertIn("Depth Exceeded", markdown)

    def test_blocks_paths_outside_workspace(self) -> None:
        with TemporaryDirectory() as tmp, TemporaryDirectory() as outside_tmp:
            root = Path(tmp)
            outside = Path(outside_tmp) / "collar.csv"
            outside.write_text("site_id,end_depth\nDH001,100\n", encoding="utf-8")

            skill = DrillholeValidationSkill(root)
            with self.assertRaises(SafePathError):
                skill.validate({"collar": str(outside)})


if __name__ == "__main__":
    unittest.main()
