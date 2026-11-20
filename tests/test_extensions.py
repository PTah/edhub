import tempfile
import unittest
from pathlib import Path
from unittest import mock

from edhud import extensions


class ExtensionLoadTests(unittest.TestCase):
    def test_no_file_means_no_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(extensions.load(object(), Path(tmp)), [])

    def test_loads_create_and_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "ext.py").write_text(
                "class E:\n    tab_title='X'\n    stopped=False\n"
                "    def build_tab(self, parent, colors, set_title): pass\n"
                "    def stop(self): E.stopped=True\n"
                "def create(app): return E()\n",
                encoding="utf-8",
            )
            found = extensions.load(object(), Path(tmp))
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0].tab_title, "X")
            extensions.stop_all(found)
            self.assertTrue(type(found[0]).stopped)

    def test_broken_extension_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "ext.py").write_text("def create(app): raise RuntimeError('boom')\n", encoding="utf-8")
            with mock.patch.object(extensions, "_log") as log:
                self.assertEqual(extensions.load(object(), Path(tmp)), [])
            log.assert_called_once()


if __name__ == "__main__":
    unittest.main()
