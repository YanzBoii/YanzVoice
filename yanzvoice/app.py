"""Application controller: wires hotkey, overlay, recorder, API and paste."""
from __future__ import annotations

import os
import sys
import traceback

from PyQt6.QtCore import QObject, QRectF, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon
from pynput import keyboard

from . import branding, config, paste
from .audio import Recorder, Take
from .encode import Payload, encode
from .logging_setup import log, log_path
from .net import connection
from .single_instance import SingleInstance
from .transcribe import TranscriptionError, transcribe
from .ui import icons, theme
from .ui.overlay import DONE, ERROR, IDLE, RECORDING, WORKING, Overlay
from .ui.settings import SettingsDialog

MIN_SECONDS = 0.35


class HotkeyBridge(QObject):
    """Marshals the pynput listener thread onto the Qt event loop."""

    triggered = pyqtSignal()

    def __init__(self, combo: str):
        super().__init__()
        self.combo = combo
        self._listener: keyboard.GlobalHotKeys | None = None
        self.error: str | None = None

    def start(self) -> bool:
        try:
            self._listener = keyboard.GlobalHotKeys({self.combo: self.triggered.emit})
            self._listener.daemon = True
            self._listener.start()
        except Exception as exc:
            self.error = str(exc)
            log.error("hotkey %r failed: %s", self.combo, exc)
            return False
        log.info("hotkey registered: %s", self.combo)
        return True

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None


class TranscribeWorker(QThread):
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str, str)  # short label for the pill, full detail for the toast

    def __init__(self, payload: Payload, cfg: dict):
        super().__init__()
        self._payload = payload
        self._cfg = cfg

    def run(self) -> None:
        try:
            text = transcribe(
                self._payload,
                api_key=self._cfg.get("groq_api_key", ""),
                model=self._cfg.get("model", "whisper-large-v3-turbo"),
                language=self._cfg.get("language", "fr"),
            )
        except TranscriptionError as exc:
            self.failed.emit(exc.short, str(exc))
        except Exception as exc:  # pragma: no cover - defensive
            log.error("unexpected: %s", traceback.format_exc())
            self.failed.emit("Échec", f"Erreur inattendue : {exc}")
        else:
            self.finished_ok.emit(text)


def tray_icon() -> QIcon:
    """The shipped .ico, falling back to a drawn mark if it is missing."""
    shipped = branding.icon()
    if not shipped.isNull():
        return shipped

    pix = QPixmap(64, 64)
    pix.fill(QColor(0, 0, 0, 0))
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QColor(0, 0, 0, 0))
    p.setBrush(theme.BG)
    p.drawRoundedRect(2, 2, 60, 60, 14, 14)
    icons.draw_wave(p, QRectF(8, 8, 48, 48), theme.TEXT)
    p.end()
    return QIcon(pix)


class YanzVoice(QObject):
    def __init__(self, app: QApplication, lock: SingleInstance | None = None):
        super().__init__()
        self.app = app
        self.lock = lock
        if lock is not None:
            lock.activated.connect(self.on_second_launch)
        self.cfg = config.load()
        self.recorder = Recorder()
        self.overlay = Overlay(self.recorder)
        self.overlay.setWindowIcon(branding.icon())
        self.worker: TranscribeWorker | None = None
        self.target_hwnd = 0

        self.overlay.mic_clicked.connect(self.toggle_recording)
        self.overlay.settings_clicked.connect(self.open_settings)
        self.overlay.close_clicked.connect(self.hide_overlay)
        self.overlay.moved.connect(self.remember_position)

        self.hotkey = HotkeyBridge(self.cfg.get("hotkey", "<ctrl>+<space>"))
        self.hotkey.triggered.connect(self.on_hotkey)
        self.hotkey.start()

        self._build_tray()
        self._restore_position()
        self.overlay.show()

        if not self.cfg.get("groq_api_key"):
            self.overlay.set_state(ERROR, "Clé API manquante")
            QTimer.singleShot(400, self.open_settings)

    # ---------- tray ----------

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(tray_icon(), self.app)
        self.tray.setToolTip(
            f"YanzVoice — {self.cfg.get('hotkey', '<ctrl>+<space>')} pour afficher"
        )
        menu = QMenu()

        show = QAction("Afficher l'overlay", menu)
        show.triggered.connect(self.show_overlay)
        menu.addAction(show)

        recenter = QAction("Recentrer en bas de l'écran", menu)
        recenter.triggered.connect(self.recenter)
        menu.addAction(recenter)

        settings = QAction("Réglages…", menu)
        settings.triggered.connect(self.open_settings)
        menu.addAction(settings)

        logs = QAction("Ouvrir le journal", menu)
        logs.triggered.connect(self.open_log)
        menu.addAction(logs)

        menu.addSeparator()

        self.startup_action = QAction("Démarrer avec Windows", menu)
        self.startup_action.setCheckable(True)
        self.startup_action.setChecked(branding.runs_at_startup())
        self.startup_action.toggled.connect(self.set_run_at_startup)
        menu.addAction(self.startup_action)

        desktop = QAction("Créer un raccourci sur le bureau", menu)
        desktop.triggered.connect(self.create_desktop_shortcut)
        menu.addAction(desktop)

        menu.addSeparator()
        quit_action = QAction("Quitter", menu)
        quit_action.triggered.connect(self.quit)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_overlay()

    def set_run_at_startup(self, enabled: bool) -> None:
        if branding.set_run_at_startup(enabled):
            self.notify(
                "YanzVoice démarrera avec Windows."
                if enabled
                else "YanzVoice ne démarrera plus automatiquement.",
                title="YanzVoice",
            )
        else:
            self.startup_action.setChecked(not enabled)
            self.notify("Le raccourci de démarrage n'a pas pu être modifié.")

    def create_desktop_shortcut(self) -> None:
        target = branding.shortcut_targets()["desktop"]
        ok, detail = branding.create_shortcut(target)
        self.notify(
            f"Raccourci créé : {target.name}" if ok
            else f"Échec de la création du raccourci : {detail}"
        )

    def notify(self, message: str, title: str = "YanzVoice") -> None:
        self.tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Warning, 7000)

    def open_log(self) -> None:
        try:
            os.startfile(str(log_path()))  # noqa: S606 - user-initiated
        except OSError as exc:
            self.notify(f"Journal introuvable : {exc}")

    # ---------- placement ----------

    def _restore_position(self) -> None:
        """Puts the pill back where the user last dragged it, if still on screen."""
        pos = self.cfg.get("overlay_pos")
        if isinstance(pos, (list, tuple)) and len(pos) == 2:
            try:
                if self.overlay.move_onto_screen(int(pos[0]), int(pos[1])):
                    return
            except (TypeError, ValueError):
                pass
            log.info("saved position %s unusable, recentring", pos)
        self.overlay.place_bottom_center()

    def remember_position(self, x: int, y: int) -> None:
        self.cfg["overlay_pos"] = [int(x), int(y)]
        config.save(self.cfg)

    def recenter(self) -> None:
        self.show_overlay()
        self.overlay.place_bottom_center()
        self.remember_position(self.overlay.pos().x(), self.overlay.pos().y())

    # ---------- overlay visibility ----------

    def show_overlay(self) -> None:
        if not self.overlay.isVisible():
            self._restore_position()
            self.overlay.show()
        self.overlay.raise_()

    def hide_overlay(self) -> None:
        if self.recorder.is_recording:
            self.recorder.stop()
        self.overlay.set_state(IDLE)
        self.overlay.hide()

    def toggle_overlay(self) -> None:
        if self.overlay.isVisible():
            self.hide_overlay()
        else:
            self.show_overlay()

    def on_second_launch(self) -> None:
        """Another launch was blocked; surface the instance already running."""
        self.target_hwnd = paste.foreground_window()
        self.show_overlay()

    def on_hotkey(self) -> None:
        """Hotkey opens the overlay; pressed again it starts or stops dictation."""
        if not self.overlay.isVisible():
            self.target_hwnd = paste.foreground_window()
            self.show_overlay()
            return
        self.toggle_recording()

    # ---------- dictation ----------

    def toggle_recording(self) -> None:
        if self.overlay.state == WORKING:
            return
        if self.recorder.is_recording:
            self.stop_recording()
        else:
            self.start_recording()

    def start_recording(self) -> None:
        if not self.cfg.get("groq_api_key"):
            self.overlay.set_state(ERROR, "Clé API manquante")
            self.open_settings()
            return

        # Remember where the text should land before we take any focus.
        hwnd = paste.foreground_window()
        if hwnd and hwnd != int(self.overlay.winId()):
            self.target_hwnd = hwnd

        if not self.recorder.start(self.cfg.get("input_device") or None):
            self.overlay.set_state(ERROR, "Micro indisponible")
            self.notify(
                f"Impossible d'ouvrir le micro : {self.recorder.error}\n"
                "Choisis un autre périphérique dans les réglages."
            )
            return
        self.overlay.set_state(RECORDING)
        # The handshake costs several round trips on a weak link; pay for it
        # now, while there is still speech to record.
        connection.prewarm()

    def stop_recording(self) -> None:
        take = self.recorder.stop()

        if take.seconds < MIN_SECONDS:
            self.overlay.set_state(ERROR, "Trop court")
            self._reset_later()
            return

        if take.is_silent:
            self.overlay.set_state(ERROR, "Aucun son")
            self.notify(
                f"Le micro « {take.device} » n'a capté que du silence "
                f"(niveau crête {take.peak:.4f}).\n"
                "Ouvre les réglages et choisis explicitement le bon périphérique, "
                "puis vérifie qu'il n'est pas coupé dans Windows."
            )
            self._reset_later(3200)
            return

        self._send(take)

    def _send(self, take: Take) -> None:
        self.overlay.set_state(WORKING)
        payload = encode(take.prepared())
        log.info(
            "payload %s: %.1f KB for %.1fs", payload.codec,
            len(payload) / 1024, take.seconds,
        )
        self.worker = TranscribeWorker(payload, self.cfg)
        self.worker.finished_ok.connect(self.on_text)
        self.worker.failed.connect(self.on_failure)
        self.worker.start()

    def on_text(self, text: str) -> None:
        if self.cfg.get("auto_paste", True):
            try:
                paste.paste_into(self.target_hwnd, text)
                self.overlay.set_state(DONE)
            except Exception as exc:
                log.warning("paste failed, clipboard only: %s", exc)
                paste.copy(text)
                self.overlay.set_state(DONE, "Copié")
        else:
            paste.copy(text)
            self.overlay.set_state(DONE, "Copié")
        self._reset_later()

    def on_failure(self, short: str, detail: str) -> None:
        self.overlay.set_state(ERROR, short)
        self.notify(detail)
        self._reset_later(2800)

    def _reset_later(self, delay: int = 2200) -> None:
        QTimer.singleShot(delay, self._reset)

    def _reset(self) -> None:
        if self.overlay.state in (DONE, ERROR):
            self.overlay.set_state(IDLE)

    # ---------- settings ----------

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.cfg)
        if dialog.exec():
            self.cfg = dialog.values()
            config.save(self.cfg)
            log.info("settings saved (device=%r)", self.cfg.get("input_device"))
            if self.overlay.state == ERROR:
                self.overlay.set_state(IDLE)

    def quit(self) -> None:
        log.info("--- YanzVoice stop ---")
        if self.lock is not None:
            self.lock.close()
        connection.close()
        self.hotkey.stop()
        if self.recorder.is_recording:
            self.recorder.stop()
        self.tray.hide()
        self.app.quit()


def run() -> int:
    log.info("--- YanzVoice start ---")
    # Before any window exists, or Windows attributes them to pythonw.exe.
    branding.set_app_user_model_id()

    app = QApplication(sys.argv)
    app.setApplicationName(branding.APP_NAME)
    app.setApplicationDisplayName(branding.APP_NAME)
    app.setOrganizationName("Yanz")
    app.setWindowIcon(branding.icon())
    app.setQuitOnLastWindowClosed(False)

    # Claim the single-instance lock before building anything: a second
    # launch must not register a second global hotkey.
    lock = SingleInstance()
    if lock.try_signal_existing():
        return 0
    lock.listen()

    app.setFont(theme.font(theme.FIELD_SIZE))

    controller = YanzVoice(app, lock)
    if controller.hotkey.error:
        controller.overlay.set_state(ERROR, "Raccourci pris")
        controller.notify(
            f"Le raccourci {controller.hotkey.combo} n'a pas pu être enregistré : "
            f"{controller.hotkey.error}"
        )
    return app.exec()
