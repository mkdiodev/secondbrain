from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ui.server import create_app


class DrillholeConfigUiTests(unittest.TestCase):
    def test_index_contains_dh_config_editor_shell(self) -> None:
        with TemporaryDirectory() as tmp:
            previous = os.environ.get("SECONDBRAIN_WORKSPACE")
            os.environ["SECONDBRAIN_WORKSPACE"] = str(Path(tmp))
            try:
                app, _runtime = create_app()
            finally:
                if previous is None:
                    os.environ.pop("SECONDBRAIN_WORKSPACE", None)
                else:
                    os.environ["SECONDBRAIN_WORKSPACE"] = previous

            response = app.test_client().get("/")
            html = response.get_data(as_text=True)

            self.assertEqual(response.status_code, 200)
            self.assertIn('id="chat-tab"', html)
            self.assertIn('id="dh-config-tab"', html)
            self.assertIn('id="dh-config-panel"', html)
            self.assertIn('id="help-tab"', html)
            self.assertIn('id="help-panel"', html)
            self.assertIn("Slash commands", html)
            self.assertIn("SQL Server", html)
            self.assertIn("SECONDBRAIN_LLM_PROVIDER", html)
            self.assertIn("LM_STUDIO_BASE_URL", html)
            self.assertIn("CREATE LOGIN", html)
            self.assertIn("SECOND_BRAIN_SQL_PROFILES", html)
            self.assertIn("/sql schema default --refresh", html)
            self.assertIn("Natural language", html)
            self.assertNotIn('id="dh-config-init"', html)
            self.assertIn('id="dh-config-reload"', html)
            self.assertIn('id="dh-config-save"', html)


if __name__ == "__main__":
    unittest.main()
