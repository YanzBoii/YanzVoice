"""`python main.py --diagnose` — tests each layer separately and reports.

Written to answer one question: when a dictation fails, which link broke?
"""
from __future__ import annotations

import socket
import ssl
import time

import numpy as np
import requests

from . import config
from .audio import SILENCE_PEAK, input_devices, resolve_device
from .encode import HAVE_FLAC, HAVE_OPUS, encode
from .logging_setup import log_path
from .net import CONNECT_TIMEOUT, ORIGIN, connection, describe_environment, probe_ipv6

HOST = "api.groq.com"

_report: "Tee | None" = None


def emit(text: str = "") -> None:
    if _report is not None:
        _report(text)
    else:
        print(text)
OK, BAD, WARN = "  [OK]  ", "  [KO]  ", "  [!]   "


def _title(text: str) -> None:
    emit(f"\n=== {text} ===")


def check_dns() -> bool:
    _title("1. Résolution DNS")
    ok = False
    for family, label in ((socket.AF_INET, "IPv4"), (socket.AF_INET6, "IPv6")):
        try:
            infos = socket.getaddrinfo(HOST, 443, family, socket.SOCK_STREAM)
            addrs = sorted({i[4][0] for i in infos})
            emit(f"{OK}{label}: {', '.join(addrs)}")
            ok = ok or family == socket.AF_INET
        except OSError as exc:
            emit(f"{WARN}{label}: {exc}")
    if not ok:
        emit(f"{BAD}Aucune adresse IPv4 — le DNS est cassé ou filtré.")
    return ok


def check_tls() -> bool:
    _title("2. Poignée de main TLS")
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((HOST, 443), timeout=12) as raw:
            with ctx.wrap_socket(raw, server_hostname=HOST) as tls:
                cert = tls.getpeercert()
                issuer = dict(x[0] for x in cert.get("issuer", ()))
                name = issuer.get("organizationName", "inconnu")
                emit(f"{OK}{tls.version()} — certificat émis par : {name}")
                # An antivirus doing HTTPS inspection substitutes its own CA.
                if not any(
                    k in name.lower()
                    for k in ("let's encrypt", "google", "digicert", "amazon", "cloudflare", "sectigo")
                ):
                    emit(
                        f"{WARN}Émetteur inhabituel. Un antivirus ou un proxy "
                        "inspecte probablement le HTTPS — c'est la cause la plus "
                        "fréquente des coupures 10054."
                    )
        return True
    except Exception as exc:
        emit(f"{BAD}{exc}")
        return False


def check_encoding() -> None:
    _title("3. Compression de la charge utile")
    codecs = []
    if HAVE_OPUS:
        codecs.append("Opus")
    if HAVE_FLAC:
        codecs.append("FLAC")
    codecs.append("WAV")
    emit(f"        encodeurs disponibles : {', '.join(codecs)}")

    rng = np.random.default_rng(0)
    t = np.linspace(0, 30, 30 * 16000, endpoint=False)
    env = 0.5 + 0.5 * np.sin(2 * np.pi * 2.5 * t)
    speech = sum(
        np.sin(2 * np.pi * f * t) * a
        for f, a in [(130, 0.5), (420, 0.3), (980, 0.15), (2400, 0.06)]
    )
    x = np.clip((speech * env * 0.5 + rng.normal(0, 0.004, len(t))), -1, 1).astype("float32")

    payload = encode(x, trim=False)
    pcm = len(x) * 2
    ratio = pcm / max(1, len(payload))
    marker = OK if payload.codec == "opus" else WARN
    emit(
        f"{marker}30 s de parole -> {len(payload)/1024:.0f} Ko en {payload.codec} "
        f"({ratio:.1f}x plus petit que le PCM brut)"
    )
    for label, bits in (("0,4 Mbit/s", 400_000), ("1 Mbit/s", 1_000_000)):
        emit(f"        envoi estime a {label} : {len(payload)*8/bits:.1f} s "
              f"(PCM : {pcm*8/bits:.1f} s)")


def check_upload(api_key: str) -> bool:
    _title("4. Envoi réel vers l'API")
    if not api_key:
        emit(f"{WARN}Aucune clé API enregistrée — envoi non testé.")
        return False

    tone = (np.sin(np.linspace(0, 440 * 2 * np.pi, 16000)) * 0.3).astype(np.float32)
    payload = encode(tone, trim=False)
    emit(f"        charge utile : {len(payload)} octets ({payload.codec})")

    started = time.perf_counter()
    connection.prewarm()
    try:
        resp = connection.post(
            "/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (payload.filename, payload.data, payload.mime)},
            data={"model": "whisper-large-v3-turbo", "response_format": "json"},
            timeout=(CONNECT_TIMEOUT, 90),
        )
    except requests.RequestException as exc:
        emit(f"{BAD}{type(exc).__name__} — {exc}")
        return False

    elapsed = (time.perf_counter() - started) * 1000
    marker = OK if resp.status_code < 400 else WARN
    emit(f"{marker}HTTP {resp.status_code} en {elapsed:.0f} ms")
    return resp.status_code < 400


def check_microphone(preferred: str | None) -> bool:
    _title("5. Microphone")
    devices = input_devices()
    if not devices:
        emit(f"{BAD}Aucun périphérique d'entrée.")
        return False

    for index, name, channels, rate in devices:
        emit(f"        [{index}] {name} ({channels}ch, {int(rate)} Hz)")

    index, resolved = resolve_device(preferred)
    emit(f"\n        Sélectionné : « {resolved} »")

    import sounddevice as sd

    try:
        info = sd.query_devices(index)
        rate = float(info["default_samplerate"])
        channels = min(2, max(1, int(info["max_input_channels"])))
        emit("        Parle maintenant (2 s)…")
        data = sd.rec(int(2 * rate), samplerate=rate, channels=channels,
                      dtype="float32", device=index)
        sd.wait()
        mono = data.mean(axis=1) if channels > 1 else data[:, 0]
        peak = float(np.max(np.abs(mono)))
    except Exception as exc:
        emit(f"{BAD}{exc}")
        return False

    if peak < SILENCE_PEAK:
        emit(f"{BAD}Niveau crête {peak:.5f} — trop faible, ce micro ne capte rien.")
        return False
    emit(f"{OK}Niveau crête {peak:.4f} — correct.")
    return True


class Tee:
    """Prints and records at once.

    A windowed build has no console, so on the other machine the report has
    to survive as a file the user can open and send back.
    """

    def __init__(self, destination):
        self.destination = destination
        self.lines: list[str] = []

    def __call__(self, text: str = "") -> None:
        print(text)
        self.lines.append(text)

    def save(self) -> None:
        try:
            body = "\n".join(self.lines) + "\n"
            # BOM so Notepad and PowerShell show the accents correctly.
            self.destination.write_text(body, encoding="utf-8-sig")
        except OSError as exc:
            print(f"(rapport non écrit : {exc})")


def diagnose() -> int:
    global _report
    destination = config.config_dir() / "diagnostic.txt"
    _report = Tee(destination)

    cfg = config.load()
    key = cfg.get("groq_api_key", "")

    emit("YanzVoice — diagnostic")
    emit(f"  clé API      : {'présente (' + key[:7] + '…)' if key else 'ABSENTE'}")
    emit(f"  micro choisi : {cfg.get('input_device') or 'défaut système'}")
    emit(f"  proxy        : {describe_environment()}")
    probe_ipv6()
    emit(f"  journal      : {log_path()}")

    dns = check_dns()
    tls = check_tls()
    check_encoding()
    working = check_upload(key)
    mic = check_microphone(cfg.get("input_device") or None)

    _title("Conclusion")
    if not dns or not tls:
        emit("Le problème est réseau, avant même l'API. Vérifie VPN, pare-feu,")
        emit("et l'inspection HTTPS de ton antivirus.")
    elif not working and key:
        emit("L'envoi échoue. Désactive temporairement l'antivirus / le VPN")
        emit("pour confirmer, puis ajoute une exception pour api.groq.com.")
    elif working:
        emit("L'envoi vers l'API fonctionne.")
    if not mic:
        emit("Le micro sélectionné ne capte rien : choisis-en un autre dans les réglages.")
    emit()
    emit(f"Rapport écrit dans : {destination}")
    _report.save()
    return 0
