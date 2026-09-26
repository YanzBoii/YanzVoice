"""Microphone capture, conditioning, and a live amplitude feed for the waveform.

Records at the device's own native rate rather than forcing 16 kHz on it —
Bluetooth hands-free channels and shared-mode WASAPI endpoints often refuse a
rate they don't own. Resampling and gain staging happen here instead, which
also lets us rescue a very quiet microphone before Whisper ever sees it.
"""
from __future__ import annotations

import io
import threading
import wave

import numpy as np
import sounddevice as sd

from .logging_setup import log

TARGET_RATE = 16000
CHANNELS_OUT = 1

# Below this peak the take is silence, not speech. Measured on real hardware:
# a muted or wrong-profile input sits around 0.001-0.008.
SILENCE_PEAK = 0.012
# Whisper does much better on a well-levelled signal than a whisper-quiet one.
NORMALISE_TARGET = 0.85


class DeviceError(Exception):
    pass


def input_devices() -> list[tuple[int, str, int, float]]:
    """(index, name, channels, default_rate) for every usable input."""
    out = []
    try:
        devices = sd.query_devices()
    except Exception as exc:  # pragma: no cover - driver dependent
        log.error("query_devices failed: %s", exc)
        return out
    for index, dev in enumerate(devices):
        if dev.get("max_input_channels", 0) > 0:
            name = " ".join(str(dev["name"]).split())
            out.append(
                (index, name, int(dev["max_input_channels"]), float(dev["default_samplerate"]))
            )
    return out


def resolve_device(preferred_name: str | None) -> tuple[int | None, str]:
    """Maps a remembered device name back to an index, tolerating reordering.

    Indices shift whenever a Bluetooth headset connects, so the name is what
    we persist. Falls back to the system default when the device is gone.
    """
    devices = input_devices()
    if preferred_name:
        for index, name, _ch, _rate in devices:
            if name == preferred_name:
                return index, name
        for index, name, _ch, _rate in devices:
            if preferred_name.lower() in name.lower():
                return index, name
        log.warning("device %r not found, falling back to system default", preferred_name)

    try:
        default_index = sd.default.device[0]
    except Exception:
        default_index = None
    if default_index is not None and default_index >= 0:
        for index, name, _ch, _rate in devices:
            if index == default_index:
                return index, name
    if devices:
        return devices[0][0], devices[0][1]
    return None, "aucun"


def _lowpass(x: np.ndarray, factor: float) -> np.ndarray:
    """Crude anti-alias before decimation: a boxcar the width of the step."""
    taps = max(1, int(factor))
    if taps < 2:
        return x
    kernel = np.ones(taps, dtype=np.float32) / taps
    return np.convolve(x, kernel, mode="same").astype(np.float32)


def resample(x: np.ndarray, src_rate: float, dst_rate: int = TARGET_RATE) -> np.ndarray:
    if len(x) < 2 or abs(src_rate - dst_rate) < 1.0:
        return x.astype(np.float32)
    if src_rate > dst_rate:
        x = _lowpass(x, src_rate / dst_rate)
    count = int(round(len(x) * dst_rate / src_rate))
    if count < 2:
        return np.zeros(0, dtype=np.float32)
    src_t = np.linspace(0.0, 1.0, len(x), endpoint=False)
    dst_t = np.linspace(0.0, 1.0, count, endpoint=False)
    return np.interp(dst_t, src_t, x).astype(np.float32)


class Take:
    """One recording, with everything needed to explain a bad result."""

    def __init__(self, samples: np.ndarray, rate: float, device: str):
        self.samples = samples
        self.rate = rate
        self.device = device
        self.peak = float(np.max(np.abs(samples))) if len(samples) else 0.0
        self.rms = float(np.sqrt(np.mean(np.square(samples)))) if len(samples) else 0.0

    @property
    def seconds(self) -> float:
        return len(self.samples) / float(self.rate) if self.rate else 0.0

    @property
    def is_silent(self) -> bool:
        return self.peak < SILENCE_PEAK

    def prepared(self) -> np.ndarray:
        """Normalised, resampled mono ready for the API."""
        x = resample(self.samples, self.rate, TARGET_RATE)
        peak = float(np.max(np.abs(x))) if len(x) else 0.0
        if peak > 1e-6:
            x = x * (NORMALISE_TARGET / peak)
        return np.clip(x, -1.0, 1.0)

    def describe(self) -> str:
        return (
            f"device={self.device!r} rate={self.rate:.0f} "
            f"dur={self.seconds:.2f}s peak={self.peak:.5f} rms={self.rms:.5f}"
        )


class Recorder:
    def __init__(self, level_slots: int = 30):
        self._stream: sd.InputStream | None = None
        self._chunks: list[np.ndarray] = []
        self._lock = threading.Lock()
        self.levels = np.zeros(level_slots, dtype=np.float32)
        self.error: str | None = None
        self.device_index: int | None = None
        self.device_name: str = ""
        self.rate: float = TARGET_RATE
        self._gain = 1.0

    @property
    def is_recording(self) -> bool:
        return self._stream is not None

    def _callback(self, indata, frames, time_info, status):  # noqa: ARG002
        if status:
            log.debug("stream status: %s", status)
        block = indata.mean(axis=1) if indata.ndim > 1 and indata.shape[1] > 1 else indata[:, 0]
        block = block.astype(np.float32, copy=True)
        with self._lock:
            self._chunks.append(block)

        rms = float(np.sqrt(np.mean(np.square(block))))
        # Display-only gain: quiet hardware should still move the bars.
        level = min(1.0, (rms * self._gain) ** 0.5 * 3.2)
        self.levels[:-1] = self.levels[1:]
        self.levels[-1] = level

    def start(self, preferred_name: str | None = None) -> bool:
        if self._stream is not None:
            return True
        self.error = None
        with self._lock:
            self._chunks = []
        self.levels[:] = 0.0

        index, name = resolve_device(preferred_name)
        if index is None:
            self.error = "aucun périphérique d'entrée détecté"
            log.error(self.error)
            return False

        try:
            info = sd.query_devices(index)
            channels = min(2, max(1, int(info["max_input_channels"])))
            rate = float(info["default_samplerate"])
        except Exception as exc:
            self.error = f"périphérique illisible : {exc}"
            log.error(self.error)
            return False

        self.device_index, self.device_name, self.rate = index, name, rate
        self._gain = 8.0  # display gain; real gain is applied at prepare time

        try:
            self._stream = sd.InputStream(
                device=index,
                samplerate=rate,
                channels=channels,
                dtype="float32",
                blocksize=0,
                callback=self._callback,
            )
            self._stream.start()
        except Exception as exc:
            self._stream = None
            self.error = str(exc)
            log.error("open failed on %r @%.0fHz x%d: %s", name, rate, channels, exc)
            return False

        log.info("recording on %r @%.0fHz x%d", name, rate, channels)
        return True

    def stop(self) -> Take:
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception as exc:  # pragma: no cover - driver dependent
                log.warning("close failed: %s", exc)
        with self._lock:
            chunks = self._chunks
            self._chunks = []
        samples = (
            np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
        )
        take = Take(samples, self.rate, self.device_name)
        log.info("take: %s", take.describe())
        return take


def to_wav_bytes(samples: np.ndarray, sample_rate: int = TARGET_RATE) -> bytes:
    """Kept for the diagnostic self-test; the app path uses encode.encode()."""
    from .encode import _wav

    return _wav(samples, sample_rate)
