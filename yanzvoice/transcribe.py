"""Speech-to-text through the Groq Whisper endpoint."""
from __future__ import annotations

import requests

from .encode import Payload
from .logging_setup import log
from .net import CONNECT_TIMEOUT, READ_TIMEOUT, connection, describe_environment

PATH = "/openai/v1/audio/transcriptions"


class TranscriptionError(Exception):
    """Something went wrong. `short` is what fits in the pill."""

    def __init__(self, message: str, short: str = "Échec de la transcription"):
        super().__init__(message)
        self.short = short


class EmptyTranscription(TranscriptionError):
    def __init__(self):
        super().__init__(
            "L'API n'a rien reconnu dans l'enregistrement — le micro capte "
            "probablement trop faiblement.",
            short="Rien reconnu",
        )


def _connection_advice(last_error: str) -> str:
    return (
        f"La connexion à Groq a échoué : {last_error}\n"
        "Si ça se répète : un antivirus qui inspecte le HTTPS, un VPN, ou un "
        "pare-feu. Lance --diagnose pour savoir quelle couche lâche."
    )


def transcribe(
    payload: Payload,
    api_key: str,
    model: str = "whisper-large-v3-turbo",
    language: str | None = "fr",
) -> str:
    if not api_key:
        raise TranscriptionError(
            "Aucune clé API Groq. Ouvre les réglages pour en ajouter une.",
            short="Clé API manquante",
        )

    data = {"model": model, "response_format": "json", "temperature": "0"}
    if language and language != "auto":
        data["language"] = language

    log.info(
        "sending %s, %d bytes (model=%s lang=%s)",
        payload.codec, len(payload), model, language,
    )

    try:
        resp = connection.post(
            PATH,
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (payload.filename, payload.data, payload.mime)},
            data=data,
            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
        )
    except requests.Timeout as exc:
        raise TranscriptionError(
            f"L'API n'a pas répondu à temps : {exc}", short="Délai dépassé"
        ) from exc
    except requests.RequestException as exc:
        log.error("all attempts failed (%s)", describe_environment())
        raise TranscriptionError(
            _connection_advice(str(exc)), short="Connexion coupée"
        ) from exc

    if resp.status_code >= 400:
        detail = resp.text[:400]
        try:
            detail = resp.json().get("error", {}).get("message", detail)
        except ValueError:
            pass
        log.error("API %s: %s", resp.status_code, detail)

        if resp.status_code == 401:
            raise TranscriptionError(
                f"Clé API refusée (401) : {detail}", short="Clé refusée"
            )
        if resp.status_code == 413:
            raise TranscriptionError(
                "Enregistrement trop long pour l'API.", short="Trop long"
            )
        if resp.status_code == 429:
            raise TranscriptionError(
                f"Quota Groq atteint (429) : {detail}", short="Quota atteint"
            )
        raise TranscriptionError(f"Erreur API {resp.status_code} : {detail}")

    try:
        text = (resp.json().get("text") or "").strip()
    except ValueError as exc:
        log.error("unparseable body: %s", resp.text[:400])
        raise TranscriptionError(
            "Réponse illisible de l'API.", short="Réponse invalide"
        ) from exc

    log.info("transcribed %d chars", len(text))
    if not text:
        raise EmptyTranscription()
    return text
