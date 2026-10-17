#!/usr/bin/env python3
"""Запуск EDHUD без консольного окна (Windows: двойной клик / ярлык в автозагрузке)."""
from __future__ import annotations

import sys

from run import main

if __name__ == "__main__":
    sys.exit(main())
