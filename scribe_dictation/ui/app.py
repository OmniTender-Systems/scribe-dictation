"""
PySide6 GUI application for scribe-dictation.

Main window with:
- Record/Stop toggle button
- Status bar (Idle / Recording... / Transcribing... / Done)
- Editable text display for transcribed output
- Copy to clipboard and Clear buttons
- Auto-paste after transcription (configurable)
- Global hotkey (Ctrl+Shift+D) to toggle recording from any app
- Settings dialog for microphone device, API key, and auto-paste toggle
- System tray icon with quick actions
- Ctrl+R keyboard shortcut to toggle recording
"""

import asyncio
import os
import sys
import threading
import time
from typing import Optional

import pyperclip
from PySide6.QtCore import Q_ARG, QMetaObject, QSettings, Qt, Slot
from PySide6.QtGui import QAction, QCloseEvent, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QStatusBar,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from scribe_dictation.audio.capture import AudioRecorder
from scribe_dictation.export import (
    Segment,
    TranscriptionResult,
    to_markdown,
    to_srt,
    to_txt,
)
from scribe_dictation.transcribe.service import TranscribeService

APP_NAME = "Scribe Dictation"
ORGANIZATION = "ScribeDictation"
SETTINGS_API_KEY = "api_key"
SETTINGS_DEVICE = "audio_device"
SETTINGS_AUTO_PASTE = "auto_paste"
SETTINGS_USE_LOCAL = "use_local"
SETTINGS_LOCAL_MODEL_SIZE = "local_model_size"

# ── Global hotkey support ─────────────────────────────────────────────

_global_hotkey_listener = None


def _ensure_custom_chimes():
    """Generate high-quality rising/falling swoop chirps in the temp directory."""
    import os
    import math
    import struct
    import wave
    import tempfile

    temp_dir = tempfile.gettempdir()
    start_path = os.path.join(temp_dir, "scribe_start.wav")
    stop_path = os.path.join(temp_dir, "scribe_stop.wav")

    # Generate chimes unconditionally on startup to ensure latest design
    sample_rate = 44100
    duration = 0.22  # 220ms swoop
    total_samples = int(duration * sample_rate)

    def generate_and_save(filepath, start_freq, end_freq):
        buffer = [0.0] * total_samples
        for i in range(total_samples):
            t = i / sample_rate
            # Linear frequency swoop glide phase
            phase = (
                2
                * math.pi
                * (start_freq * t + 0.5 * (end_freq - start_freq) * (t**2) / duration)
            )

            # Smooth cosine-like envelope: 40ms fade-in, 60ms fade-out
            fade_in = 0.04
            fade_out = 0.06
            if t < fade_in:
                env = t / fade_in
            elif t > (duration - fade_out):
                env = (duration - t) / fade_out
            else:
                env = 1.0

            # Soft pure sine wave chirp
            val = math.sin(phase) * env * 0.35
            buffer[i] = val

        try:
            with wave.open(filepath, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(sample_rate)
                for val in buffer:
                    val = max(-1.0, min(1.0, val))
                    sample = int(val * 32767)
                    wav_file.writeframesraw(struct.pack("<h", sample))
        except Exception:
            pass

    generate_and_save(start_path, start_freq=220.0, end_freq=360.0)  # Rising swoop
    generate_and_save(stop_path, start_freq=360.0, end_freq=220.0)  # Falling swoop


def _play_sound(start: bool):
    """Play a pleasant, custom generated chime to indicate start or end of recording."""
    try:
        import sys

        if sys.platform == "win32":
            import winsound
            import os
            import tempfile

            _ensure_custom_chimes()
            filename = "scribe_start.wav" if start else "scribe_stop.wav"
            filepath = os.path.join(tempfile.gettempdir(), filename)
            if os.path.exists(filepath):
                winsound.PlaySound(filepath, winsound.SND_FILENAME | winsound.SND_ASYNC)
    except Exception as e:
        print(f"Failed to play sound: {e}")


def _start_global_hotkey(press_callback, release_callback):
    """Start a background thread listening for global hotkey (press/release)."""
    global _global_hotkey_listener

    if _global_hotkey_listener is not None:
        return

    try:
        from pynput import keyboard
    except ImportError:
        return

    settings = QSettings(ORGANIZATION, APP_NAME)
    hotkey_type = settings.value("global_hotkey", "Ctrl + Win")

    current_keys = set()
    is_triggered = False

    def on_press(key):
        nonlocal is_triggered
        normalized_key = key
        if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
            normalized_key = keyboard.Key.ctrl
        elif key in (keyboard.Key.cmd_l, keyboard.Key.cmd_r):
            normalized_key = keyboard.Key.cmd
        elif key in (keyboard.Key.alt_l, keyboard.Key.alt_r):
            normalized_key = keyboard.Key.alt
        elif key in (keyboard.Key.shift_l, keyboard.Key.shift_r):
            normalized_key = keyboard.Key.shift

        current_keys.add(normalized_key)

        match = False
        if hotkey_type == "Ctrl + Win":
            match = (
                keyboard.Key.ctrl in current_keys and keyboard.Key.cmd in current_keys
            )
        elif hotkey_type == "Ctrl + Space":
            match = (
                keyboard.Key.ctrl in current_keys and keyboard.Key.space in current_keys
            )
        elif hotkey_type == "Caps Lock":
            match = key == keyboard.Key.caps_lock
        elif hotkey_type == "F1":
            match = key == keyboard.Key.f1

        if match:
            if not is_triggered:
                is_triggered = True
                if hasattr(press_callback, "__self__"):
                    from PySide6.QtCore import QMetaObject, Qt

                    QMetaObject.invokeMethod(
                        press_callback.__self__,
                        press_callback.__name__,
                        Qt.ConnectionType.QueuedConnection,
                    )
                else:
                    press_callback()

    def on_release(key):
        nonlocal is_triggered
        normalized_key = key
        if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
            normalized_key = keyboard.Key.ctrl
        elif key in (keyboard.Key.cmd_l, keyboard.Key.cmd_r):
            normalized_key = keyboard.Key.cmd
        elif key in (keyboard.Key.alt_l, keyboard.Key.alt_r):
            normalized_key = keyboard.Key.alt
        elif key in (keyboard.Key.shift_l, keyboard.Key.shift_r):
            normalized_key = keyboard.Key.shift

        try:
            current_keys.discard(normalized_key)
        except KeyError:
            pass

        release_match = False
        if hotkey_type == "Ctrl + Win":
            release_match = normalized_key in (keyboard.Key.ctrl, keyboard.Key.cmd)
        elif hotkey_type == "Ctrl + Space":
            release_match = normalized_key in (keyboard.Key.ctrl, keyboard.Key.space)
        elif hotkey_type == "Caps Lock":
            release_match = key == keyboard.Key.caps_lock
        elif hotkey_type == "F1":
            release_match = key == keyboard.Key.f1

        if release_match:
            if is_triggered:
                is_triggered = False
                if hasattr(release_callback, "__self__"):
                    from PySide6.QtCore import QMetaObject, Qt

                    QMetaObject.invokeMethod(
                        release_callback.__self__,
                        release_callback.__name__,
                        Qt.ConnectionType.QueuedConnection,
                    )
                else:
                    release_callback()

    _global_hotkey_listener = keyboard.Listener(
        on_press=on_press, on_release=on_release
    )
    _global_hotkey_listener.daemon = True
    _global_hotkey_listener.start()


def _stop_global_hotkey():
    """Stop the global hotkey listener."""
    global _global_hotkey_listener
    if _global_hotkey_listener is not None:
        _global_hotkey_listener.stop()
        _global_hotkey_listener = None


def _simulate_paste():
    """Simulate Ctrl+V (Windows) / Cmd+V (macOS) to paste into active window."""
    try:
        from pynput.keyboard import Controller, Key

        kb = Controller()
        mod = Key.cmd if sys.platform == "darwin" else Key.ctrl
        kb.press(mod)
        kb.press(KeyCode.from_vk(86))
        kb.release(KeyCode.from_vk(86))
        kb.release(mod)
    except Exception as e:
        print(f"Auto-paste failed: {e}")


def _copy_to_clipboard(text: str) -> bool:
    """Place ``text`` on the system clipboard.

    Uses PySide6's ``QGuiApplication.clipboard()`` (no extra dependency beyond
    the existing PySide6 requirement) and falls back to ``pyperclip`` if the Qt
    clipboard is unavailable. Returns ``True`` when the text was written.
    """
    try:
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
            return True
    except Exception as e:  # pragma: no cover - defensive, depends on platform
        print(f"Qt clipboard write failed: {e}")

    try:
        pyperclip.copy(text)
        return True
    except Exception as e:  # pragma: no cover - defensive, depends on platform
        print(f"pyperclip clipboard write failed: {e}")
        return False


try:
    from pynput.keyboard import KeyCode as _KC

    KeyCode = _KC
except ImportError:

    class KeyCode:
        @staticmethod
        def from_vk(vk):
            return None


# ── Settings Dialog ────────────────────────────────────────────────────


class SettingsDialog(QDialog):
    """Dialog for configuring application settings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} — Settings")
        self.setMinimumWidth(400)
        self.settings = QSettings(ORGANIZATION, APP_NAME)
        layout = QFormLayout(self)

        # Mode Selection
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Local Engine - Offline", "local")
        self.mode_combo.addItem("Cloud API - Online", "api")
        use_local_saved = self.settings.value(SETTINGS_USE_LOCAL, "true") == "true"
        self.mode_combo.setCurrentIndex(0 if use_local_saved else 1)
        self.mode_combo.currentIndexChanged.connect(self._toggle_mode_fields)
        layout.addRow("Transcription Mode:", self.mode_combo)

        # API Key (for API mode)
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText("sk-...")
        saved_key = self.settings.value(SETTINGS_API_KEY, "")
        if saved_key:
            self.api_key_input.setText(saved_key)
        layout.addRow("OpenAI API Key:", self.api_key_input)

        # Local Model Size (for Local mode)
        self.model_size_combo = QComboBox()
        for size in ["tiny", "base", "small", "medium", "large-v3"]:
            self.model_size_combo.addItem(size, size)
        saved_size = self.settings.value(SETTINGS_LOCAL_MODEL_SIZE, "base")
        self.model_size_combo.setCurrentText(saved_size)
        layout.addRow("Local Model Size:", self.model_size_combo)

        self.device_combo = QComboBox()
        self._populate_devices()
        layout.addRow("Microphone:", self.device_combo)

        self.auto_paste_check = QCheckBox("Auto-paste after transcription")
        self.auto_paste_check.setChecked(
            self.settings.value(SETTINGS_AUTO_PASTE, "true") == "true"
        )
        layout.addRow(self.auto_paste_check)

        # Global Hotkey Selection
        self.hotkey_combo = QComboBox()
        for hk in ["Ctrl + Win", "Ctrl + Space", "Caps Lock", "F1"]:
            self.hotkey_combo.addItem(hk, hk)
        saved_hotkey = self.settings.value("global_hotkey", "Ctrl + Win")
        self.hotkey_combo.setCurrentText(saved_hotkey)
        layout.addRow("Global Hotkey:", self.hotkey_combo)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._save)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)

        # Labels for toggling visibility
        self.api_key_label = layout.labelForField(self.api_key_input)
        self.model_size_label = layout.labelForField(self.model_size_combo)

        self._toggle_mode_fields()

    def _toggle_mode_fields(self):
        is_local = self.mode_combo.currentData() == "local"
        self.api_key_input.setVisible(not is_local)
        if self.api_key_label:
            self.api_key_label.setVisible(not is_local)
        self.model_size_combo.setVisible(is_local)
        if self.model_size_label:
            self.model_size_label.setVisible(is_local)

    def _populate_devices(self):
        import sounddevice as sd

        saved_device = self.settings.value(SETTINGS_DEVICE, "")
        self.device_combo.addItem("Default", None)
        try:
            devices = sd.query_devices()
            for i, dev in enumerate(devices):
                if dev["max_input_channels"] > 0:
                    label = f"{dev['name']} (API: {dev['hostapi']})"
                    self.device_combo.addItem(label, i)
                    if saved_device and (
                        str(i) == saved_device or dev["name"] == saved_device
                    ):
                        self.device_combo.setCurrentIndex(self.device_combo.count() - 1)
        except Exception:
            pass

    def _save(self):
        use_local = self.mode_combo.currentData() == "local"
        self.settings.setValue(SETTINGS_USE_LOCAL, "true" if use_local else "false")
        self.settings.setValue(SETTINGS_API_KEY, self.api_key_input.text())
        self.settings.setValue(
            SETTINGS_LOCAL_MODEL_SIZE, self.model_size_combo.currentData()
        )

        device_id = self.device_combo.currentData()
        self.settings.setValue(
            SETTINGS_DEVICE, str(device_id) if device_id is not None else ""
        )
        self.settings.setValue(
            SETTINGS_AUTO_PASTE,
            "true" if self.auto_paste_check.isChecked() else "false",
        )
        self.settings.setValue("global_hotkey", self.hotkey_combo.currentText())
        self.accept()


class ScribeDictationWindow(QMainWindow):
    """Main application window for Scribe Dictation."""

    STATUS_IDLE = "Idle"
    STATUS_RECORDING = "Recording...  (Ctrl+Win to stop)"
    STATUS_TRANSCRIBING = "Transcribing..."
    STATUS_DONE = "Done"

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(480, 360)

        # Set Window Icon
        from PySide6.QtGui import QIcon

        icon_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "resources", "icon.ico"
        )
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.settings = QSettings(ORGANIZATION, APP_NAME)
        self._recorder: Optional[AudioRecorder] = None
        self._transcriber: Optional[TranscribeService] = None

        # Segments accumulated across recordings in this session, used for
        # Export. Each recording becomes one timestamped segment, with start
        # measured from the first recording in the session.
        self._session_started_at: Optional[float] = None
        self._segments: list = []
        self._recording_started_at: Optional[float] = None

        self._setup_ui()
        self._setup_shortcuts()
        self._setup_global_hotkey()
        self._setup_tray()
        self._setup_transcriber()
        self._update_hotkey_label()
        self._update_status(self.STATUS_IDLE)

    # ── UI Setup ──────────────────────────────────────────────────────

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Text display area
        self.text_display = QPlainTextEdit()
        self.text_display.setPlaceholderText("Transcribed text will appear here...")
        self.text_display.setMinimumHeight(180)
        layout.addWidget(self.text_display)

        # Button row
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.record_btn = QPushButton("\U0001f3a4 Record")
        self.record_btn.setMinimumHeight(40)
        self.record_btn.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.record_btn.clicked.connect(self._toggle_recording)
        btn_layout.addWidget(self.record_btn)

        self.copy_btn = QPushButton("\U0001f4cb Copy")
        self.copy_btn.clicked.connect(self._copy_to_clipboard_action)
        btn_layout.addWidget(self.copy_btn)

        self.clear_btn = QPushButton("\U0001f5d1 Clear")
        self.clear_btn.clicked.connect(self._clear_text)
        btn_layout.addWidget(self.clear_btn)

        layout.addLayout(btn_layout)

        # Hotkey Help Label
        from PySide6.QtWidgets import QLabel

        self.hotkey_label = QLabel()
        self.hotkey_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hotkey_label.setStyleSheet("color: #718096; font-size: 11px;")
        layout.addWidget(self.hotkey_label)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # Menu bar
        self._setup_menu()

    def _setup_menu(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&File")

        settings_action = QAction("&Settings...", self)
        settings_action.setShortcut(QKeySequence("Ctrl+,"))
        settings_action.triggered.connect(self._open_settings)
        file_menu.addAction(settings_action)

        file_menu.addSeparator()

        export_action = QAction("&Export...", self)
        export_action.setShortcut(QKeySequence("Ctrl+E"))
        export_action.triggered.connect(self._export_transcription)
        file_menu.addAction(export_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        help_menu = menu_bar.addMenu("&Help")
        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

        help_menu.addSeparator()
        deactivate_action = QAction("Deactivate &Pro License...", self)
        deactivate_action.triggered.connect(self._deactivate_license)
        help_menu.addAction(deactivate_action)

    def _deactivate_license(self):
        reply = QMessageBox.question(
            self,
            "Deactivate License",
            "Are you sure you want to deactivate your Pro license on this computer? The app will close.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            from scribe_dictation.licensing import deactivate_license

            deactivate_license()
            self.close()

    def _setup_shortcuts(self):
        shortcut = QShortcut(QKeySequence("Ctrl+R"), self)
        shortcut.activated.connect(self._toggle_recording)

    def _setup_global_hotkey(self):
        """Register system-wide hotkey."""
        self._recording_mode = None
        self._last_hotkey_press_time = 0.0
        _start_global_hotkey(
            self._on_global_hotkey_pressed, self._on_global_hotkey_released
        )

    def _update_hotkey_label(self):
        hotkey = self.settings.value("global_hotkey", "Ctrl + Win")
        self.hotkey_label.setText(
            f"Global Hotkey: Hold <b>{hotkey}</b> to record, release to paste"
        )

    @Slot()
    def _on_global_hotkey_pressed(self):
        import time

        self._last_hotkey_press_time = time.time()

        if self._recorder and self._recorder.is_recording:
            self._stop_recording()
            self._recording_mode = None
        else:
            self._recording_mode = "HOLD"
            self._start_recording()

    @Slot()
    def _on_global_hotkey_released(self):
        import time

        if hasattr(self, "_recording_mode") and self._recording_mode == "HOLD":
            duration = time.time() - getattr(self, "_last_hotkey_press_time", 0.0)
            if duration >= 0.4:
                # Held down and released -> stop recording
                self._stop_recording()
                self._recording_mode = None
            else:
                # Short tap -> lock recording on
                self._recording_mode = "LOCK"

    def _setup_tray(self):
        """Create a system tray icon with quick actions."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        self.tray_icon = QSystemTrayIcon(self)
        from PySide6.QtGui import QIcon

        icon_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "resources", "icon.ico"
        )
        if os.path.exists(icon_path):
            self.tray_icon.setIcon(QIcon(icon_path))
        else:
            self.tray_icon.setIcon(
                self.style().standardIcon(self.style().StandardPixmap.SP_ComputerIcon)
            )
        self.tray_icon.setToolTip(APP_NAME)

        from PySide6.QtWidgets import QMenu

        menu = QMenu()

        toggle_action = menu.addAction("Toggle Recording")
        toggle_action.triggered.connect(self._toggle_recording)

        menu.addSeparator()

        show_action = menu.addAction("Show Window")
        show_action.triggered.connect(self.show)

        settings_action = menu.addAction("Settings...")
        settings_action.triggered.connect(self._open_settings)

        menu.addSeparator()

        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(self.close)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show()
            self.raise_()

    def _setup_transcriber(self):
        """Initialize the transcription service from settings or env."""
        use_local = self.settings.value(SETTINGS_USE_LOCAL, "true") == "true"
        local_model_size = self.settings.value(SETTINGS_LOCAL_MODEL_SIZE, "base")
        api_key = self.settings.value(SETTINGS_API_KEY, "") or os.environ.get(
            "OPENAI_API_KEY", ""
        )

        try:
            self._transcriber = TranscribeService(
                api_key=api_key, use_local=use_local, local_model_size=local_model_size
            )
        except Exception as e:
            print(f"Failed to setup transcriber: {e}")
            self._transcriber = None

    # ── Status ────────────────────────────────────────────────────────

    def _update_status(self, text: str):
        self.status_bar.showMessage(text)

    # ── Recording ─────────────────────────────────────────────────────

    def _toggle_recording(self):
        if self._recorder and self._recorder.is_recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        _play_sound(True)
        device_str = self.settings.value(SETTINGS_DEVICE, "")
        device = int(device_str) if device_str and device_str != "None" else None

        if self._session_started_at is None:
            self._session_started_at = time.monotonic()
        self._recording_started_at = time.monotonic()

        self._recorder = AudioRecorder(device=device)
        self._recorder.start()

        self.record_btn.setText("\u23f9 Stop")
        self._update_status(self.STATUS_RECORDING)

        # Start silence-detection thread
        self._silence_thread = threading.Thread(
            target=self._auto_stop_loop, daemon=True
        )
        self._silence_thread.start()

    def _auto_stop_loop(self):
        """Monitor recording for silence and auto-stop after 1.5s."""
        import time
        import numpy as np

        silence_duration = 1.5
        block_duration = 0.1
        blocks_for_silence = int(silence_duration / block_duration)
        silent_blocks = 0

        while self._recorder and self._recorder.is_recording:
            time.sleep(block_duration)
            with self._recorder._lock:
                if not self._recorder._recording:
                    continue
                latest = self._recorder._recording[-1]
                level = float(np.sqrt(np.mean(latest**2))) if latest.size > 0 else 0.0

            if level < 0.01:  # SILENCE_THRESHOLD
                silent_blocks += 1
                if silent_blocks >= blocks_for_silence:
                    QMetaObject.invokeMethod(
                        self, "_stop_recording", Qt.ConnectionType.QueuedConnection
                    )
                    break
            else:
                silent_blocks = 0

    def _stop_recording(self):
        if not self._recorder or not self._recorder.is_recording:
            return

        _play_sound(False)
        self._recording_mode = None

        try:
            wav_path = self._recorder.stop()
        except RuntimeError:
            self._reset_recording_ui()
            return

        self._reset_recording_ui()
        self._transcribe_async(wav_path)

    def _reset_recording_ui(self):
        self.record_btn.setText("\U0001f3a4 Record")

    # ── Transcription ─────────────────────────────────────────────────

    def _transcribe_async(self, wav_path: str):
        self._update_status(self.STATUS_TRANSCRIBING)

        if self._transcriber is None:
            self._setup_transcriber()
            if self._transcriber is None:
                self.text_display.appendPlainText(
                    "[Transcription failed: No API key configured. "
                    "Set OPENAI_API_KEY environment variable or configure in Settings.]"
                )
                self._update_status(self.STATUS_IDLE)
                return

        def run_transcribe():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(self._transcriber.transcribe(wav_path))
                loop.close()
            except Exception as e:
                result = f"[Transcription error: {e}]"

            QMetaObject.invokeMethod(
                self,
                "_on_transcription_complete",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(str, result),
            )

        thread = threading.Thread(target=run_transcribe, daemon=True)
        thread.start()

    @Slot(str)
    def _on_transcription_complete(self, text: str):
        self.text_display.appendPlainText(text)
        self._update_status(self.STATUS_DONE)

        # Record this recording as a timestamped segment (relative to the
        # start of the session) so it can be included in Export output.
        if text.strip():
            now = time.monotonic()
            session_start = self._session_started_at or now
            seg_start = (self._recording_started_at or now) - session_start
            seg_end = now - session_start
            self._segments.append(
                Segment(
                    start=max(seg_start, 0.0),
                    end=max(seg_end, seg_start, 0.0),
                    text=text,
                )
            )

        # Always place the result on the clipboard so the user can paste with
        # Ctrl+V even when automatic pasting is disabled.
        if text.strip():
            _copy_to_clipboard(text)

            # Auto-paste (simulate Ctrl+V into the previously-active window) is
            # an optional, toggleable behaviour gated by the "auto_paste" setting.
            auto_paste = self.settings.value(SETTINGS_AUTO_PASTE, "true") == "true"
            if auto_paste:
                from PySide6.QtCore import QTimer

                QTimer.singleShot(200, _simulate_paste)

    # ── Actions ───────────────────────────────────────────────────────

    def _copy_to_clipboard_action(self):
        text = self.text_display.toPlainText()
        if text.strip():
            _copy_to_clipboard(text)
            self._update_status("Copied!")

    def _clear_text(self):
        self.text_display.clear()
        self._segments = []
        self._session_started_at = None
        self._update_status(self.STATUS_IDLE)

    def _export_transcription(self):
        """Export the current transcription to .txt, .md, or .srt."""
        segments = list(self._segments)
        if not segments:
            # Fall back to whatever plain text is on screen (e.g. manually
            # edited), as a single zero-length segment, so Export still
            # works even if no recording has completed in this session.
            text = self.text_display.toPlainText()
            if not text.strip():
                QMessageBox.information(self, "Export", "Nothing to export yet.")
                return
            segments = [Segment(start=0.0, end=0.0, text=text)]

        result = TranscriptionResult(segments=segments)

        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Transcription",
            "transcription.txt",
            "Plain Text (*.txt);;Markdown (*.md);;SubRip Subtitle (*.srt)",
        )
        if not path:
            return

        if path.endswith(".md") or "Markdown" in selected_filter:
            content = to_markdown(result)
        elif path.endswith(".srt") or "SubRip" in selected_filter:
            content = to_srt(result)
        else:
            content = to_txt(result)

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            self._update_status(f"Exported to {path}")
        except OSError as e:
            QMessageBox.warning(self, "Export failed", f"Could not write file:\n{e}")

    def _open_settings(self):
        dialog = SettingsDialog(self)
        if dialog.exec():
            self._setup_transcriber()
            _stop_global_hotkey()
            self._setup_global_hotkey()
            self._update_hotkey_label()

    def _show_about(self):
        QMessageBox.about(
            self,
            f"About {APP_NAME}",
            f"<b>{APP_NAME}</b><br><br>"
            f"Version 0.2.0<br><br>"
            f"A desktop dictation app supporting local offline processing and OpenAI cloud API.<br><br>"
            f"Press <b>Ctrl+R</b> or the global shortcut to start/stop recording.<br>"
            f"Auto-paste is configurable in Settings.",
        )

    def closeEvent(self, event: QCloseEvent):
        if self._recorder and self._recorder.is_recording:
            try:
                self._recorder.stop()
            except RuntimeError:
                pass
        _stop_global_hotkey()
        event.accept()


def main():
    """Launch the Scribe Dictation application."""
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORGANIZATION)

    # ── Licensing check ──
    from scribe_dictation.licensing import is_offline_cache_valid
    from scribe_dictation.ui.activation import ActivationDialog

    if not is_offline_cache_valid():
        activation = ActivationDialog()
        if activation.exec() != QDialog.DialogCode.Accepted:
            sys.exit(0)

    window = ScribeDictationWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
