"""
Holographic Floating Audio Visualizer Capsule for Private Scribe.

A frameless, translucent, frosted-acrylic floating HUD pill that appears when
recording or transcribing without stealing window focus.
"""

import math
import numpy as np
from typing import Optional
from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import (
    QColor, QPainter, QPainterPath, QLinearGradient, QBrush, QPen, QFont, QScreen
)
from PySide6.QtWidgets import QWidget, QApplication


class VoiceCapsule(QWidget):
    """A floating, non-intrusive acrylic audio visualizer HUD."""

    STATE_RECORDING = "recording"
    STATE_TRANSCRIBING = "transcribing"
    STATE_DONE = "done"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        # Enforce OS-level non-activation flags so HUD capsule never steals focus
        import sys
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

        self.setFixedSize(170, 44)

        # Visualizer State
        self._state = self.STATE_RECORDING
        self._level = 0.0
        self._phase = 0.0
        self._bars = [0.15, 0.25, 0.35, 0.25, 0.15]
        self._target_bars = [0.15, 0.25, 0.35, 0.25, 0.15]

        # Animation timer (60 FPS)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate_frame)
        self._timer.setInterval(16)

    def show_recording(self):
        """Display the capsule in recording audio waveform mode."""
        self._state = self.STATE_RECORDING
        self._level = 0.0
        self._reposition()
        self.show()
        if not self._timer.isActive():
            self._timer.start()

    def show_transcribing(self):
        """Display the capsule in quantum AI shimmer mode."""
        self._state = self.STATE_TRANSCRIBING
        self._reposition()
        self.show()
        if not self._timer.isActive():
            self._timer.start()

    def show_done(self):
        """Briefly show completion before fading out."""
        self._state = self.STATE_DONE
        self.update()
        QTimer.singleShot(450, self.hide_capsule)

    def hide_capsule(self):
        """Hide capsule and stop animation."""
        self._timer.stop()
        self.hide()

    def update_audio_level(self, level: float):
        """Feed real-time microphone RMS volume level (0.0 to 1.0)."""
        self._level = max(0.0, min(1.0, level * 5.0))
        # Spread energy across 5 bars with slight frequency curve
        c = self._level
        self._target_bars = [
            0.15 + c * 0.45,
            0.25 + c * 0.85,
            0.35 + c * 1.0,
            0.25 + c * 0.75,
            0.15 + c * 0.40,
        ]

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
        if self._state == self.STATE_RECORDING:
            # Smooth bar interpolation towards target
            for i in range(len(self._bars)):
                self._bars[i] += (self._target_bars[i] - self._bars[i]) * 0.3
                # Natural idle oscillation
                idle = math.sin(self._phase + i * 0.7) * 0.08
                self._bars[i] = max(0.12, min(1.0, self._bars[i] + idle))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        radius = h / 2.0
        rect = QRectF(1.5, 1.5, w - 3.0, h - 3.0)

        # ── 1. Frosted Glass Acrylic Background ──
        bg_gradient = QLinearGradient(0, 0, 0, h)
        bg_gradient.setColorAt(0.0, QColor(22, 27, 34, 230))
        bg_gradient.setColorAt(1.0, QColor(13, 17, 23, 245))

        capsule_path = QPainterPath()
        capsule_path.addRoundedRect(rect, radius, radius)

        painter.fillPath(capsule_path, QBrush(bg_gradient))

        # ── 2. Subtle Glow Border ──
        if self._state == self.STATE_RECORDING:
            border_pen = QPen(QColor(88, 166, 255, 140), 1.2)
        elif self._state == self.STATE_TRANSCRIBING:
            # Shimmering purple/cyan gradient border
            shimmer = (math.sin(self._phase * 1.5) + 1.0) / 2.0
            border_pen = QPen(QColor(163, 113, 247, int(120 + shimmer * 110)), 1.4)
        else:
            border_pen = QPen(QColor(63, 185, 80, 200), 1.2)

        painter.setPen(border_pen)
        painter.drawRoundedRect(rect, radius, radius)

        # ── 3. Internal Content ──
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))

        if self._state == self.STATE_RECORDING:
            # Live 5-Band Fluid Equalizer Bars
            bar_width = 3.5
            bar_gap = 3.2
            total_bars_width = 5 * bar_width + 4 * bar_gap
            start_x = 24.0

            for i, val in enumerate(self._bars):
                bar_h = max(4.0, val * 18.0)
                bx = start_x + i * (bar_width + bar_gap)
                by = (h - bar_h) / 2.0

                # Cyan to emerald gradient bars
                bar_grad = QLinearGradient(bx, by, bx, by + bar_h)
                bar_grad.setColorAt(0.0, QColor(56, 189, 248))
                bar_grad.setColorAt(1.0, QColor(52, 211, 153))

                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(bar_grad))
                painter.drawRoundedRect(QRectF(bx, by, bar_width, bar_h), 1.75, 1.75)

            # Label
            painter.setPen(QColor(240, 246, 252))
            painter.drawText(QRectF(start_x + total_bars_width + 12, 0, w - start_x - total_bars_width - 16, h),
                             int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), "Listening...")

        elif self._state == self.STATE_TRANSCRIBING:
            # AI Shimmer Wave Pulse
            pulse_x = 26.0 + (math.sin(self._phase * 2.0) + 1.0) * 12.0
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(168, 85, 247, 220)))
            painter.drawEllipse(QRectF(pulse_x, (h - 8.0) / 2.0, 8.0, 8.0))

            painter.setPen(QColor(192, 132, 252))
            painter.drawText(QRectF(52, 0, w - 56, h),
                             int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), "Transcribing...")

        elif self._state == self.STATE_DONE:
            # Green Checkmark Pulse
            painter.setPen(QColor(74, 222, 128))
            painter.drawText(QRectF(0, 0, w, h),
                             int(Qt.AlignmentFlag.AlignCenter), "✓ Pasted")
