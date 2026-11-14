"""Open AG Patcher — legacy TUI entry point.

Оставлен для совместимости (`python3 main.py "/Applications/Antigravity IDE.app"`).
Новый macOS-ориентированный вход — `agpatch` (source/agpatch.py).

На POSIX больше НЕ запрашивает sudo при старте: цели, принадлежащие
пользователю (обычный DMG-инсталл в /Applications), пишутся без root,
а для root-овых целей права запрашивает `agpatch` точечно, когда это
действительно нужно.
"""

import sys
import os

from patcher.utils.admin import is_admin, run_as_admin
from patcher.utils.console import setup_console
from patcher.cli import run_cli


def _posix_privilege_hint():
    if os.geteuid() == 0:
        return
    from patcher.utils.console import color, COLOR_DIM

    print(color("  [i] Tip: `agpatch patch` performs the same patching with automatic sudo.", COLOR_DIM))
    print(color("  [i] Writing into a user-owned .app needs no root — sudo is requested only if needed.", COLOR_DIM))
    print()


if __name__ == "__main__":
    setup_console()
    if os.name == "nt" and os.environ.get("SKIP_ELEVATION") != "1" and not is_admin():
        if run_as_admin():
            sys.exit(0)
        else:
            print("  [!] Could not elevate privileges. The script may fail to modify files.")
    elif os.name == "posix":
        _posix_privilege_hint()

    try:
        run_cli()
    except KeyboardInterrupt:
        print("\n  [i] Exiting...")
        sys.exit(0)
    except (PermissionError, OSError) as e:
        # Страховка от необработанного traceback (бэкап внутри .app -> EPERM):
        # вместо "Failed to execute script 'main'" показываем понятную подсказку.
        print(f"\n  [!] Filesystem error: {e}")
        if sys.platform == "darwin":
            print("  [i] macOS blocked writing inside the .app bundle.")
            print("  [i] Close Antigravity and retry with sudo:")
            print("        sudo agpatch patch")
            print("  [i] If it still says 'Operation not permitted', check flags:")
            print("        ls -lO '/Applications/Antigravity.app/Contents/Resources/bin/language_server'")
        else:
            print("  [i] No write access — re-run as admin/root and close Antigravity first.")
        sys.exit(1)
    except Exception as e:
        print(f"\n  [!] Unexpected error: {e}")
        print("  [i] Please report it: https://github.com/AvenCores/open-antigravity-patcher/issues")
        sys.exit(1)
