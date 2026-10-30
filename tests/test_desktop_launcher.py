import tempfile
import unittest
from pathlib import Path

from desktop_launcher import find_project_root, find_python


class DesktopLauncherTests(unittest.TestCase):
    def test_finds_project_next_to_windows_executable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.py").touch()
            (root / "frontend").mkdir()
            self.assertEqual(find_project_root(root / "启动小助手.exe"), root)

    def test_finds_project_outside_mac_app_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.py").touch()
            (root / "frontend").mkdir()
            executable = root / "启动小助手.app/Contents/MacOS/启动小助手"
            self.assertEqual(find_project_root(executable), root)

    def test_prefers_project_virtual_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            python = root / (".venv/Scripts/python.exe" if __import__("os").name == "nt" else ".venv/bin/python")
            python.parent.mkdir(parents=True)
            python.touch()
            self.assertEqual(find_python(root), str(python))
