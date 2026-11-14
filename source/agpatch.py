#!/usr/bin/env python3
"""agpatch — точка входа CLI для macOS.

Запуск:
    python3 agpatch.py [command]

Обычно вызывается через лаунчер `agpatch` (см. install.sh),
который добавляет этот каталог в sys.path и проксирует аргументы.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


def main():
    from patcher.commands import main as cli_main

    return cli_main()


if __name__ == "__main__":
    sys.exit(main())
