"""
Holographic Floating Audio Visualizer Capsule for Privacy Scribe.

A frameless, translucent, frosted-acrylic floating HUD pill that appears when
recording or transcribing without stealing window focus. Powered by the
AudioWaveformRibbon dynamic waveform engine.
"""

import math
import sys
from typing import Optional, Union
import numpy as np

from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import (
    QColor,
    QPainter,
    QPainterPath,
    QLinearGradient,
    QBrush,
    QPen,
    QFont,
    QScreen,
)
from PySide6.QtWidgets import QWidget, QApplication, QHBoxLayout, QLabel

from scribe_dictation.ui.visualizer import AudioWaveformRibbon


class VoiceCapsule(QWidget):
    """A floating, non-intrusive acrylic audio visualizer HUD featuring waveform ribbon."""

    STATE_RECORDING = "recording"
    STATE_TRANSCRIBING = "transcribing"
    STATE_DONE = "done"

    def __init__(self, parent=None, is_pro: bool = False):
        super().__init__(parent)
        self._is_pro = is_pro
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        # Enforce OS-level non-activation flags so HUD capsule never steals focus
        if sys.platform == "win32":
            try:
                import ctypes

                hwnd = int(self.winId())
                GWL_EXSTYLE = -20
                WS_EX_NOACTIVATE = 0x08000000
                WS_EX_TOOLWINDOW = 0x00000080
                WS_EX_TOPMOST = 0x00000008
                user32 = ctypes.windll.user32
                style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                user32.SetWindowLongW(
                    hwnd,
                    GWL_EXSTYLE,
                    style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST,
                )
            except Exception:
                pass

        self.setFixedSize(190, 44)

        # Visualizer State
        self._state = self.STATE_RECORDING
        self._phase = 0.0

        # Sub-components: Ribbon waveform + Status text
        self._setup_layout()

        # Animation timer for capsule frame & border shimmer (60 FPS)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate_frame)
        self._timer.setInterval(16)

    def _setup_layout(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 4, 14, 4)
        layout.setSpacing(8)

        # Waveform ribbon widget
        self.ribbon = AudioWaveformRibbon(self, num_points=24, is_pro=self._is_pro)
        self.ribbon.setFixedSize(54, 32)
        layout.addWidget(self.ribbon)

        # Status text label
        self.label = QLabel("Listening...")
        self.label.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        self.label.setStyleSheet("color: #f0f6fc; background: transparent;")
        self.label.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        )
        layout.addWidget(self.label)

    @property
    def is_pro(self) -> bool:
        return self._is_pro

    @is_pro.setter
    def is_pro(self, val: bool) -> None:
        self._is_pro = bool(val)
        if hasattr(self, "ribbon"):
            self.ribbon.is_pro = self._is_pro
        self.update()

    def set_pro_mode(self, is_pro: bool) -> None:
        self.is_pro = is_pro

    def show_recording(self):
        """Display the capsule in recording audio waveform mode."""
        self._state = self.STATE_RECORDING
        self.ribbon.set_transcribing(False)
        self.ribbon.set_active(True)
        self.ribbon.show()
        self.label.setText("Listening...")
        self.label.setStyleSheet("color: #f0f6fc; background: transparent;")
        self._reposition()
        self.show()
        if not self._timer.isActive():
            self._timer.start()

    def show_transcribing(self):
        """Display the capsule in quantum AI shimmer mode."""
        self._state = self.STATE_TRANSCRIBING
        self.ribbon.set_transcribing(True)
        self.ribbon.set_active(True)
        self.ribbon.show()
        self.label.setText("Transcribing...")
        self.label.setStyleSheet("color: #c084fc; background: transparent;")
        self._reposition()
        self.show()
        if not self._timer.isActive():
            self._timer.start()

    def show_done(self):
        """Briefly show completion before fading out."""
        self._state = self.STATE_DONE
        self.ribbon.set_active(False)
        self.ribbon.hide()
        self.label.setText("✓ Pasted")
        self.label.setStyleSheet(
            "color: #4ade80; background: transparent; font-weight: bold;"
        )
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.update()
        QTimer.singleShot(450, self.hide_capsule)

    def hide_capsule(self):
        """Hide capsule and stop animation."""
        self._timer.stop()
        self.ribbon.set_active(False)
        self.hide()

    def update_audio_level(self, level: float):
        """Feed real-time microphone RMS volume level (0.0 to 1.0) into ribbon."""
        if hasattr(self, "ribbon"):
            self.ribbon.update_audio_level(level)

    def update_audio_buffer(self, buffer: Union[np.ndarray, list]):
        """Feed raw audio slice into ribbon."""
        if hasattr(self, "ribbon"):
            self.ribbon.update_audio_buffer(buffer)

    def _reposition(self):
        """Position the capsule nicely at bottom-center of current screen."""
        screen: Optional[QScreen] = QApplication.primaryScreen()
        if screen:
            geom = screen.availableGeometry()
            x = geom.x() + (geom.width() - self.width()) // 2
            y = geom.y() + geom.height() - self.height() - 48
            self.move(x, y)

    def _animate_frame(self):
        self._phase += 0.12
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = float(self.width()), float(self.height())
        radius = h / 2.0
        rect = QRectF(1.5, 1.5, w - 3.0, h - 3.0)

        # ── 1. Frosted Glass Acrylic Background ──
        bg_gradient = QLinearGradient(0, 0, 0, h)
        bg_gradient.setColorAt(0.0, QColor(22, 27, 34, 235))
        bg_gradient.setColorAt(1.0, QColor(13, 17, 23, 250))

        capsule_path = QPainterPath()
        capsule_path.addRoundedRect(rect, radius, radius)

        painter.fillPath(capsule_path, QBrush(bg_gradient))

        # ── 2. Dynamic Glow Border ──
        if self._state == self.STATE_RECORDING:
            if self._is_pro:
                border_pen = QPen(QColor(251, 191, 36, 170), 1.3)
            else:
                border_pen = QPen(QColor(88, 166, 255, 160), 1.3)
        elif self._state == self.STATE_TRANSCRIBING:
            # Shimmering purple gradient border
            shimmer = (math.sin(self._phase * 1.5) + 1.0) / 2.0
            border_pen = QPen(QColor(168, 85, 247, int(130 + shimmer * 115)), 1.5)
        else:
            border_pen = QPen(QColor(74, 222, 128, 210), 1.3)

        painter.setPen(border_pen)
        painter.drawRoundedRect(rect, radius, radius)
