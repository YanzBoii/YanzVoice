"""HTTP plumbing tuned for a slow, flaky Windows uplink.

Three things matter here, in order of how much they cost the user:

1. The TLS handshake. On a weak link, DNS + TCP + TLS is several round trips
   before a single byte of audio moves. We do it while the user is still
   talking, so by the time they stop it is already paid for.
2. A broken IPv6 route. When AAAA resolution fails, every connection stalls on
   it first. We probe once and pin IPv4 for the session if so.
3. Connection resets (WinError 10054). Retries with backoff, and a fallback
   that drops the environment's proxy settings.
"""
from __future__ import annotations

import os
import socket
import threading
import time
from contextlib import contextmanager

import requests
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .logging_setup import log

HOST = "api.groq.com"
ORIGIN = f"https://{HOST}"

# Generous connect timeout: a weak link is slow, not broken.
CONNECT_TIMEOUT = 20
READ_TIMEOUT = 120

RETRY = Retry(
    total=3,
    connect=3,
    read=2,
    backoff_factor=0.9,
    status_forcelist=(408, 425, 429, 500, 502, 503, 504),
    allowed_methods=frozenset({"POST", "HEAD", "GET"}),
    raise_on_status=False,
)

_ipv6_broken: bool | None = None
_original_gai_family = urllib3.util.connection.allowed_gai_family


def _pin_ipv4() -> None:
    urllib3.util.connection.allowed_gai_family = lambda: socket.AF_INET


def probe_ipv6() -> bool:
    """Checks AAAA resolution once; pins IPv4 for the session when it fails.

    A machine whose IPv6 is advertised but unroutable stalls every connection
    on a doomed attempt first — worth one probe at startup to avoid.
    """
    global _ipv6_broken
    if _ipv6_broken is not None:
        return not _ipv6_broken
    try:
        socket.getaddrinfo(HOST, 443, socket.AF_INET6, socket.SOCK_STREAM)
        _ipv6_broken = False
        log.info("IPv6 resolves; leaving address family to the OS")
    except OSError as exc:
        _ipv6_broken = True
        _pin_ipv4()
        log.info("IPv6 unavailable (%s); pinning IPv4 for this session", exc)
    return not _ipv6_broken


def make_session(trust_env: bool = True, keep_alive: bool = True) -> requests.Session:
    session = requests.Session()
    session.trust_env = trust_env
    adapter = HTTPAdapter(max_retries=RETRY, pool_connections=2, pool_maxsize=4)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    if not keep_alive:
        session.headers["Connection"] = "close"
    # Whisper responses are small JSON; asking for gzip costs nothing.
    session.headers["Accept-Encoding"] = "gzip, deflate"
    return session


@contextmanager
def _no_proxy_env():
    """Temporarily clears proxy variables that can point at a dead proxy."""
    keys = [k for k in os.environ if k.lower().endswith("_proxy")]
    saved = {k: os.environ.pop(k) for k in keys}
    try:
        yield
    finally:
        os.environ.update(saved)


class Connection:
    """A session kept warm so the handshake is already done when audio lands."""

    # A pooled socket older than this is likely dead on a flaky link.
    MAX_WARM_AGE = 55.0

    def __init__(self):
        self._session: requests.Session | None = None
        self._warmed_at = 0.0
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def _fresh_session(self) -> requests.Session:
        return make_session(trust_env=True, keep_alive=True)

    def prewarm(self) -> None:
        """Opens DNS + TCP + TLS in the background. Safe to call repeatedly."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(target=self._do_prewarm, daemon=True)
            self._thread.start()

    def _do_prewarm(self) -> None:
        probe_ipv6()
        started = time.perf_counter()
        session = self._fresh_session()
        try:
            # Any cheap request establishes the connection; the pool keeps it.
            session.head(ORIGIN, timeout=(CONNECT_TIMEOUT, 15), allow_redirects=False)
        except requests.RequestException as exc:
            log.debug("prewarm failed (harmless): %s", exc)
            session.close()
            return
        elapsed = (time.perf_counter() - started) * 1000
        with self._lock:
            old, self._session = self._session, session
            self._warmed_at = time.monotonic()
        if old is not None:
            old.close()
        log.info("connection warm in %.0f ms", elapsed)

    def _take_warm(self) -> requests.Session | None:
        with self._lock:
            session = self._session
            age = time.monotonic() - self._warmed_at
            self._session = None
        if session is None:
            return None
        if age > self.MAX_WARM_AGE:
            log.debug("warm connection too old (%.0fs), discarding", age)
            session.close()
            return None
        log.info("reusing warm connection (%.1fs old)", age)
        return session

    def post(self, path: str, **kwargs) -> requests.Response:
        """POSTs, preferring the warm connection and falling back on failure.

        Raises the last RequestException when every attempt fails.
        """
        probe_ipv6()
        url = f"{ORIGIN}{path}"
        attempts: list[tuple[str, requests.Session, bool]] = []

        warm = self._take_warm()
        if warm is not None:
            attempts.append(("warm", warm, True))
        attempts.append(("fresh", self._fresh_session(), True))

        last: Exception | None = None
        for name, session, owned in attempts:
            try:
                started = time.perf_counter()
                resp = session.post(url, **kwargs)
            except requests.RequestException as exc:
                last = exc
                log.warning("%s attempt failed: %s", name, exc)
                if owned:
                    session.close()
                continue
            log.info(
                "%s attempt: HTTP %s in %.0f ms",
                name, resp.status_code, (time.perf_counter() - started) * 1000,
            )
            if owned:
                session.close()
            return resp

        # Last resort: ignore any proxy configuration, force a clean socket.
        log.warning("falling back to no-proxy attempt")
        try:
            with _no_proxy_env():
                session = make_session(trust_env=False, keep_alive=False)
                try:
                    return session.post(url, **kwargs)
                finally:
                    session.close()
        except requests.RequestException as exc:
            last = exc

        assert last is not None
        raise last

    def close(self) -> None:
        with self._lock:
            session, self._session = self._session, None
        if session is not None:
            session.close()


connection = Connection()


def describe_environment() -> str:
    found = {
        k: v for k, v in os.environ.items()
        if k.lower() in {"http_proxy", "https_proxy", "all_proxy", "no_proxy"}
    }
    return str(found) if found else "aucun proxy dans l'environnement"
