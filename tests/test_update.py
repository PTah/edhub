"""Проверка версий и подмена файлов обновления без сети и без PowerShell."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import os
from unittest import mock

from edhud.update import (
    SPAWN_FLAGS,
    CREATE_BREAKAWAY_FROM_JOB,
    CREATE_NO_WINDOW,
    Asset,
    _install_tree,
    _replace_file,
    _same_path,
    apply_update,
    compare_versions,
    helper_command,
    pick_asset,
    process_alive,
    same_exe_parent,
    wait_pids_from_argv,
)


class UpdateTests(unittest.TestCase):
    def test_version_order(self) -> None:
        self.assertEqual(compare_versions("1.2.12", "1.3.0"), -1)
        self.assertEqual(compare_versions("v1.3.0", "1.3.0"), 0)
        self.assertEqual(compare_versions("1.3.0", "1.2.9"), 1)
        self.assertEqual(compare_versions("1.3", "1.3.0"), 0)

    def test_pick_asset_matches_layout(self) -> None:
        assets = [
            Asset("EDHUD-Setup-1.3.0.exe", "https://example/setup"),
            Asset("EDHUD-portable-1.3.0.zip", "https://example/portable"),
            Asset("EDHUD-1.3.0-windows.zip", "https://example/win"),
        ]
        portable = pick_asset(assets, "onefile")
        installed = pick_asset(assets, "onedir")
        assert portable is not None and installed is not None
        self.assertIn("portable", portable.name)
        self.assertNotIn("portable", installed.name)
        self.assertTrue(installed.name.endswith(".zip"))

    def test_helper_is_the_exe_itself(self) -> None:
        command = helper_command(
            Path("C:/EDHUD/EDHUD.exe"),
            12,
            Path("C:/stage/EDHUD.exe"),
            Path("C:/EDHUD/EDHUD.exe"),
            Path("C:/log/apply.log"),
        )
        joined = " ".join(command).lower()
        self.assertIn("--apply-update", command)
        self.assertNotIn("powershell", joined)
        self.assertNotIn(".ps1", joined)
        self.assertNotIn("cmd", joined.split())
        self.assertTrue(SPAWN_FLAGS & CREATE_NO_WINDOW)
        self.assertTrue(SPAWN_FLAGS & CREATE_BREAKAWAY_FROM_JOB)
        both = helper_command(
            Path("C:/EDHUD/EDHUD.exe"),
            12,
            Path("C:/stage/EDHUD.exe"),
            Path("C:/EDHUD/EDHUD.exe"),
            Path("C:/log/apply.log"),
            extra_pids=[34],
        )
        self.assertEqual(both.count("--wait-pid"), 2)
        self.assertEqual(both[both.index("--wait-pid") + 1], "12")
        self.assertIn("34", both)

    def test_wait_pids_keep_bootloader(self) -> None:
        argv = ["EDHUD.exe", "--apply-update", "--wait-pid", "10", "--wait-pid", "11", "--wait-pid", "0"]
        self.assertEqual(wait_pids_from_argv(argv), [10, 11])

    def test_same_path_ignores_case(self) -> None:
        self.assertTrue(_same_path(r"C:\EDHUD\EDHUD.exe", r"c:\edhud\edhud.exe"))
        self.assertFalse(_same_path(r"C:\a.exe", r"C:\b.exe"))

    def test_install_retries_locked_exe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "new.exe"
            target = root / "EDHUD.exe"
            source.write_bytes(b"new-build")
            target.write_bytes(b"old-build")
            calls = {"n": 0}

            def flaky(src: Path, dst: Path) -> None:
                calls["n"] += 1
                if calls["n"] == 1:
                    raise PermissionError("locked")
                _replace_file(src, dst)

            with mock.patch("edhud.update._replace_file", flaky):
                _install_tree(source, target, pause=0)
            self.assertEqual(target.read_bytes(), b"new-build")
            self.assertEqual(calls["n"], 2)

    def test_current_process_is_alive(self) -> None:
        self.assertTrue(process_alive(os.getpid()))
        self.assertFalse(process_alive(0))
        parent = same_exe_parent(os.getpid())
        self.assertNotEqual(parent, os.getpid())

    def test_apply_replaces_file_without_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "new.exe"
            target = root / "EDHUD.exe"
            source.write_bytes(b"new-build")
            target.write_bytes(b"old-build")
            code = apply_update(0, source, target, root / "apply.log", restart=False)
            self.assertEqual(code, 0)
            self.assertEqual(target.read_bytes(), b"new-build")
            self.assertIn("files replaced", (root / "apply.log").read_text(encoding="utf-8"))

    def test_apply_copies_onedir_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "staging"
            (source / "_internal").mkdir(parents=True)
            (source / "EDHUD.exe").write_bytes(b"exe")
            (source / "_internal" / "python.dll").write_bytes(b"dll")
            target = root / "install"
            target.mkdir()
            (target / "EDHUD.exe").write_bytes(b"old")
            code = apply_update(0, source, target, None, restart=False)
            self.assertEqual(code, 0)
            self.assertEqual((target / "EDHUD.exe").read_bytes(), b"exe")
            self.assertEqual((target / "_internal" / "python.dll").read_bytes(), b"dll")
