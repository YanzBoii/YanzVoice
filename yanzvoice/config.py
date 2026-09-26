"""Persisted user settings (API key, hotkey, behaviour)."""
from __future__ import annotations

import json
import os
from pathlib import Path

APP_NAME = "YanzVoice"

DEFAULTS = {
    "groq_api_key": "",
    "model": "whisper-large-v3-turbo",
    "language": "fr",
    "hotkey": "<ctrl>+<space>",
    "auto_paste": True,
    "input_device": "",   # remembered by name; empty = system default
    "overlay_pos": None,  # [x, y] once the user has dragged it somewhere
}


def config_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    d = Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_path() -> Path:
    return config_dir() / "config.json"


def load() -> dict:
    cfg = dict(DEFAULTS)
    path = config_path()
    if path.exists():
        try:
            cfg.update(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass
    env_key = os.environ.get("GROQ_API_KEY")
    if env_key and not cfg.get("groq_api_key"):
        cfg["groq_api_key"] = env_key
    return cfg


def save(cfg: dict) -> None:
    config_path().write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8"
    )
