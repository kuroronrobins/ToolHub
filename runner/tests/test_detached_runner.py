from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from toolhub_runner.base_runner import BaseRunner
from toolhub_runner.manifest import Admin, AppManifest, Detail, Display, Run, Search


def make_manifest(app_dir: Path, mode: str = "gui") -> AppManifest:
    return AppManifest(
        id="detached_sample",
        name="Detached Sample",
        app_dir=app_dir,
        display=Display(icon="icon.svg", short_description="desc", categories=["cat"]),
        detail=Detail(description="desc"),
        search=Search(),
        run=Run(runner="python", entry="main.py", mode=mode),
        admin=Admin(),
    )


class DetachedRunnerTests(unittest.TestCase):
    def test_detached_immediate_exit_is_failure_with_stderr(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app_dir = root / "apps" / "detached_sample"
            app_dir.mkdir(parents=True)
            script = app_dir / "fail.py"
            script.write_text(
                "import sys\nprint('stdout marker')\nprint('stderr marker', file=sys.stderr)\nsys.exit(7)\n",
                encoding="utf-8",
            )
            runner = BaseRunner(root, make_manifest(app_dir))

            with patch.dict(os.environ, {"TOOLHUB_USER_DATA_ROOT": str(root)}), patch("toolhub_runner.base_runner.STARTUP_PROBE_SECONDS", 0.2):
                result = runner.start_detached([sys.executable, str(script)], os.environ.copy())

            self.assertFalse(result.ok)
            self.assertIn("起動直後", result.user_message)
            payload = json.loads(Path(result.log_path or "").read_text(encoding="utf-8"))
            self.assertEqual(payload["exit_code"], 7)
            self.assertIn("stdout marker", payload["stdout"])
            self.assertIn("stderr marker", payload["stderr"])
            self.assertIn("stdout_log_path", payload)
            self.assertIn("stderr_log_path", payload)

    def test_detached_process_alive_after_probe_is_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app_dir = root / "apps" / "detached_sample"
            app_dir.mkdir(parents=True)
            script = app_dir / "sleep.py"
            script.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
            runner = BaseRunner(root, make_manifest(app_dir))

            with patch.dict(os.environ, {"TOOLHUB_USER_DATA_ROOT": str(root)}), patch("toolhub_runner.base_runner.STARTUP_PROBE_SECONDS", 0.2):
                result = runner.start_detached([sys.executable, str(script)], os.environ.copy())

            self.assertTrue(result.ok)
            payload = json.loads(Path(result.log_path or "").read_text(encoding="utf-8"))
            self.assertIsNone(payload["exit_code"])
            self.assertTrue(payload["pid"])
            pid = int(payload["pid"])
            try:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                else:
                    os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
            time.sleep(0.2)


if __name__ == "__main__":
    unittest.main()
