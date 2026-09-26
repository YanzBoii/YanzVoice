"""Publishes the repository and a downloadable release on GitHub.

    .venv\\Scripts\\python.exe publish.py

Assumes `gh auth login` has already been done. Creates the repository if it
does not exist, pushes, then attaches `dist/YanzVoice-windows.zip` to a
release so the other machine has a real download link.

Safety: refuses to run if a Groq key is found anywhere in the tracked files
or in git history.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = "YanzVoice"
DESCRIPTION = "Dictée vocale Windows — Groq Whisper, collage automatique"
ARCHIVE = ROOT / "dist" / f"{REPO}-windows.zip"
VERSION = "v1.0.0"

def _use_utf8() -> None:
    """The Windows console defaults to cp1252 and chokes on accents."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass


_use_utf8()

SECRET = re.compile(r"gsk_[A-Za-z0-9]{20,}")

GH_CANDIDATES = [
    Path(r"C:\Program Files\GitHub CLI\gh.exe"),
    Path(r"C:\Program Files (x86)\GitHub CLI\gh.exe"),
]


def find_gh() -> str | None:
    found = shutil.which("gh")
    if found:
        return found
    for candidate in GH_CANDIDATES:
        if candidate.exists():
            return str(candidate)
    return None


def run(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    done = subprocess.run(args, capture_output=True, text=True, cwd=ROOT)
    if check and done.returncode != 0:
        print(f"\nÉchec : {' '.join(args[:3])}…")
        print((done.stderr or done.stdout).strip())
        raise SystemExit(1)
    return done


def secrets_present() -> bool:
    """Never publish a key, whatever the working tree looks like right now."""
    tracked = run(["git", "ls-files"]).stdout.split()
    for name in tracked:
        path = ROOT / name
        try:
            if SECRET.search(path.read_text(encoding="utf-8", errors="ignore")):
                print(f"  CLÉ TROUVÉE dans {name}")
                return True
        except (OSError, UnicodeError):
            continue

    history = run(["git", "log", "-p", "--all"], check=False).stdout
    if SECRET.search(history):
        print("  CLÉ TROUVÉE dans l'historique git")
        return True
    return False


def main() -> int:
    gh = find_gh()
    if gh is None:
        print("GitHub CLI introuvable. Installe-le :")
        print("  winget install --id GitHub.cli")
        return 1

    auth = run([gh, "auth", "status"], check=False)
    if auth.returncode != 0:
        print("Tu n'es pas connecté à GitHub. Lance d'abord, dans ton terminal :")
        print("\n  gh auth login\n")
        print("Choisis : GitHub.com, puis HTTPS, puis Login with a web browser.")
        return 1

    account = re.search(r"account (\S+)", auth.stderr + auth.stdout)
    user = account.group(1) if account else "?"
    print(f"Connecté en tant que {user}\n")

    print("Vérification qu'aucune clé API ne sera publiée…")
    if secrets_present():
        print("\nPublication annulée. Retire la clé avant de recommencer.")
        return 1
    print("  aucun secret détecté\n")

    if not ARCHIVE.exists():
        print(f"Archive manquante : {ARCHIVE}")
        print("Construis-la d'abord :  python build.py")
        return 1

    exists = run([gh, "repo", "view", f"{user}/{REPO}"], check=False).returncode == 0
    if exists:
        print(f"Le dépôt {user}/{REPO} existe déjà — mise à jour.")
        run(["git", "push", "-u", "origin", "HEAD"], check=False)
    else:
        print(f"Création du dépôt public {user}/{REPO}…")
        run([gh, "repo", "create", REPO,
             "--public", "--source", ".", "--remote", "origin",
             "--description", DESCRIPTION, "--push"])

    tag_taken = run([gh, "release", "view", VERSION], check=False).returncode == 0
    if tag_taken:
        print(f"La release {VERSION} existe — remplacement de l'archive.")
        run([gh, "release", "upload", VERSION, str(ARCHIVE), "--clobber"])
    else:
        print(f"Création de la release {VERSION} ({ARCHIVE.stat().st_size // 1024 // 1024} Mo)…")
        notes = (
            "**Application Windows autonome — rien à installer.**\n\n"
            "1. Télécharge `YanzVoice-windows.zip`\n"
            "2. Décompresse-le où tu veux\n"
            "3. Lance `YanzVoice.exe`\n\n"
            "Il te faudra une clé API Groq gratuite : "
            "https://console.groq.com/keys\n\n"
            "`YanzVoice.exe --install` ajoute les raccourcis Bureau et "
            "menu Démarrer.\n"
            "`YanzVoice.exe --diagnose` teste réseau, encodage et micro."
        )
        run([gh, "release", "create", VERSION, str(ARCHIVE),
             "--title", f"YanzVoice {VERSION}", "--notes", notes])

    url = run([gh, "repo", "view", "--json", "url", "-q", ".url"]).stdout.strip()
    print("\n" + "-" * 58)
    print(f"  Dépôt        : {url}")
    print(f"  Téléchargement: {url}/releases/latest")
    print("-" * 58)
    print("\nSur l'autre PC, ouvre ce second lien et récupère le .zip.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
