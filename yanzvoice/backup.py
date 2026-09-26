"""Export and import the local settings, API key included.

The point is to move a working setup between machines without ever putting
the key in the repository. The exported file is a private artefact: it holds
the Groq key in clear text and must stay off any public share.
"""
from __future__ import annotations

import ctypes
import json
from datetime import datetime
from pathlib import Path

from . import config
from .logging_setup import log

SECRET_KEYS = ("groq_api_key",)
# Machine-specific values: carrying them over does more harm than good.
LOCAL_ONLY = ("overlay_pos", "input_device")

MB_ICONINFORMATION = 0x40
MB_ICONERROR = 0x10


def _notify(message: str, title: str = "YanzVoice", error: bool = False) -> None:
    """A dialog, because a windowed build has no console to print to."""
    print(message)
    try:
        ctypes.windll.user32.MessageBoxW(
            0, message, title, MB_ICONERROR if error else MB_ICONINFORMATION
        )
    except Exception:
        pass


def default_export_path() -> Path:
    stamp = datetime.now().strftime("%Y-%m-%d")
    documents = Path.home() / "Documents"
    folder = documents if documents.is_dir() else Path.home()
    return folder / f"yanzvoice-config-{stamp}.json"


def export_config(destination: str | None = None) -> int:
    cfg = config.load()
    path = Path(destination).expanduser() if destination else default_export_path()

    payload = {
        "_app": "YanzVoice",
        "_exported": datetime.now().isoformat(timespec="seconds"),
        "_warning": "Ce fichier contient ta clé API Groq en clair. Ne le partage pas.",
        "settings": {k: v for k, v in cfg.items() if k not in LOCAL_ONLY},
    }

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except OSError as exc:
        _notify(f"Écriture impossible : {exc}", error=True)
        return 1

    has_key = bool(cfg.get("groq_api_key"))
    log.info("config exported to %s (key included: %s)", path, has_key)
    _notify(
        f"Réglages exportés vers :\n{path}\n\n"
        + (
            "Ta clé API est dedans, en clair.\n"
            "Garde ce fichier privé : ne le mets jamais sur GitHub."
            if has_key
            else "Aucune clé API n'était enregistrée."
        )
    )
    return 0


def import_config(source: str) -> int:
    path = Path(source).expanduser()
    if not path.is_file():
        _notify(f"Fichier introuvable :\n{path}", error=True)
        return 1

    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        _notify(f"Fichier illisible :\n{exc}", error=True)
        return 1

    # Accept both the wrapped export and a bare config.json.
    incoming = payload.get("settings") if isinstance(payload, dict) else None
    if incoming is None:
        incoming = payload
    if not isinstance(incoming, dict):
        _notify("Ce fichier ne contient pas de réglages YanzVoice.", error=True)
        return 1

    known = set(config.DEFAULTS)
    cfg = config.load()
    applied = [
        key for key, value in incoming.items()
        if key in known and key not in LOCAL_ONLY and (cfg.update({key: value}) or True)
    ]

    config.save(cfg)
    log.info("config imported from %s (%d keys)", path, len(applied))

    secrets = [k for k in applied if k in SECRET_KEYS and cfg.get(k)]
    _notify(
        f"{len(applied)} réglage(s) importé(s) depuis :\n{path}\n\n"
        + ("Clé API restaurée." if secrets else "Aucune clé API dans ce fichier.")
        + "\n\nRelance YanzVoice pour qu'ils prennent effet."
    )
    return 0
