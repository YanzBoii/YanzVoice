"""Turning a take into the smallest payload the API will accept.

On a slow uplink the encode is free and the bytes are everything: 30 s of
speech is 937 KB as 16 kHz PCM but 107 KB as Opus, which on a 0.4 Mbit/s link
is the difference between 19 seconds of waiting and 2.
"""
from __future__ import annotations

import io
import wave

import numpy as np

from .logging_setup import log

TARGET_RATE = 16000

try:
    import soundfile as sf

    _FORMATS = sf.available_formats()
    HAVE_OPUS = "OGG" in _FORMATS and "OPUS" in sf.available_subtypes("OGG")
    HAVE_FLAC = "FLAC" in _FORMATS
except Exception as exc:  # pragma: no cover - optional dependency
    sf = None
    HAVE_OPUS = HAVE_FLAC = False
    log.warning("soundfile unavailable, falling back to WAV: %s", exc)


# Silence either side of the words is pure upload cost.
TRIM_WINDOW = 0.02   # seconds per analysis frame
TRIM_MARGIN = 0.18   # keep this much around speech so nothing clips
TRIM_FLOOR = 0.055   # fraction of peak counted as speech


def trim_silence(x: np.ndarray, rate: int = TARGET_RATE) -> np.ndarray:
    """Drops leading and trailing silence, keeping a margin for consonants."""
    if len(x) < rate // 10:
        return x

    frame = max(1, int(rate * TRIM_WINDOW))
    usable = (len(x) // frame) * frame
    if usable < frame:
        return x

    energy = np.abs(x[:usable]).reshape(-1, frame).max(axis=1)
    peak = float(energy.max()) if len(energy) else 0.0
    if peak <= 0.0:
        return x

    loud = np.flatnonzero(energy >= peak * TRIM_FLOOR)
    if len(loud) == 0:
        return x

    margin = int(rate * TRIM_MARGIN)
    start = max(0, loud[0] * frame - margin)
    end = min(len(x), (loud[-1] + 1) * frame + margin)
    if end - start < rate // 10:
        return x
    return x[start:end]


class Payload:
    def __init__(self, data: bytes, filename: str, mime: str, codec: str):
        self.data = data
        self.filename = filename
        self.mime = mime
        self.codec = codec

    def __len__(self) -> int:
        return len(self.data)


def _wav(x: np.ndarray, rate: int) -> bytes:
    pcm = (np.clip(x, -1.0, 1.0) * 32767.0).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def _via_soundfile(x: np.ndarray, rate: int, fmt: str, subtype: str) -> bytes:
    buf = io.BytesIO()
    sf.write(buf, np.clip(x, -1.0, 1.0), rate, format=fmt, subtype=subtype)
    return buf.getvalue()


def encode(x: np.ndarray, rate: int = TARGET_RATE, trim: bool = True) -> Payload:
    """Best available compression, degrading safely to plain WAV."""
    if trim:
        before = len(x)
        x = trim_silence(x, rate)
        if len(x) != before:
            log.info(
                "trimmed %.2fs of silence", (before - len(x)) / float(rate)
            )

    raw = len(x) * 2  # what PCM_16 would have cost

    if HAVE_OPUS:
        try:
            data = _via_soundfile(x, rate, "OGG", "OPUS")
            log.info("opus: %d bytes (%.1fx smaller than PCM)", len(data), raw / max(1, len(data)))
            return Payload(data, "audio.ogg", "audio/ogg", "opus")
        except Exception as exc:
            log.warning("opus encode failed: %s", exc)

    if HAVE_FLAC:
        try:
            data = _via_soundfile(x, rate, "FLAC", "PCM_16")
            log.info("flac: %d bytes", len(data))
            return Payload(data, "audio.flac", "audio/flac", "flac")
        except Exception as exc:
            log.warning("flac encode failed: %s", exc)

    data = _wav(x, rate)
    log.info("wav: %d bytes", len(data))
    return Payload(data, "audio.wav", "audio/wav", "wav")
