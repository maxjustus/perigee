"""Protect an existing analysis project from the headless launcher."""

from pathlib import Path
import os
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).with_name("psoc.sh")


class ProjectProtectionTests(unittest.TestCase):
    def test_refuses_existing_project_before_external_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "ghidra"
            project.mkdir()
            marker = project / "annotations.txt"
            marker.write_text("preserve these names")
            commands = root / "commands"
            commands.mkdir()
            for command in ("python3", "curl", "brew"):
                path = commands / command
                path.write_text("#!/bin/sh\nexit 99\n")
                path.chmod(0o755)
            result = subprocess.run(
                ["/bin/sh", str(SCRIPT), str(root)],
                env={**os.environ, "PATH": f"{commands}:/usr/bin:/bin"},
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("already exists", result.stderr)
            self.assertEqual(marker.read_text(), "preserve these names")


if __name__ == "__main__":
    unittest.main()
