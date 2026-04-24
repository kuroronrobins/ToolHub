from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("toolhub_bootstrap", ROOT / "main.py")
assert SPEC is not None and SPEC.loader is not None
bootstrap = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bootstrap
SPEC.loader.exec_module(bootstrap)


class BootstrapCheckTests(unittest.TestCase):
    def test_validate_project_structure_passes_current_project(self) -> None:
        self.assertEqual(bootstrap.validate_project_structure(ROOT), [])

    def test_validate_project_structure_reports_missing_directories(self) -> None:
        missing = bootstrap.validate_project_structure(ROOT / "does_not_exist")
        self.assertIn("launcher", missing)
        self.assertIn("launcher/package.json", missing)


if __name__ == "__main__":
    unittest.main()
