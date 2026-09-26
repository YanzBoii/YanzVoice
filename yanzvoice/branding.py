"""Windows identity: icon, taskbar grouping, Start menu and desktop entries.

Without an explicit AppUserModelID, Windows attributes the window to
`pythonw.exe` — the taskbar shows the Python icon and groups YanzVoice with
any other Python process. Setting our own ID before the first window is
created is what makes this read as an application rather than a script.
"""
from __future__ import annotations

import ctypes
import hashlib
import subprocess
import sys
from pathlib import Path

from PyQt6.QtGui import QIcon

from . import paths
from .config import config_dir
from .logging_setup import log

APP_ID = "Yanz.YanzVoice"
APP_NAME = "YanzVoice"

ROOT = paths.resource_root()
ICON_FILE = paths.assets() / "icons" / "yanzvoice.ico"

_icon: QIcon | None = None


def set_app_user_model_id() -> bool:
    """Claims our own taskbar identity. Must run before any window exists."""
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception as exc:  # pragma: no cover - non-Windows
        log.debug("AppUserModelID unavailable: %s", exc)
        return False
    return True


def icon() -> QIcon:
    """The application icon, cached. Empty QIcon if the file is missing."""
    global _icon
    if _icon is None:
        if ICON_FILE.exists():
            _icon = QIcon(str(ICON_FILE))
        else:
            log.warning("icon not found at %s", ICON_FILE)
            _icon = QIcon()
    return _icon


def shortcut_icon() -> Path:
    """A copy of the icon named after its own content.

    Explorer caches icons by file path, so replacing `yanzvoice.ico` in place
    leaves shortcuts showing the previous artwork until the cache is cleared.
    Pointing each shortcut at a content-addressed copy means a new icon always
    gets a new path, and the cache never has a stale entry to serve.
    """
    if not ICON_FILE.exists():
        return ICON_FILE

    digest = hashlib.sha256(ICON_FILE.read_bytes()).hexdigest()[:8]
    # Beside the config, never inside the bundle: a build folder may be
    # read-only, and a onefile bundle is deleted when the app exits.
    cache = config_dir() / "icons"
    cache.mkdir(parents=True, exist_ok=True)
    stamped = cache / f"{ICON_FILE.stem}-{digest}.ico"

    if not stamped.exists():
        stamped.write_bytes(ICON_FILE.read_bytes())
        log.info("icon stamped as %s", stamped.name)

    # Drop copies of icons we no longer ship.
    for old in cache.glob(f"{ICON_FILE.stem}-*.ico"):
        if old != stamped:
            try:
                old.unlink()
                log.info("removed stale icon copy %s", old.name)
            except OSError:
                pass
    return stamped


def interpreter() -> Path:
    """The windowed interpreter, so launching never flashes a console."""
    exe = Path(sys.executable)
    windowed = exe.with_name("pythonw.exe")
    return windowed if windowed.exists() else exe


def launch_target() -> tuple[Path, str, Path]:
    """(program, arguments, working directory) a shortcut should point at."""
    if paths.is_frozen():
        exe = Path(sys.executable)
        return exe, "", exe.parent
    return interpreter(), f'"{ROOT / "main.py"}"', ROOT


def _powershell(script: str) -> tuple[bool, str]:
    try:
        done = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=45,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    if done.returncode != 0:
        return False, (done.stderr or done.stdout).strip()
    return True, done.stdout.strip()


def shortcut_targets() -> dict[str, Path]:
    desktop = Path.home() / "Desktop" / f"{APP_NAME}.lnk"
    start = (
        Path.home()
        / "AppData/Roaming/Microsoft/Windows/Start Menu/Programs"
        / f"{APP_NAME}.lnk"
    )
    startup = (
        Path.home()
        / "AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Startup"
        / f"{APP_NAME}.lnk"
    )
    return {"desktop": desktop, "start": start, "startup": startup}


def create_shortcut(destination: Path) -> tuple[bool, str]:
    """Writes a .lnk pointing at this checkout, with the app icon and ID."""
    program, arguments, workdir = launch_target()
    script = f"""
$ErrorActionPreference = 'Stop'
$dir = Split-Path -Parent '{destination}'
if (-not (Test-Path $dir)) {{ New-Item -ItemType Directory -Force -Path $dir | Out-Null }}
$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{destination}')
$s.TargetPath = '{program}'
$s.Arguments = '{arguments}'
$s.WorkingDirectory = '{workdir}'
$s.IconLocation = '{shortcut_icon()}'
$s.Description = 'Dictée vocale — {APP_NAME}'
$s.WindowStyle = 7
$s.Save()
"""
    ok, detail = _powershell(script)
    if ok:
        log.info("shortcut written: %s", destination)
    else:
        log.error("shortcut failed (%s): %s", destination, detail)
    return ok, detail


def remove_shortcut(destination: Path) -> bool:
    try:
        if destination.exists():
            destination.unlink()
            log.info("shortcut removed: %s", destination)
        return True
    except OSError as exc:
        log.error("could not remove %s: %s", destination, exc)
        return False


def runs_at_startup() -> bool:
    return shortcut_targets()["startup"].exists()


def set_run_at_startup(enabled: bool) -> bool:
    target = shortcut_targets()["startup"]
    if enabled:
        return create_shortcut(target)[0]
    return remove_shortcut(target)


def install(startup: bool = False) -> int:
    """`--install`: desktop and Start menu entries, optionally at login."""
    targets = shortcut_targets()
    print(f"{APP_NAME} — installation des raccourcis\n")
    program, arguments, _workdir = launch_target()
    print(f"  programme    : {program}")
    if arguments:
        print(f"  arguments    : {arguments}")
    print(f"  icône        : {shortcut_icon()}")
    if not ICON_FILE.exists():
        print("\n  [!] Icône introuvable — les raccourcis seront sans icône.")
    print()

    wanted = ["desktop", "start"] + (["startup"] if startup else [])
    failures = 0
    for key in wanted:
        ok, detail = create_shortcut(targets[key])
        label = {"desktop": "Bureau", "start": "Menu Démarrer", "startup": "Démarrage"}[key]
        if ok:
            print(f"  [OK] {label:<14} {targets[key]}")
        else:
            failures += 1
            print(f"  [KO] {label:<14} {detail}")

    print()
    print("Terminé." if not failures else f"{failures} raccourci(s) en échec.")
    return 1 if failures else 0


def uninstall() -> int:
    targets = shortcut_targets()
    print(f"{APP_NAME} — suppression des raccourcis\n")
    for key, path in targets.items():
        label = {"desktop": "Bureau", "start": "Menu Démarrer", "startup": "Démarrage"}[key]
        if not path.exists():
            print(f"  [--] {label:<14} absent")
        elif remove_shortcut(path):
            print(f"  [OK] {label:<14} supprimé")
        else:
            print(f"  [KO] {label:<14} échec")
    print("\nTerminé.")
    return 0
