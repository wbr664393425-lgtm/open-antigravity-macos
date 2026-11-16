"""Неинтерактивный CLI `agpatch` — обёртка над патчерами Open AG Patcher.

Зачем отдельный слой: оригинальный `main.py` — это TUI-меню, где всё
делается цифрами и подтверждениями. Для запуска «одной командой в
терминале macOS» нужен обычный интерфейс командной строки:

    agpatch                 # статус всех целей (по умолчанию)
    agpatch status          # то же явно
    agpatch patch           # пропатчить всё найденное
    agpatch patch ide app   # только выбранные цели
    agpatch restore         # откатить из бэкапов
    agpatch doctor          # диагностика окружения, целей и подписей
    agpatch menu            # старое интерактивное меню

Ключевые macOS-моменты:
  * sudo запрашивается ТОЧЕЧНО — только если целевой файл не пишется
    текущим пользователем (DMG-инсталл обычно принадлежит пользователю,
    и root не нужен вовсе);
  * подтверждения не блокируют запуск: `-y` или отсутствие TTY
    включают автосогласие;
  * экран не очищается, вывод остаётся в логе терминала.
"""

import argparse
import os
import platform
import subprocess
import sys

from patcher.constants import VERSION

TARGET_ORDER = ("ide", "app", "agy", "vscode")

TARGET_TITLES = {
    "ide": "Antigravity IDE",
    "app": "Antigravity 2.0 (language_server)",
    "agy": "Antigravity CLI (agy)",
    "vscode": "Antigravity VS Code extension",
}

TARGET_ALIASES = {
    "ide": "ide",
    "editor": "ide",
    "antigravity-ide": "ide",
    "antigravityide": "ide",
    "app": "app",
    "2.0": "app",
    "antigravity": "app",
    "manager": "app",
    "language-server": "app",
    "language_server": "app",
    "ls": "app",
    "agy": "agy",
    "cli": "agy",
    "vscode": "vscode",
    "extension": "vscode",
    "ext": "vscode",
    "all": "all",
}

# Какие файлы реально пишутся при патче каждой цели (для проверки прав).
WRITE_FILES = {
    "ide": ("main_js",),
    "app": ("manager",),
    "agy": ("agy",),
    "vscode": ("vscode_js", "vscode_agy"),
}


# ────────────────────────────────────────────────────────────── env / helpers ──
def _console():
    from patcher.utils import console

    return console


def _apply_color_mode(no_color):
    console = _console()
    if no_color or os.environ.get("NO_COLOR") or not sys.stdout.isatty():
        console.USE_COLOR = False


def _setup(no_color=False, assume_yes=False, clear_screen=False):
    from patcher.utils.console import setup_console
    from patcher.utils import session

    setup_console()
    _apply_color_mode(no_color)
    session.set_assume_yes(assume_yes)
    session.set_clear_screen(clear_screen)


def _entry_script():
    """Абсолютный путь к этому входному скрипту (нужен для sudo-перезапуска)."""
    main_mod = sys.modules.get("__main__")
    candidate = getattr(main_mod, "__file__", None) or sys.argv[0]
    return os.path.abspath(candidate)


def _is_writable(path):
    if not path:
        return False
    if os.geteuid() == 0:
        return True
    if not os.path.exists(path):
        return False
    parent = os.path.dirname(os.path.abspath(path)) or "."
    return os.access(path, os.W_OK) and os.access(parent, os.W_OK)


def _needs_root(paths):
    return any(p and os.path.exists(p) and not _is_writable(p) for p in paths)


def _elevate(argv):
    """Перезапуск через sudo, если цель принадлежит root.

    AGPATCH_ELEVATED=1 защищает от бесконечного цикла перезапусков.
    """
    from patcher.utils.console import info, warn

    if os.environ.get("AGPATCH_ELEVATED") == "1":
        warn("Already running with sudo, but the target is still not writable.")
        return False

    if not sys.stdin.isatty():
        warn("Target requires admin rights and there is no terminal for the password prompt.")
        warn("Re-run with: sudo agpatch " + " ".join(argv))
        return False

    entry = _entry_script()
    cmd = ["sudo", "/usr/bin/env", "AGPATCH_ELEVATED=1", sys.executable, entry] + list(argv)
    info("Target is not writable by the current user — requesting administrator rights (sudo)...")
    # Печатаем полную команду, а не только аргументы: "sudo patch all" выглядел
    # как вызов несуществующего бинаря.
    print(f"  $ sudo {sys.executable} {entry} {' '.join(argv)}")
    sys.stdout.flush()
    try:
        os.execvp(cmd[0], cmd)
    except Exception as e:
        warn(f"Could not re-launch with sudo: {e}")
        return False
    return False


def _abort_if_sandboxed(paths, targets):
    """Понятная диагностика, когда права уже повышены, а запись всё равно закрыта.

    Обычно это значит, что мешает не POSIX-права, а что-то уровнем выше:
    read-only том, неизменяемый флаг (uchg/schg) или приватность macOS
    «Управление приложениями» (TCC App Management), которая блокирует
    правку чужих .app даже для root.
    """
    from patcher.utils.console import err, hint, warn

    warn("Running as root, but the target is still not writable.")
    err("Refusing to continue — nothing has been modified.")
    print()
    hint("Most likely causes, check in this order:")
    hint(f"  1) immutable flags: ls -lO '{paths[0]}'   (flags column: no uchg / schg)")
    hint("  2) read-only volume: mount | grep -i applications")
    hint("  3) App Management privacy: System Settings -> Privacy & Security -> App Management")
    hint("     Allow the terminal you are using (a terminal embedded in another app")
    hint("     inherits that app's restrictions, and root does not bypass TCC).")
    hint("  4) if the app was just updated/installed by another process, wait a second and retry")
    print()
    hint("Then retry: sudo agpatch patch " + " ".join(str(t) for t in targets))
    return 1



# ─────────────────────────────────────────────────────────────── discovery ──
def discover(path_override=None, target_hint=None):
    """Находит все цели. Возвращает dict с ключами main_js/manager/agy/vscode_js/vscode_agy."""
    from patcher.ide.discovery import (
        find_install_root,
        find_main_js,
        resolve_target_path,
    )
    from patcher.manager.discovery import find_manager_binary, resolve_manager_path
    from patcher.agy.discovery import find_agy_binary, resolve_agy_path
    from patcher.vscode.discovery import (
        find_extension_js,
        find_gemini_antigravity_binary,
    )

    found = {
        "main_js": "",
        "manager": "",
        "agy": "",
        "vscode_js": "",
        "vscode_agy": "",
    }

    # target_hint может прийти списком (из argparse nargs="*") — берём первый элемент.
    if isinstance(target_hint, (list, tuple)):
        target_hint = target_hint[0] if target_hint else None

    # Явный путь: пробуем распознать тип цели (или использовать подсказку).
    if path_override:
        raw = path_override
        hint = (target_hint or "").lower()
        if hint == "ide":
            root = resolve_target_path(raw)
            found["main_js"] = find_main_js(root) if os.path.isdir(root) else root
        elif hint == "app":
            found["manager"] = resolve_manager_path(raw)
        elif hint == "agy":
            found["agy"] = resolve_agy_path(raw)
        elif hint == "vscode":
            found["vscode_js"] = resolve_extension_path_safe(raw)
        else:
            # Автоопределение: .app > main.js > language_server > agy
            root = resolve_target_path(raw)
            if os.path.isdir(root):
                found["main_js"] = find_main_js(root)
            elif root.endswith("main.js"):
                found["main_js"] = root
            if not found["main_js"]:
                found["manager"] = resolve_manager_path(raw)
            if not found["main_js"] and not found["manager"]:
                found["agy"] = resolve_agy_path(raw)

        if not any(found.values()):
            from patcher.utils.console import err

            err(f"Provided path could not be resolved: {raw}")
        else:
            # Отбрасываем пути, которых на диске нет (опечатка / неверный тип цели)
            for key, value in list(found.items()):
                if value and not os.path.exists(value):
                    found[key] = ""
            if not any(found.values()):
                from patcher.utils.console import err

                err(f"Path exists in no patchable form: {raw}")
        return found

    # Автопоиск
    ide_root = find_install_root()
    if ide_root:
        found["main_js"] = find_main_js(ide_root)
    found["manager"] = find_manager_binary()
    found["agy"] = find_agy_binary()
    found["vscode_js"] = find_extension_js()
    found["vscode_agy"] = find_gemini_antigravity_binary()
    return found


def resolve_extension_path_safe(raw):
    from patcher.vscode.discovery import resolve_extension_path

    return resolve_extension_path(raw)


def _target_files(found):
    """Файлы, относящиеся к цели (пустые строки отфильтровываются)."""
    out = {}
    for target, keys in WRITE_FILES.items():
        paths = [found.get(k, "") for k in keys]
        out[target] = [p for p in paths if p and os.path.exists(p)]
    return out


def _available_targets(found):
    files = _target_files(found)
    return [t for t in TARGET_ORDER if files.get(t)]


def _parse_targets(raw_targets):
    names = raw_targets or ["all"]
    resolved = []
    for name in names:
        key = TARGET_ALIASES.get(str(name).strip().lower())
        if not key:
            raise SystemExit(
                f"Unknown target: {name!r}. Use one of: all, ide, app, agy, vscode."
            )
        if key == "all":
            return list(TARGET_ORDER)
        if key not in resolved:
            resolved.append(key)
    # Сохраняем стабильный порядок
    return [t for t in TARGET_ORDER if t in resolved]


# ─────────────────────────────────────────────────────────────────── status ──
def cmd_status(args):
    from patcher.cli import print_target_info
    from patcher.utils.console import (
        print_menu_section,
        hint,
        ok,
        warn,
        info,
        color,
        COLOR_DIM,
        COLOR_GREEN,
    )

    found = discover(args.path, args.target)
    print()
    print_menu_section("TARGETS")
    print_target_info(
        found["main_js"],
        found["manager"],
        found["agy"],
        vscode_path=found["vscode_js"],
        vscode_agy_path=found["vscode_agy"],
        show_search_line=False,
    )
    print()

    available = _available_targets(found)
    if not available:
        warn("No Antigravity installation found.")
        hint("Install one of: Antigravity IDE, Antigravity 2.0, Antigravity CLI, or the VS Code extension.")
        hint("Then re-run: agpatch status")
        return 1

    print_menu_section("NEXT")
    for cmd, desc in (
        ("agpatch patch", "patch everything found above (auto sudo when needed)"),
        ("agpatch doctor", "environment / signature diagnostics"),
        ("agpatch restore", "roll back from backups"),
        ("agpatch menu", "original interactive menu"),
    ):
        print(f"      {color(cmd.ljust(16), COLOR_GREEN)} {color(desc, COLOR_DIM)}")
    print()
    ok(f"{len(available)} target(s) detected: {', '.join(TARGET_TITLES[t] for t in available)}")
    return 0


# ──────────────────────────────────────────────────────────────────── patch ──
def _patch_one(target, found):
    """Патчит одну цель. Возвращает True при успехе."""
    from patcher.ide.patcher import do_patch, is_already_patched as ide_patched
    from patcher.manager.patcher import (
        do_patch_manager,
        is_already_patched as mgr_patched,
    )
    from patcher.agy.patcher import do_patch_agy, is_already_patched as agy_patched
    from patcher.vscode.patcher import do_patch_vscode, is_already_patched as ext_patched
    from patcher.utils.console import err, hint, ok, print_menu_section

    print_menu_section(f"PATCH — {TARGET_TITLES[target]}")

    if target == "ide":
        path = found["main_js"]
        if not path:
            err("Antigravity IDE not found.")
            return False
        do_patch(path)
        return ide_patched(_read_text(path))

    if target == "app":
        path = found["manager"]
        if not path:
            err("Antigravity 2.0 (language_server) not found.")
            return False
        do_patch_manager(path)
        return mgr_patched(path)

    if target == "agy":
        path = found["agy"]
        if not path:
            err("Antigravity CLI (agy) not found.")
            return False
        do_patch_agy(path)
        return agy_patched(path)

    if target == "vscode":
        js = found["vscode_js"]
        binary = found["vscode_agy"]
        missing = []
        if not js:
            missing.append("extension.js (google.google-antigravity)")
        if not binary:
            missing.append("binary in ~/.gemini/bin (antigravity/agy)")
        if missing:
            err("VS Code extension patch blocked — not found: " + "; ".join(missing))
            hint("Install the extension in VS Code, run it once, then retry.")
            return False
        do_patch_vscode(js)
        do_patch_agy(binary)
        return ext_patched(_read_text(js)) and agy_patched(binary)

    return False


def _read_text(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def cmd_patch(args):
    from patcher.utils.console import (
        info,
        hint,
        ok,
        warn,
        err,
        print_menu_section,
        print_menu_footer,
    )

    targets = _parse_targets(args.target)
    found = discover(args.path, args.target[0] if args.path and args.target else None)

    files_by_target = _target_files(found)
    write_paths = [p for t in targets for p in files_by_target.get(t, [])]

    if args.dry_run:
        print_menu_section("DRY RUN — nothing will be written")
        for t in targets:
            paths = files_by_target.get(t, [])
            if paths:
                for p in paths:
                    state = "writable" if _is_writable(p) else "NEEDS SUDO"
                    ok(f"{TARGET_TITLES[t]}: would patch {p} ({state})")
            else:
                warn(f"{TARGET_TITLES[t]}: not installed / not found — skipped")
        if write_paths and _needs_root(write_paths):
            hint("Admin rights will be requested automatically for the targets above.")
        print()
        return 0

    if write_paths and _needs_root(write_paths):
        if os.environ.get("AGPATCH_ELEVATED") == "1":
            return _abort_if_sandboxed(write_paths, args.target or ["all"])
        argv = ["patch"] + list(args.target or [])
        if args.yes:
            argv.append("-y")
        if args.path:
            argv += ["--path", args.path]
        # При успехе _elevate не возвращается (exec); при неудаче идём дальше,
        # чтобы патчер показал точную причину отказа записи.
        _elevate(argv)

    results = {}
    for t in targets:
        if not files_by_target.get(t):
            warn(f"{TARGET_TITLES[t]}: not installed / not found — skipped.")
            results[t] = None
            continue
        print()
        try:
            results[t] = bool(_patch_one(t, found))
        except KeyboardInterrupt:
            raise
        except Exception as e:  # noqa: BLE001 — CLI не должен падать трейсбеком
            err(f"{TARGET_TITLES[t]}: unexpected error: {e}")
            results[t] = False

    print()
    print_menu_section("SUMMARY")
    succeeded = 0
    patched = 0
    for t in targets:
        state = results.get(t)
        if state is None:
            warn(f"{TARGET_TITLES[t]}: skipped (not found)")
        elif state:
            succeeded += 1
            patched += 1
            ok(f"{TARGET_TITLES[t]}: patched")
        else:
            succeeded += 1
            err(f"{TARGET_TITLES[t]}: failed (see messages above)")
    print()
    print_menu_footer("Restart the affected apps for the patch to take effect.")
    return 0 if patched else 1


# ────────────────────────────────────────────────────────────────── restore ──
def cmd_restore(args):
    from patcher.ide.patcher import do_restore
    from patcher.manager.patcher import do_restore_manager
    from patcher.agy.patcher import do_restore_agy
    from patcher.vscode.patcher import do_restore_vscode
    from patcher.utils.console import (
        err,
        hint,
        ok,
        warn,
        print_menu_section,
        print_menu_footer,
    )

    targets = _parse_targets(args.target)
    found = discover(args.path, args.target[0] if args.path and args.target else None)
    files_by_target = _target_files(found)

    if args.dry_run:
        print_menu_section("DRY RUN — nothing will be restored")
        for t in targets:
            for p in files_by_target.get(t, []):
                bak = p + (".agybak" if t in ("app", "agy", "vscode") else ".bak")
                exists = os.path.exists(bak)
                (ok if exists else warn)(
                    f"{TARGET_TITLES[t]}: {'backup found' if exists else 'no backup'} — {bak}"
                )
        print()
        return 0

    print_menu_section("RESTORE")
    for t in targets:
        if not files_by_target.get(t):
            warn(f"{TARGET_TITLES[t]}: not installed / not found — skipped.")
            continue
        print()
        try:
            if t == "ide":
                do_restore(found["main_js"])
            elif t == "app":
                do_restore_manager(found["manager"])
            elif t == "agy":
                do_restore_agy(found["agy"])
            elif t == "vscode":
                do_restore_vscode(found["vscode_js"])
                if found["vscode_agy"]:
                    do_restore_agy(found["vscode_agy"])
        except Exception as e:  # noqa: BLE001
            err(f"{TARGET_TITLES[t]}: restore error: {e}")
    print()
    print_menu_footer("Restart the affected apps after restoring.")
    return 0


# ─────────────────────────────────────────────────────────────────── doctor ──
def _run(cmd):
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return res.returncode, (res.stdout or "") + (res.stderr or "")
    except Exception as e:  # noqa: BLE001
        return 127, str(e)


def _signature_state(app_path):
    if not app_path or not os.path.exists(app_path):
        return "n/a"
    rc, out = _run(["/usr/bin/codesign", "-dv", app_path])
    if rc != 0:
        return "not signed / unreadable"
    if "Signature=adhoc" in out:
        return "ad-hoc (patched locally)"
    for line in out.splitlines():
        if line.startswith("Authority="):
            return line.strip().replace("Authority=", "signed: ", 1)
    return "signed"


def _quarantine_state(path):
    if not path or not os.path.exists(path):
        return "n/a"
    rc, out = _run(["/usr/bin/xattr", "-p", "com.apple.quarantine", path])
    if rc == 0 and out.strip():
        return "present"
    return "none"


def _owner(path):
    try:
        st = os.stat(path)
        import pwd
        import grp

        return f"{pwd.getpwuid(st.st_uid).pw_name}:{grp.getgrgid(st.st_gid).gr_name}"
    except Exception:
        return "?"


def _process_running(patterns):
    rc, out = _run(["pgrep", "-fl", "|".join(patterns)])
    lines = [ln for ln in out.splitlines() if ln.strip()]
    return lines


def cmd_doctor(args):
    from patcher.utils.console import (
        ok,
        warn,
        err,
        info,
        hint,
        print_menu_section,
        print_menu_footer,
    )
    from patcher.ide.discovery import get_ag_version
    from patcher.manager.discovery import get_antigravity_version
    from patcher.ide.patcher import is_already_patched as ide_patched
    from patcher.manager.patcher import is_already_patched as mgr_patched
    from patcher.agy.patcher import is_already_patched as agy_patched

    problems = 0

    print_menu_section("ENVIRONMENT")
    mac_ver = platform.mac_ver()[0] or "unknown"
    info(f"macOS:      {mac_ver} ({platform.machine()})")
    info(f"Python:     {platform.python_version()} ({sys.executable})")
    info(f"Privileges: {'root (sudo)' if os.geteuid() == 0 else 'user ' + str(os.getuid())}")
    info(f"Arch:       {'Apple Silicon' if platform.machine() == 'arm64' else 'Intel / Rosetta'}")

    for tool in ("/usr/bin/codesign", "/usr/bin/xattr", "/usr/bin/chflags", "/usr/bin/pgrep"):
        if os.path.exists(tool):
            ok(f"tool {tool}")
        else:
            err(f"tool {tool} missing")
            problems += 1

    rc, _ = _run(["/usr/bin/codesign", "-d", "/usr/bin/true"])
    if rc != 0:
        warn("codesign is not functional — install Xcode Command Line Tools: xcode-select --install")
        problems += 1

    print_menu_section("TARGETS")
    found = discover(args.path, args.target)
    rows = []
    if found["main_js"]:
        ver, _ = get_ag_version(found["main_js"])
        rows.append(
            (
                "ide",
                found["main_js"],
                ver or "?",
                "patched" if ide_patched(_read_text(found["main_js"])) else "not patched",
            )
        )
    if found["manager"]:
        ver = get_antigravity_version(found["manager"]) or "?"
        rows.append(
            (
                "app",
                found["manager"],
                ver,
                "patched" if mgr_patched(found["manager"]) else "not patched",
            )
        )
    if found["agy"]:
        rows.append(
            (
                "agy",
                found["agy"],
                "-",
                "patched" if agy_patched(found["agy"]) else "not patched",
            )
        )
    if found["vscode_js"] or found["vscode_agy"]:
        rows.append(
            (
                "vscode",
                found["vscode_js"] or found["vscode_agy"],
                "-",
                "found",
            )
        )

    if not rows:
        warn("No target found.")
        hint("Antigravity IDE: /Applications/Antigravity IDE.app")
        hint("Antigravity 2.0: /Applications/Antigravity.app")
        hint("Installed elsewhere? agpatch doctor --path '/path/to/App.app'")
        problems += 1
    else:
        for target, path, ver, state in rows:
            ok(f"{TARGET_TITLES[target]}")
            info(f"  path:       {path}")
            info(f"  version:    {ver}")
            info(f"  patch:      {state}")
            info(f"  writable:   {'yes' if _is_writable(path) else 'NO (sudo needed)'}")
            info(f"  owner:      {_owner(path)}")
            bundle = _find_bundle(path)
            if bundle:
                sig = _signature_state(bundle)
                info(f"  signature:  {sig}")
                info(f"  quarantine: {_quarantine_state(bundle)}")
                if state == "patched":
                    vrc, vout = _run(["/usr/bin/codesign", "--verify", bundle])
                    if vrc == 0:
                        ok("  verification: signature valid")
                    else:
                        err("  verification: signature BROKEN — app may be killed on launch")
                        dim_out = (vout or "").strip().splitlines()
                        if dim_out:
                            info(f"  codesign:   {dim_out[0][:100]}")
                        hint("  fix: agpatch restore && agpatch patch")
                        problems += 1
                elif "ad-hoc" in sig:
                    warn("  Patched locally but current bundle is already ad-hoc signed.")
            else:
                info(f"  signature:  {_signature_state(path)}")

    print_menu_section("RUNNING PROCESSES")
    procs = _process_running(["Antigravity", "language_server", "agy"])
    if procs:
        for line in procs[:6]:
            info(line[:120])
        hint("Patching works while running, but a restart is required afterwards.")
    else:
        ok("Antigravity processes are not running.")

    print_menu_section("VERDICT")
    if problems:
        warn(f"{problems} problem(s) found — see messages above.")
    else:
        ok("No problems detected.")
    print()
    print_menu_footer("Report issues: https://github.com/AvenCores/open-antigravity-patcher/issues")
    return 0 if not problems else 1


def _find_bundle(path):
    from patcher.utils.file import find_app_bundle

    return find_app_bundle(path)


# ──────────────────────────────────────────────────────────────────── other ──
def cmd_menu(args):
    from patcher.utils.console import err, hint

    if not sys.stdin.isatty():
        err("The interactive menu needs a terminal (stdin is not a TTY).")
        hint("Use non-interactive commands instead: agpatch status / patch / restore / doctor")
        return 1

    from patcher.cli import run_cli

    # run_cli() читает sys.argv напрямую и принял бы "menu" за путь к цели.
    saved_argv = sys.argv[:]
    sys.argv = [saved_argv[0]]
    try:
        run_cli()
    finally:
        sys.argv = saved_argv
    return 0


def cmd_version(args):
    print(f"agpatch {VERSION}")
    print(f"python {platform.python_version()} / {platform.system()} {platform.release()}")
    return 0


def cmd_self_uninstall(args):
    from patcher.utils.console import info, ok, warn, err

    home = os.path.expanduser("~")
    share = os.path.join(home, ".local", "share", "agpatch")
    bin_path = os.path.join(home, ".local", "bin", "agpatch")

    removed = 0
    for path in (bin_path,):
        if os.path.islink(path) or os.path.isfile(path):
            try:
                os.remove(path)
                ok(f"Removed {path}")
                removed += 1
            except Exception as e:  # noqa: BLE001
                err(f"Could not remove {path}: {e}")

    if os.path.isdir(share):
        import shutil

        if args.yes or _confirm("Remove installed copy in ~/.local/share/agpatch?"):
            try:
                shutil.rmtree(share)
                ok(f"Removed {share}")
                removed += 1
            except Exception as e:  # noqa: BLE001
                err(f"Could not remove {share}: {e}")
    else:
        info("No installed copy found (~/.local/share/agpatch).")

    if removed:
        ok("agpatch uninstalled. Backups inside the apps are untouched.")
        info("To also restore patched files: agpatch restore (before removing the tool).")
    else:
        warn("Nothing to uninstall.")
    return 0


def _confirm(question):
    from patcher.cli import confirmed

    return confirmed(question)


def cmd_check_updates(args):
    from patcher.utils.update import check_for_updates
    from patcher.utils.console import info

    info("Checking GitHub releases...")
    check_for_updates(silent=False)
    return 0


# ──────────────────────────────────────────────────────────────────── parser ──
def build_parser():
    parser = argparse.ArgumentParser(
        prog="agpatch",
        description="Open AG Patcher — macOS command line for Antigravity region-lock bypass.",
        epilog=(
            "Examples:\n"
            "  agpatch                      show patch status of every detected target\n"
            "  agpatch patch                patch everything that was found\n"
            "  agpatch patch ide app        patch only Antigravity IDE and Antigravity 2.0\n"
            "  agpatch patch --dry-run      show what would be patched, write nothing\n"
            "  agpatch restore              restore patched files from backups\n"
            "  agpatch doctor               full environment / signature diagnostics\n"
            "  agpatch menu                 original interactive menu\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="store_true", help="print version and exit")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="assume yes for every confirmation (non-interactive)",
    )
    common.add_argument(
        "--dry-run",
        action="store_true",
        help="do not write anything, only report what would happen",
    )
    common.add_argument(
        "--no-color",
        action="store_true",
        help="disable ANSI colors",
    )
    common.add_argument(
        "--path",
        default="",
        help="explicit path to the app bundle / binary instead of auto-detection",
    )

    sub = parser.add_subparsers(dest="command")

    p_status = sub.add_parser("status", parents=[common], help="show detected targets and patch state")
    p_status.set_defaults(func=cmd_status, target=[])

    p_patch = sub.add_parser("patch", parents=[common], help="apply patches")
    p_patch.add_argument(
        "target",
        nargs="*",
        default=["all"],
        help="all | ide | app | agy | vscode (default: all)",
    )
    p_patch.set_defaults(func=cmd_patch)

    p_restore = sub.add_parser("restore", parents=[common], help="restore from backups")
    p_restore.add_argument(
        "target",
        nargs="*",
        default=["all"],
        help="all | ide | app | agy | vscode (default: all)",
    )
    p_restore.set_defaults(func=cmd_restore)

    p_doctor = sub.add_parser("doctor", parents=[common], help="diagnose environment and targets")
    p_doctor.add_argument("target", nargs="*", default=["all"], help=argparse.SUPPRESS)
    p_doctor.set_defaults(func=cmd_doctor)

    p_checks = sub.add_parser("check-updates", parents=[common], help="check GitHub for a newer release")
    p_checks.add_argument("target", nargs="*", default=[], help=argparse.SUPPRESS)
    p_checks.set_defaults(func=cmd_check_updates)

    p_menu = sub.add_parser("menu", parents=[common], help="open the original interactive menu")
    p_menu.add_argument("target", nargs="*", default=[], help=argparse.SUPPRESS)
    p_menu.set_defaults(func=cmd_menu)

    p_uninstall = sub.add_parser("self-uninstall", parents=[common], help="remove the installed agpatch launcher")
    p_uninstall.add_argument("target", nargs="*", default=[], help=argparse.SUPPRESS)
    p_uninstall.set_defaults(func=cmd_self_uninstall)

    return parser


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)

    if "--version" in argv or "-V" in argv:
        return cmd_version(None)

    # Без подкоманды (или только с флагами) — показываем статус:
    # самый полезный дефолтный вывод для `agpatch` в терминале.
    if not argv:
        argv = ["status"]
    elif argv[0] in ("-h", "--help"):
        pass  # общий help, не help подкоманды status
    elif argv[0].startswith("-"):
        argv = ["status"] + argv

    parser = build_parser()
    args = parser.parse_args(argv)

    assume_yes = bool(getattr(args, "yes", False)) or not sys.stdin.isatty()
    _setup(
        no_color=bool(getattr(args, "no_color", False)),
        assume_yes=assume_yes,
        clear_screen=False,
    )

    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        print("\n  [i] Interrupted.")
        return 130
    except BrokenPipeError:
        return 0
