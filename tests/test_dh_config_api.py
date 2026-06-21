from __future__ import annotations

import json
import os
import unittest
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from secondbrain.skills.drillhole_validation_skill import default_config
from ui.server import create_app


class DrillholeConfigApiTests(unittest.TestCase):
    def _client(self, workspace: Path, app_config: Path | None = None):
        previous = {
            "SECONDBRAIN_WORKSPACE": os.environ.get("SECONDBRAIN_WORKSPACE"),
            "OLLAMA_BASE_URL": os.environ.get("OLLAMA_BASE_URL"),
            "OLLAMA_MODEL": os.environ.get("OLLAMA_MODEL"),
            "SECONDBRAIN_DH_CONFIG_PATH": os.environ.get("SECONDBRAIN_DH_CONFIG_PATH"),
        }
        os.environ["SECONDBRAIN_WORKSPACE"] = str(workspace)
        os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"
        os.environ["OLLAMA_MODEL"] = "gemma4:e2b"
        if app_config is not None:
            os.environ["SECONDBRAIN_DH_CONFIG_PATH"] = str(app_config)
        try:
            app, _runtime = create_app()
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        return app.test_client()

    def _app_config_copy(self, root: Path) -> Path:
        target = root / "embedded" / "userConfig.json"
        target.parent.mkdir(parents=True)
        shutil.copyfile(Path("secondbrain/defaults/userConfig.json"), target)
        return target

    def test_get_config_returns_embedded_app_user_config(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            app_config = self._app_config_copy(root)
            client = self._client(root / "workspace", app_config)

            response = client.get("/api/dh/config")
            payload = response.get_json()

            self.assertEqual(response.status_code, 200)
            self.assertTrue(payload["exists"])
            self.assertEqual(payload["scope"], "app")
            self.assertTrue(payload["path"].endswith("userConfig.json"))
            self.assertEqual(payload["config"]["version"], "1.0")
            self.assertEqual(len(payload["config"]["libraries"]), 54)

    def test_init_config_is_noop_because_embedded_config_is_always_active(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            app_config = self._app_config_copy(root)
            client = self._client(root / "workspace", app_config)

            response = client.post("/api/dh/config/init")
            payload = response.get_json()

            self.assertEqual(response.status_code, 200)
            self.assertTrue(payload["exists"])
            self.assertEqual(payload["scope"], "app")
            self.assertFalse((root / "workspace" / ".secondbrain" / "dh-validation" / "config.json").exists())

    def test_put_config_saves_valid_rules_and_libraries(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            app_config = self._app_config_copy(root)
            client = self._client(root / "workspace", app_config)
            config = default_config()
            config["libraries"].append(
                {
                    "id": "cu_class",
                    "name": "Cu Class",
                    "items": [{"code": "HIGH", "description": "High copper"}],
                }
            )
            assay = next(item for item in config["configs"] if item["tableType"] == "ASSAY")
            assay["columns"].append(
                {
                    "columnName": "CU_CLASS",
                    "label": "Cu Class",
                    "isSchemaRequired": False,
                    "isMandatory": False,
                    "type": "string",
                    "validation": {"lookup": {"libraryId": "cu_class", "caseSensitive": False}},
                }
            )

            response = client.put("/api/dh/config", json={"config": config})
            payload = response.get_json()

            self.assertEqual(response.status_code, 200)
            self.assertTrue(payload["exists"])
            saved = json.loads(app_config.read_text(encoding="utf-8"))
            self.assertEqual(saved["libraries"][-1]["id"], "cu_class")
            self.assertEqual(payload["config"]["configs"], saved["configs"])

    def test_put_config_rejects_invalid_table_and_lookup_library(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            client = self._client(root / "workspace", self._app_config_copy(root))
            config = default_config()
            config["configs"].append({"tableType": "BOGUS", "columns": []})

            response = client.put("/api/dh/config", json={"config": config})

            self.assertEqual(response.status_code, 400)
            self.assertIn("Unknown tableType", response.get_json()["error"])

            config = default_config()
            lithology = next(item for item in config["configs"] if item["tableType"] == "LITHOLOGY")
            lithology["columns"][0]["validation"] = {"lookup": {"libraryId": "missing", "caseSensitive": False}}
            response = client.put("/api/dh/config", json={"config": config})

            self.assertEqual(response.status_code, 400)
            self.assertIn("unknown library", response.get_json()["error"])

    def test_config_api_ignores_workspace_switch_and_workspace_config_files(self) -> None:
        with TemporaryDirectory() as first_tmp, TemporaryDirectory() as second_tmp:
            first = Path(first_tmp)
            second = Path(second_tmp)
            app_config = self._app_config_copy(first)
            workspace_config = default_config()
            workspace_config["version"] = "workspace-only"
            path = first / "workspace" / ".secondbrain" / "dh-validation"
            path.mkdir(parents=True)
            (path / "config.json").write_text(json.dumps(workspace_config), encoding="utf-8")

            client = self._client(first / "workspace", app_config)
            first_response = client.get("/api/dh/config").get_json()
            self.assertEqual(first_response["scope"], "app")
            self.assertEqual(first_response["config"]["version"], "1.0")

            switch = client.post("/api/workspace", json={"workspace": str(second)})
            self.assertEqual(switch.status_code, 200)
            second_response = client.get("/api/dh/config").get_json()

            self.assertTrue(second_response["exists"])
            self.assertEqual(second_response["scope"], "app")
            self.assertEqual(second_response["config"]["version"], "1.0")


if __name__ == "__main__":
    unittest.main()
