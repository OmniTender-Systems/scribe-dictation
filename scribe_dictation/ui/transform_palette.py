"""Global 'Transform Selected Text' Quick Action Palette for Privacy Scribe Pro.

A modern, sleek floating action palette (frameless, acrylic rounded theme)
that grabs selected text via simulated Ctrl+C, presents quick AI transformation
actions (Clean & Fix Grammar, Markdown Bullets, Professional Email, Executive
Summary, Translate to English, Custom AI Instruction), transforms the text in
the background with FormatEngine and dynamic progress animation, and automatically
pastes the transformed result back into the target application window.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from typing import List, Optional

import pyperclip
from PySide6.QtCore import (
    QPoint,
    QRectF,
    QThread,
    QTimer,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QFont,
    QGuiApplication,
    QKeyEvent,
    QLinearGradient,
    QPainter,
    QPainterPath,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from scribe_dictation.formatters.modes import FormatEngine


# ── Action Definition ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TransformActionItem:
    """Metadata for a palette transformation action."""

    id: str
    label: str
    icon: str
    description: str
    shortcut_hint: str = ""


DEFAULT_TRANSFORM_ACTIONS: List[TransformActionItem] = [
    TransformActionItem(
        id="clean",
        label="Clean & Fix Grammar",
        icon="✍️",
        description="Fix grammar, typos, and improve sentence clarity.",
        shortcut_hint="1",
    ),
    TransformActionItem(
        id="bullets",
        label="Format as Markdown Bullets",
        icon="📋",
        description="Convert selected text into crisp bullet points.",
        shortcut_hint="2",
    ),
    TransformActionItem(
        id="email",
        label="Professional Email Rewrite",
        icon="✉️",
        description="Draft a polite, professional email from thoughts.",
        shortcut_hint="3",
    ),
    TransformActionItem(
        id="summary",
        label="Executive Summary",
        icon="📝",
        description="Generate concise summary with key takeaways.",
        shortcut_hint="4",
    ),
    TransformActionItem(
        id="translate_en",
        label="Translate to English",
        icon="🌐",
        description="Translate text into fluent, natural English.",
        shortcut_hint="5",
    ),
]


# ── Clipboard Simulation Helpers ──────────────────────────────────────────────


def _simulate_copy(target_hwnd: Optional[int] = None) -> None:
    """Simulate atomic Ctrl+C (Windows/Linux) / Cmd+C (macOS) to copy highlighted text."""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            INPUT_KEYBOARD = 1
            KEYEVENTF_KEYUP = 0x0002

            VK_SHIFT = 0x10
            VK_CONTROL = 0x11
            VK_MENU = 0x12  # Alt
            VK_LWIN = 0x5B
            VK_RWIN = 0x5C
            VK_C = 0x43

            class KEYBDINPUT(ctypes.Structure):
                _fields_ = [
                    ("wVk", wintypes.WORD),
                    ("wScan", wintypes.WORD),
                    ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
                ]

            class _INPUT_UNION(ctypes.Union):
                _fields_ = [("ki", KEYBDINPUT)]

            class INPUT(ctypes.Structure):
                _fields_ = [
                    ("type", wintypes.DWORD),
                    ("u", _INPUT_UNION),
                ]

            def make_key_input(vk: int, flags: int) -> INPUT:
                inp = INPUT()
                inp.type = INPUT_KEYBOARD
                inp.u.ki.wVk = vk
                inp.u.ki.wScan = 0
                inp.u.ki.dwFlags = flags
                inp.u.ki.time = 0
                inp.u.ki.dwExtraInfo = None
                return inp

            if target_hwnd and user32.IsWindow(target_hwnd):
                user32.SetForegroundWindow(target_hwnd)
                user32.BringWindowToTop(target_hwnd)
                time.sleep(0.04)

            # Clear modifier keys
            release_mods = [
                make_key_input(VK_SHIFT, KEYEVENTF_KEYUP),
                make_key_input(VK_CONTROL, KEYEVENTF_KEYUP),
                make_key_input(VK_MENU, KEYEVENTF_KEYUP),
                make_key_input(VK_LWIN, KEYEVENTF_KEYUP),
                make_key_input(VK_RWIN, KEYEVENTF_KEYUP),
            ]
            mod_array = (INPUT * len(release_mods))(*release_mods)
            user32.SendInput(len(release_mods), mod_array, ctypes.sizeof(INPUT))
            time.sleep(0.02)

            # Fire Ctrl+C
            copy_seq = [
                make_key_input(VK_CONTROL, 0),
                make_key_input(VK_C, 0),
                make_key_input(VK_C, KEYEVENTF_KEYUP),
                make_key_input(VK_CONTROL, KEYEVENTF_KEYUP),
            ]
            copy_array = (INPUT * len(copy_seq))(*copy_seq)
            user32.SendInput(len(copy_seq), copy_array, ctypes.sizeof(INPUT))
            return
        except Exception as e:
            print(f"Win32 SendInput copy failed: {e}")

    try:
        from pynput.keyboard import Controller, Key

        kb = Controller()
        mod = Key.cmd if sys.platform == "darwin" else Key.ctrl
        kb.press(mod)
        kb.press("c")
        time.sleep(0.02)
        kb.release("c")
        kb.release(mod)
    except Exception as e:
        print(f"pynput copy simulation failed: {e}")


def _restore_window_focus(target_hwnd: int) -> bool:
    """Forcefully restore focus to a target HWND on Windows, bypassing OS foreground lock restrictions."""
    if not target_hwnd or sys.platform != "win32":
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        if not user32.IsWindow(target_hwnd):
            return False

        fg_hwnd = user32.GetForegroundWindow()
        if fg_hwnd == target_hwnd:
            return True

        current_thread_id = kernel32.GetCurrentThreadId()
        target_thread_id = user32.GetWindowThreadProcessId(target_hwnd, None)
        fg_thread_id = user32.GetWindowThreadProcessId(fg_hwnd, None) if fg_hwnd else 0

        attached_target = False
        attached_fg = False
        if target_thread_id and target_thread_id != current_thread_id:
            attached_target = bool(
                user32.AttachThreadInput(current_thread_id, target_thread_id, True)
            )
        if (
            fg_thread_id
            and fg_thread_id != current_thread_id
            and fg_thread_id != target_thread_id
        ):
            attached_fg = bool(
                user32.AttachThreadInput(current_thread_id, fg_thread_id, True)
            )

        VK_MENU = 0x12
        KEYEVENTF_KEYUP = 0x0002
        user32.keybd_event(VK_MENU, 0, 0, 0)
        user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)

        SW_RESTORE = 9
        if user32.IsIconic(target_hwnd):
            user32.ShowWindow(target_hwnd, SW_RESTORE)

        user32.BringWindowToTop(target_hwnd)
        user32.SetForegroundWindow(target_hwnd)
        user32.SetFocus(target_hwnd)

        if attached_target:
            user32.AttachThreadInput(current_thread_id, target_thread_id, False)
        if attached_fg:
            user32.AttachThreadInput(current_thread_id, fg_thread_id, False)

        return True
    except Exception as e:
        print(f"Failed to restore window focus: {e}")
        return False


def _simulate_paste(target_hwnd: Optional[int] = None) -> None:
    """Simulate atomic Ctrl+V (Windows/Linux) / Cmd+V (macOS) to paste into active window."""
    if sys.platform == "win32":
        try:
            import ctypes

            user32 = ctypes.windll.user32

            if target_hwnd:
                _restore_window_focus(target_hwnd)
                time.sleep(0.08)

            VK_SHIFT = 0x10
            VK_CONTROL = 0x11
            VK_MENU = 0x12  # Alt
            VK_LWIN = 0x5B
            VK_RWIN = 0x5C
            VK_V = 0x56
            KEYEVENTF_KEYUP = 0x0002

            # 1. Release modifier keys
            for vk in (VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN):
                user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
            time.sleep(0.02)

            # 2. Fire clean Ctrl+V down and up sequence
            user32.keybd_event(VK_CONTROL, 0, 0, 0)
            time.sleep(0.01)
            user32.keybd_event(VK_V, 0, 0, 0)
            time.sleep(0.02)
            user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
            time.sleep(0.01)
            user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
            return
        except Exception as e:
            print(f"Win32 keybd_event paste failed: {e}")

    try:
        from pynput.keyboard import Controller, Key

        kb = Controller()
        mod = Key.cmd if sys.platform == "darwin" else Key.ctrl
        kb.press(mod)
        kb.press("v")
        time.sleep(0.02)
        kb.release("v")
        kb.release(mod)
    except Exception as e:
        print(f"pynput paste simulation failed: {e}")


def _copy_to_clipboard(text: str) -> bool:
    """Place ``text`` onto system clipboard using Qt or pyperclip."""
    try:
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
            return True
    except Exception as e:
        print(f"Qt clipboard write failed: {e}")

    try:
        pyperclip.copy(text)
        return True
    except Exception as e:
        print(f"pyperclip write failed: {e}")
        return False


def grab_selected_text(target_hwnd: Optional[int] = None, timeout: float = 0.25) -> str:
    """Grab highlighted/selected text from the active window via simulated Ctrl+C."""
    old_clip = ""
    try:
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            old_clip = clipboard.text()
    except Exception:
        try:
            old_clip = pyperclip.paste()
        except Exception:
            old_clip = ""

    # Clear clipboard temporarily to reliably detect copy event
    try:
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.clear()
    except Exception:
        pass

    _simulate_copy(target_hwnd)

    start_time = time.monotonic()
    while time.monotonic() - start_time < timeout:
        time.sleep(0.025)
        try:
            clipboard = QGuiApplication.clipboard()
            if clipboard is not None:
                new_text = clipboard.text()
                if new_text and new_text != old_clip:
                    return new_text
            new_text = pyperclip.paste()
            if new_text and new_text != old_clip:
                return new_text
        except Exception:
            pass

    # Fallback to whatever is in clipboard
    try:
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None and clipboard.text():
            return clipboard.text()
        return pyperclip.paste() or old_clip or ""
    except Exception:
        return old_clip or ""


# ── Background Worker ─────────────────────────────────────────────────────────


class TransformWorker(QThread):
    """Background worker thread to execute FormatEngine transformation non-blockingly."""

    transformed = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        format_engine: FormatEngine,
        text: str,
        action: str,
        custom_instruction: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.format_engine = format_engine
        self.text = text
        self.action = action
        self.custom_instruction = custom_instruction

    def run(self) -> None:
        try:
            result = self.format_engine.transform(
                self.text,
                action=self.action,
                custom_instruction=self.custom_instruction,
                use_llm=True,
            )
            self.transformed.emit(result)
        except Exception as e:
            self.failed.emit(str(e))


# ── Shimmer & Progress Indicator ──────────────────────────────────────────────


class ShimmerProgressBar(QWidget):
    """A sleek glowing gradient shimmer bar indicating active AI processing."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(6)
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step)
        self._timer.setInterval(20)
        self.hide()

    def start(self) -> None:
        self._phase = 0.0
        self.show()
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def _step(self) -> None:
        self._phase = (self._phase + 0.04) % 1.0
        self.update()

    def paintEvent(self, event) -> None:
        if not self.isVisible():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = float(self.width()), float(self.height())
        radius = h / 2.0

        bg_path = QPainterPath()
        bg_path.addRoundedRect(QRectF(0, 0, w, h), radius, radius)
        painter.fillPath(bg_path, QColor(30, 41, 59, 180))

        # Moving gradient highlight
        x_center = self._phase * (w + 120) - 60
        grad = QLinearGradient(x_center - 60, 0, x_center + 60, 0)
        grad.setColorAt(0.0, QColor(99, 102, 241, 0))
        grad.setColorAt(0.5, QColor(192, 132, 252, 255))
        grad.setColorAt(1.0, QColor(59, 130, 246, 0))

        painter.fillPath(bg_path, QBrush(grad))


# ── Action Button Component ───────────────────────────────────────────────────


class ActionButton(QPushButton):
    """A customized sleek dark button with icon, label, and hover highlight."""

    def __init__(
        self,
        item: TransformActionItem,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.item = item
        self.setText(f"{item.icon}  {item.label}")
        self.setToolTip(item.description)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(36)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #f1f5f9;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 6px 12px;
                font-family: 'Segoe UI', system-ui, sans-serif;
                font-size: 12px;
                font-weight: 500;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #334155;
                border-color: #6366f1;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #0f172a;
                border-color: #818cf8;
            }
            QPushButton:disabled {
                background-color: #0f172a;
                border-color: #1e293b;
                color: #475569;
            }
        """)


# ── Transform Palette Main Widget ─────────────────────────────────────────────


class TransformPalette(QWidget):
    """Modern floating Quick Action Palette for selected text transformations."""

    transformed = Signal(str)
    dismissed = Signal()

    def __init__(
        self,
        format_engine: Optional[FormatEngine] = None,
        target_hwnd: Optional[int] = None,
        initial_text: str = "",
        is_pro: bool = True,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.format_engine = format_engine or FormatEngine()
        self.target_hwnd = target_hwnd
        self.is_pro = is_pro
        self._worker: Optional[TransformWorker] = None
        self._is_transforming = False
        self._drag_pos: Optional[QPoint] = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        self.setFixedWidth(440)
        self._setup_ui()
        if initial_text:
            self.set_text(initial_text)

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(0)

        # ── Root Card Container with Rounded Acrylic styling ──
        self.card = QFrame(self)
        self.card.setObjectName("PaletteCard")
        self.card.setStyleSheet("""
            QFrame#PaletteCard {
                background-color: #0f172a;
                border: 1px solid #334155;
                border-radius: 14px;
            }
        """)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(14, 12, 14, 14)
        card_layout.setSpacing(10)

        # ── Header Row ──
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        title_icon = QLabel("✨")
        title_icon.setStyleSheet("font-size: 15px;")
        header_layout.addWidget(title_icon)

        title_label = QLabel("Transform Selected Text")
        title_label.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        title_label.setStyleSheet("color: #f8fafc;")
        header_layout.addWidget(title_label)

        if self.is_pro:
            pro_badge = QLabel("PRO")
            pro_badge.setStyleSheet("""
                background-color: #4f46e5;
                color: #ffffff;
                font-size: 9px;
                font-weight: bold;
                padding: 2px 6px;
                border-radius: 4px;
            """)
            header_layout.addWidget(pro_badge)

        header_layout.addStretch()

        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #94a3b8;
                border: none;
                font-size: 13px;
                font-weight: bold;
                border-radius: 12px;
            }
            QPushButton:hover {
                background-color: #334155;
                color: #ef4444;
            }
        """)
        self.close_btn.clicked.connect(self.dismiss)
        header_layout.addWidget(self.close_btn)

        card_layout.addLayout(header_layout)

        # ── Source Text Preview / Editor ──
        self.text_preview = QPlainTextEdit()
        self.text_preview.setPlaceholderText(
            "Selected text will appear here (or type / paste here)..."
        )
        self.text_preview.setMaximumHeight(85)
        self.text_preview.setStyleSheet("""
            QPlainTextEdit {
                background-color: #020617;
                color: #cbd5e1;
                border: 1px solid #1e293b;
                border-radius: 8px;
                padding: 6px 8px;
                font-family: 'Segoe UI', system-ui, sans-serif;
                font-size: 11px;
            }
            QPlainTextEdit:focus {
                border-color: #6366f1;
            }
        """)
        card_layout.addWidget(self.text_preview)

        # ── Shimmer Progress Bar ──
        self.shimmer_bar = ShimmerProgressBar(self)
        card_layout.addWidget(self.shimmer_bar)

        # ── Action Buttons ──
        self.action_buttons: List[ActionButton] = []
        buttons_layout = QVBoxLayout()
        buttons_layout.setSpacing(6)

        for item in DEFAULT_TRANSFORM_ACTIONS:
            btn = ActionButton(item, self)
            btn.clicked.connect(
                lambda checked=False, a_id=item.id: self.execute_transform(a_id)
            )
            self.action_buttons.append(btn)
            buttons_layout.addWidget(btn)

        card_layout.addLayout(buttons_layout)

        # ── Custom AI Instruction Row ──
        custom_layout = QHBoxLayout()
        custom_layout.setSpacing(6)

        self.custom_input = QLineEdit()
        self.custom_input.setPlaceholderText(
            "💬 Custom AI instruction (e.g. 'Make concise')..."
        )
        self.custom_input.setStyleSheet("""
            QLineEdit {
                background-color: #020617;
                color: #f1f5f9;
                border: 1px solid #1e293b;
                border-radius: 8px;
                padding: 6px 10px;
                font-family: 'Segoe UI', system-ui, sans-serif;
                font-size: 11px;
            }
            QLineEdit:focus {
                border-color: #8b5cf6;
            }
        """)
        self.custom_input.returnPressed.connect(self._on_custom_transform)
        custom_layout.addWidget(self.custom_input)

        self.custom_btn = QPushButton("Transform")
        self.custom_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.custom_btn.setFixedHeight(30)
        self.custom_btn.setStyleSheet("""
            QPushButton {
                background-color: #6366f1;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 4px 12px;
                font-weight: 600;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #4f46e5;
            }
            QPushButton:pressed {
                background-color: #4338ca;
            }
            QPushButton:disabled {
                background-color: #1e293b;
                color: #475569;
            }
        """)
        self.custom_btn.clicked.connect(self._on_custom_transform)
        custom_layout.addWidget(self.custom_btn)

        card_layout.addLayout(custom_layout)

        # ── Status & Feedback Label ──
        self.status_label = QLabel("Select an action above or press Esc to cancel")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: #64748b; font-size: 10px;")
        card_layout.addWidget(self.status_label)

        main_layout.addWidget(self.card)

    # ── Text Management & Positioning ─────────────────────────────────────────

    def set_text(self, text: str) -> None:
        """Set the text to be transformed."""
        self.text_preview.setPlainText(text or "")

    def get_text(self) -> str:
        """Retrieve the current text in the preview box."""
        return self.text_preview.toPlainText().strip()

    def set_target_hwnd(self, hwnd: Optional[int]) -> None:
        """Set the target window handle to paste into upon completion."""
        self.target_hwnd = hwnd

    def position_near_cursor(self) -> None:
        """Position the palette near mouse cursor with screen boundary clamping."""
        cursor_pos = QCursor.pos()
        screen = QGuiApplication.screenAt(cursor_pos) or QGuiApplication.primaryScreen()
        if not screen:
            self.show()
            return

        screen_geom = screen.availableGeometry()
        w = self.width()
        h = self.sizeHint().height() or 380

        # Center slightly below/right of cursor
        x = cursor_pos.x() - (w // 2)
        y = cursor_pos.y() - 40

        # Screen boundary clamping
        x = max(screen_geom.left() + 10, min(x, screen_geom.right() - w - 10))
        y = max(screen_geom.top() + 10, min(y, screen_geom.bottom() - h - 10))

        self.move(x, y)

    def position_center_screen(self) -> None:
        """Position the palette in center of active screen."""
        screen = QGuiApplication.primaryScreen()
        if not screen:
            self.show()
            return

        screen_geom = screen.availableGeometry()
        x = screen_geom.x() + (screen_geom.width() - self.width()) // 2
        y = screen_geom.y() + (screen_geom.height() - self.sizeHint().height()) // 2
        self.move(x, y)

    # ── Action Execution & UI State ───────────────────────────────────────────

    def _on_custom_transform(self) -> None:
        instruction = self.custom_input.text().strip()
        self.execute_transform(action="custom", custom_instruction=instruction)

    def execute_transform(
        self,
        action: str,
        custom_instruction: str = "",
        target_text: Optional[str] = None,
    ) -> None:
        """Execute text transformation asynchronously."""
        if self._is_transforming:
            return

        text = target_text if target_text is not None else self.get_text()
        if not text:
            self.status_label.setText("⚠️ Please select or enter text to transform.")
            self.status_label.setStyleSheet("color: #f59e0b; font-size: 10px;")
            return

        self._set_transforming_state(True)
        self.status_label.setText("✨ Transforming text with AI...")
        self.status_label.setStyleSheet(
            "color: #c084fc; font-size: 10px; font-weight: 500;"
        )

        self._worker = TransformWorker(
            format_engine=self.format_engine,
            text=text,
            action=action,
            custom_instruction=custom_instruction,
            parent=self,
        )
        self._worker.transformed.connect(self._on_transform_complete)
        self._worker.failed.connect(self._on_transform_error)
        self._worker.start()

    def _set_transforming_state(self, active: bool) -> None:
        self._is_transforming = active
        for btn in self.action_buttons:
            btn.setEnabled(not active)
        self.custom_btn.setEnabled(not active)
        self.custom_input.setEnabled(not active)
        self.text_preview.setReadOnly(active)

        if active:
            self.shimmer_bar.start()
        else:
            self.shimmer_bar.stop()

    @Slot(str)
    def _on_transform_complete(self, result: str) -> None:
        """Handle successful transformation: copy, auto-paste, notify, and close."""
        self._set_transforming_state(False)
        self.status_label.setText("✓ Pasted to active window")
        self.status_label.setStyleSheet(
            "color: #4ade80; font-size: 10px; font-weight: bold;"
        )

        # 1. Place transformed text onto clipboard
        _copy_to_clipboard(result)

        # 2. Emit signal with result
        self.transformed.emit(result)

        # 3. Simulate paste back into target application
        if self.target_hwnd:
            _simulate_paste(self.target_hwnd)
        else:
            _simulate_paste()

        # 4. Hide / close palette
        QTimer.singleShot(350, self.dismiss)

    @Slot(str)
    def _on_transform_error(self, error_msg: str) -> None:
        """Handle transformation failure gracefully."""
        self._set_transforming_state(False)
        self.status_label.setText(f"❌ Transformation failed: {error_msg}")
        self.status_label.setStyleSheet("color: #ef4444; font-size: 10px;")

    def dismiss(self) -> None:
        """Dismiss and hide the palette without making changes."""
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait(100)
        self._set_transforming_state(False)
        self.hide()
        self.dismissed.emit()

    # ── Keyboard & Mouse Navigation ───────────────────────────────────────────

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.dismiss()
            event.accept()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_pos is not None and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        self._drag_pos = None
