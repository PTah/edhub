# Created by nc.ai 1.2.15 on Papasha 2026-11-15 11:19:11
"""Версия программы и версия сборки должны совпадать.

Автообновление (`edhud.update.check`) сравнивает `edhud.__version__` с тегом
последнего релиза на GitHub, а установщик и имена архивов берут версию из
`pyproject.toml`. Стоит им разойтись — приложение либо вечно считает себя
старым, либо никогда не видит обновлений.
"""
import tomllib
from pathlib import Path

from edhud import __version__

ROOT = Path(__file__).resolve().parent.parent


def test_version_matches_pyproject():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert __version__ == data["project"]["version"], (
        f"edhud.__version__={__version__} != pyproject version={data['project']['version']}"
    )


def test_version_is_plain_semver():
    parts = __version__.split(".")
    assert len(parts) == 3, __version__
    assert all(part.isdigit() for part in parts), __version__
