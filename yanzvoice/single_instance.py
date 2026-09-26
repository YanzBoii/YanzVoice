"""One running copy, no matter how many times the launcher is clicked.

Without this, every launch registers its own global hotkey, so Ctrl+Space
wakes all of them at once and old builds linger behind new ones.

A second launch hands its request to the first instance over a named pipe and
exits, so clicking the shortcut again simply reveals the pill already running.
"""
from __future__ import annotations

import getpass

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

from .logging_setup import log

CONNECT_TIMEOUT_MS = 400
SHOW = b"show\n"


def _server_name() -> str:
    """Per-user, so two accounts on one machine don't fight over the pipe."""
    try:
        user = getpass.getuser()
    except Exception:
        user = "default"
    return f"YanzVoice-{user}"


class SingleInstance(QObject):
    """Owns the pipe. `activated` fires when another launch asks us to show."""

    activated = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._server: QLocalServer | None = None

    def try_signal_existing(self) -> bool:
        """True when another instance answered and was asked to show itself."""
        socket = QLocalSocket()
        socket.connectToServer(_server_name())
        if not socket.waitForConnected(CONNECT_TIMEOUT_MS):
            return False
        socket.write(SHOW)
        socket.flush()
        socket.waitForBytesWritten(CONNECT_TIMEOUT_MS)
        socket.disconnectFromServer()
        log.info("another instance is running; asked it to show and exiting")
        return True

    def listen(self) -> bool:
        """Claims the pipe for this process."""
        name = _server_name()
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_connection)

        if not self._server.listen(name):
            # A crashed instance can leave the name behind; reclaim it once.
            QLocalServer.removeServer(name)
            if not self._server.listen(name):
                log.warning("could not claim %s: %s", name, self._server.errorString())
                return False
        log.info("instance lock held on %s", name)
        return True

    def _on_connection(self) -> None:
        socket = self._server.nextPendingConnection() if self._server else None
        if socket is None:
            return
        socket.readyRead.connect(lambda: self._read(socket))
        socket.disconnected.connect(socket.deleteLater)

    def _read(self, socket: QLocalSocket) -> None:
        if SHOW.strip() in bytes(socket.readAll()):
            log.info("show requested by a second launch")
            self.activated.emit()

    def close(self) -> None:
        if self._server is not None:
            self._server.close()
            self._server = None
