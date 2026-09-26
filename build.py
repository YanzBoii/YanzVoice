"""Builds the standalone Windows application, then zips it for transfer.

    .venv\\Scripts\\python.exe build.py

Produces `dist/YanzVoice/YanzVoice.exe` (a folder that starts instantly) and
`dist/YanzVoice-windows.zip` to hand to another machine. The target PC needs
nothing installed: Python, Qt, PortAudio and libsndfile all travel inside.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

def _use_utf8() -> None:
    """The Windows console defaults to cp1252 and chokes on accents."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass


_use_utf8()

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
APP = "YanzVoice"
ICON = ROOT / "assets" / "icons" / "yanzvoice.ico"

# Qt ships far more than a tray app needs; dropping these halves the download.
EXCLUDE = [
    "PyQt6.QtQml", "PyQt6.QtQuick", "PyQt6.QtQuick3D", "PyQt6.QtWebEngineCore",
    "PyQt6.QtWebEngineWidgets", "PyQt6.QtMultimedia", "PyQt6.Qt3DCore",
    "PyQt6.QtCharts", "PyQt6.QtDataVisualization", "PyQt6.QtPdf",
    "PyQt6.QtBluetooth", "PyQt6.QtPositioning", "PyQt6.QtSql",
    "PyQt6.QtTest", "PyQt6.QtDesigner", "PyQt6.QtHelp",
    "tkinter", "unittest", "pydoc", "doctest", "pdb",
    "matplotlib", "PIL", "scipy", "pandas",
]

HIDDEN = ["sounddevice", "soundfile", "_cffi_backend"]


def check_pyinstaller() -> bool:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller manquant. Installe-le :")
        print(f"  {sys.executable} -m pip install pyinstaller")
        return False
    return True


def stop_running() -> None:
    """A previous build still running holds its own DLLs open.

    taskkill is not always on PATH for a windowed parent, so PowerShell is
    the fallback; either way we wait for the handles to actually drop.
    """
    commands = [
        ["taskkill", "/IM", f"{APP}.exe", "/F"],
        ["powershell", "-NoProfile", "-Command",
         f"Get-Process {APP} -ErrorAction SilentlyContinue | Stop-Process -Force"],
    ]
    stopped = False
    for command in commands:
        try:
            done = subprocess.run(command, capture_output=True, text=True, timeout=25)
        except (OSError, subprocess.SubprocessError):
            continue
        if done.returncode == 0:
            stopped = True
            break
    if stopped:
        print(f"  arrêté : {APP}.exe était en cours d'exécution")
        time.sleep(1.5)


def clean() -> None:
    """Removes previous output, retrying while Windows releases handles."""
    for folder in (DIST, BUILD):
        for attempt in range(4):
            if not folder.exists():
                break
            try:
                shutil.rmtree(folder)
                print(f"  nettoyé : {folder.name}/")
                break
            except PermissionError as exc:
                if attempt == 3:
                    print(f"\n  Impossible de supprimer {folder} : {exc}")
                    print("  Ferme YanzVoice.exe puis relance.")
                    raise SystemExit(1)
                time.sleep(1.5)


def build() -> bool:
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--name", APP,
        "--windowed",              # no console window behind the pill
        "--onedir",                # starts instantly; onefile re-extracts
        "--icon", str(ICON),
        "--add-data", f"{ROOT / 'assets'}{__import__('os').pathsep}assets",
        "--distpath", str(DIST),
        "--workpath", str(BUILD),
        "--specpath", str(BUILD),
    ]
    for name in HIDDEN:
        args += ["--hidden-import", name]
    for name in EXCLUDE:
        args += ["--exclude-module", name]
    args.append(str(ROOT / "main.py"))

    print("Compilation… (quelques minutes)\n")
    done = subprocess.run(args)
    return done.returncode == 0


def folder_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def make_zip() -> Path | None:
    app_dir = DIST / APP
    if not app_dir.exists():
        return None
    archive = DIST / f"{APP}-windows.zip"
    print(f"\nCompression vers {archive.name}…")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for item in sorted(app_dir.rglob("*")):
            if item.is_file():
                zf.write(item, item.relative_to(app_dir.parent))
    return archive


def main() -> int:
    if not check_pyinstaller():
        return 1
    if not ICON.exists():
        print(f"Icône introuvable : {ICON}")
        return 1

    print(f"{APP} — construction de l'application autonome\n")
    clean()

    if not build():
        print("\nLa compilation a échoué.")
        return 1

    exe = DIST / APP / f"{APP}.exe"
    if not exe.exists():
        print(f"\nExécutable introuvable : {exe}")
        return 1

    archive = make_zip()

    print("\n" + "-" * 58)
    print(f"  exécutable : {exe}")
    print(f"  dossier    : {folder_size(DIST / APP) / 1024 / 1024:.0f} Mo")
    if archive:
        print(f"  archive    : {archive}")
        print(f"               {archive.stat().st_size / 1024 / 1024:.0f} Mo à transférer")
    print("-" * 58)
    print("\nSur l'autre PC : décompresse, puis lance YanzVoice.exe.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
