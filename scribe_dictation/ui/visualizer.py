"""
Animated real-time audio visualizer waveform ribbon for Privacy Scribe.

A high-performance, GPU/QPainter-rendered dynamic waveform ribbon that responds
to live microphone amplitude and frequency energy levels with smooth interpolation,
gradient glows, and an idle breathing animation.
"""

import math
from typing import List, Optional, Tuple, Union
import numpy as np

from PySide6.QtCore import QPointF, QRectF, QTimer, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QWidget


# Theme palettes for waveform ribbon
CYAN_VIOLET_PALETTE = {
    "gradient_start": QColor(56, 189, 248, 230),  # Bright cyan (#38bdf8)
    "gradient_mid": QColor(139, 92, 246, 220),  # Violet (#8b5cf6)
    "gradient_end": QColor(236, 72, 153, 200),  # Magenta/pink (#ec4899)
    "glow_color": QColor(56, 189, 248, 80),
    "fill_opacity": 0.25,
    "glow_pen_width": 3.5,
    "core_pen_width": 2.0,
}

GOLD_AMBER_PALETTE = {
    "gradient_start": QColor(251, 191, 36, 240),  # Amber/gold (#fbbf24)
    "gradient_mid": QColor(245, 158, 11, 230),  # Warm amber (#f59e0b)
    "gradient_end": QColor(239, 68, 68, 210),  # Coral/orange-red (#ef4444)
    "glow_color": QColor(251, 191, 36, 90),
    "fill_opacity": 0.30,
    "glow_pen_width": 3.5,
    "core_pen_width": 2.0,
}

TRANSCRIBING_PALETTE = {
    "gradient_start": QColor(168, 85, 247, 230),  # Purple (#a855f7)
    "gradient_mid": QColor(236, 72, 153, 220),  # Pink (#ec4899)
    "gradient_end": QColor(99, 102, 241, 210),  # Indigo (#6366f1)
    "glow_color": QColor(168, 85, 247, 90),
    "fill_opacity": 0.25,
    "glow_pen_width": 3.5,
    "core_pen_width": 2.0,
}


class AudioWaveformRibbon(QWidget):
    """
    Animated dynamic audio ribbon waveform widget.

    Renders multi-layered bezier waves reacting to audio amplitude / buffer levels
    with smooth interpolation, fluid multi-harmonic breathing animation in silence,
    and glowing gradients.
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        num_points: int = 32,
        is_pro: bool = False,
        sample_interval_ms: int = 16,
    ):
        super().__init__(parent)
        self._num_points = max(8, num_points)
        self._is_pro = is_pro
        self._is_transcribing = False
        self._is_active = True

        # Amplitude tracking (0.0 to 1.0)
        self._raw_level: float = 0.0
        self._target_amplitude: float = 0.0
        self._current_amplitude: float = 0.0

        # Frequency / multi-band heights across points
        self._target_points = np.zeros(self._num_points, dtype=np.float32)
        self._current_points = np.zeros(self._num_points, dtype=np.float32)

        # Animation phase & clock
        self._phase: float = 0.0
        self._pulse_phase: float = 0.0
        self._decay_rate: float = 0.22
        self._attack_rate: float = 0.35

        # 60 FPS update timer
        self._timer = QTimer(self)
        self._timer.setInterval(sample_interval_ms)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start()

    # ── Configuration & Properties ────────────────────────────────────

    @property
    def is_pro(self) -> bool:
        return self._is_pro

    @is_pro.setter
    def is_pro(self, val: bool) -> None:
        if self._is_pro != bool(val):
            self._is_pro = bool(val)
            self.update()

    @property
    def is_transcribing(self) -> bool:
        return self._is_transcribing

    @is_transcribing.setter
    def is_transcribing(self, val: bool) -> None:
        if self._is_transcribing != bool(val):
            self._is_transcribing = bool(val)
            self.update()

    @property
    def is_active(self) -> bool:
        return self._is_active

    @is_active.setter
    def is_active(self, val: bool) -> None:
        self._is_active = bool(val)
        if self._is_active and not self._timer.isActive():
            self._timer.start()
        elif not self._is_active and self._timer.isActive():
            self._timer.stop()
        self.update()

    def set_pro_mode(self, is_pro: bool) -> None:
        """Explicit helper to toggle pro gold/amber styling."""
        self.is_pro = is_pro

    def set_transcribing(self, transcribing: bool) -> None:
        """Explicit helper to toggle transcribing shimmer styling."""
        self.is_transcribing = transcribing

    def set_active(self, active: bool) -> None:
        """Start or stop the animation loop."""
        self.is_active = active

    # ── Live Audio Feeds ──────────────────────────────────────────────

    def update_audio_level(self, level: float) -> None:
        """
        Feed real-time microphone RMS volume level (0.0 to 1.0).
        Automatically shapes frequency distribution across points with smooth envelope.
        """
        # Clamp and scale volume for vivid responsiveness
        clamped = max(0.0, min(1.0, float(level)))
        # Non-linear boost for subtle whispers
        scaled = min(1.0, math.pow(clamped, 0.75) * 3.2 if clamped > 0 else 0.0)
        self._raw_level = clamped
        self._target_amplitude = scaled

        # Generate bell-curve shaped energy across ribbon points
        mid = (self._num_points - 1) / 2.0
        sigma = self._num_points / 3.0
        new_targets = np.zeros(self._num_points, dtype=np.float32)

        for i in range(self._num_points):
            dist = (i - mid) / sigma
            bell = math.exp(-0.5 * dist * dist)
            # Add secondary harmonics across the points
            harmonic = 0.8 + 0.3 * math.sin(i * 0.9 + self._phase * 2.0)
            new_targets[i] = min(1.0, scaled * bell * harmonic)

        self._target_points = new_targets

    def update_audio_buffer(self, buffer: Union[np.ndarray, List[float]]) -> None:
        """
        Feed raw PCM audio slice or FFT spectrum directly for high-fidelity visualization.
        """
        if buffer is None:
            self.update_audio_level(0.0)
            return

        arr = np.asarray(buffer, dtype=np.float32)
        if arr.size == 0:
            self.update_audio_level(0.0)
            return

        # If 2D (multi-channel), take mean across channels
        if arr.ndim > 1:
            arr = np.mean(arr, axis=1)

        # Compute RMS
        rms = float(np.sqrt(np.mean(arr**2)))
        self._raw_level = min(1.0, rms)
        self._target_amplitude = min(1.0, math.pow(rms, 0.75) * 3.2)

        # Downsample or interpolate buffer chunks into _num_points
        chunk_size = max(1, len(arr) // self._num_points)
        new_targets = np.zeros(self._num_points, dtype=np.float32)

        for i in range(self._num_points):
            start = i * chunk_size
            end = min(len(arr), (i + 1) * chunk_size)
            if start < len(arr):
                chunk = arr[start:end]
                val = float(np.max(np.abs(chunk))) if chunk.size > 0 else 0.0
                new_targets[i] = min(1.0, val * 2.5)

        self._target_points = new_targets

    # ── Animation Loop ────────────────────────────────────────────────

    def _on_tick(self) -> None:
        """Interpolate current state smoothly toward targets and tick idle waves."""
        # Advance phase clock
        self._phase += 0.08
        self._pulse_phase += 0.05
        if self._phase > 2.0 * math.pi * 100:
            self._phase -= 2.0 * math.pi * 100

        # Smooth overall amplitude interpolation
        if self._target_amplitude > self._current_amplitude:
            self._current_amplitude += (
                self._target_amplitude - self._current_amplitude
            ) * self._attack_rate
        else:
            self._current_amplitude += (
                self._target_amplitude - self._current_amplitude
            ) * self._decay_rate

        # Smooth point-by-point interpolation
        for i in range(self._num_points):
            target = self._target_points[i]
            curr = self._current_points[i]
            rate = self._attack_rate if target > curr else self._decay_rate
            self._current_points[i] = curr + (target - curr) * rate

        # Slowly reset target amplitude to 0 if not continually fed
        self._target_amplitude = max(0.0, self._target_amplitude * 0.88)
        self._target_points *= 0.88

        self.update()

    # ── Painting & Wave Rendering ─────────────────────────────────────

    def _get_palette(self) -> dict:
        if self._is_transcribing:
            return TRANSCRIBING_PALETTE
        if self._is_pro:
            return GOLD_AMBER_PALETTE
        return CYAN_VIOLET_PALETTE

    def _build_wave_path(
        self,
        w: float,
        h: float,
        phase_offset: float,
        freq_multiplier: float,
        amp_scale: float,
        vertical_offset: float = 0.0,
    ) -> Tuple[QPainterPath, List[QPointF]]:
        """
        Compute smooth cubic Bezier spline for a specific wave layer harmonic.
        """
        cy = (h / 2.0) + vertical_offset
        max_amp = (h / 2.0) * 0.82

        points: List[QPointF] = []
        step_x = w / (self._num_points - 1) if self._num_points > 1 else w

        # Minimum idle breathing baseline amplitude
        idle_amp = max(2.5, h * 0.09)

        for i in range(self._num_points):
            x = i * step_x
            norm_x = i / (self._num_points - 1) if self._num_points > 1 else 0.5

            # Base envelope tapering at ends (smooth transition to zero at edges)
            envelope = math.sin(norm_x * math.pi)

            # Idle multi-harmonic breathing wave
            idle_wave = (
                (
                    math.sin(
                        self._phase * 1.5 * freq_multiplier
                        + norm_x * 4.0 * math.pi
                        + phase_offset
                    )
                    * 0.65
                    + math.cos(self._phase * 2.2 + norm_x * 2.5 * math.pi) * 0.35
                )
                * idle_amp
                * envelope
            )

            # Dynamic live audio displacement
            pt_energy = float(self._current_points[i])
            active_wave = (
                pt_energy
                * max_amp
                * amp_scale
                * envelope
                * math.sin(
                    self._phase * 3.0 * freq_multiplier
                    + norm_x * 6.0 * math.pi
                    + phase_offset
                )
            )

            # If strong speaking audio, blend from idle to active
            total_y = (
                cy + (idle_wave * max(0.2, 1.0 - self._current_amplitude)) + active_wave
            )
            points.append(QPointF(x, total_y))

        # Build smooth cubic Bezier path through calculated points
        path = QPainterPath()
        if not points:
            return path, points

        path.moveTo(points[0])
        for i in range(len(points) - 1):
            p0 = points[max(0, i - 1)]
            p1 = points[i]
            p2 = points[i + 1]
            p3 = points[min(len(points) - 1, i + 2)]

            # Catmull-Rom to Cubic Bezier control points conversion
            c1x = p1.x() + (p2.x() - p0.x()) / 6.0
            c1y = p1.y() + (p2.y() - p0.y()) / 6.0
            c2x = p2.x() - (p3.x() - p1.x()) / 6.0
            c2y = p2.y() - (p3.y() - p1.y()) / 6.0

            path.cubicTo(QPointF(c1x, c1y), QPointF(c2x, c2y), p2)

        return path, points

    def paintEvent(self, event) -> None:
        """Draw glowing animated waveform ribbons with layered alpha and gradients."""
        w = float(self.width())
        h = float(self.height())
        if w <= 0 or h <= 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        palette = self._get_palette()

        # ── 1. Create Linear Gradient Brush ──
        grad = QLinearGradient(0, 0, w, 0)
        grad.setColorAt(0.0, palette["gradient_start"])
        grad.setColorAt(0.5, palette["gradient_mid"])
        grad.setColorAt(1.0, palette["gradient_end"])

        # ── 2. Layer 1: Background Fill under Secondary Harmonic Wave ──
        wave2_path, wave2_points = self._build_wave_path(
            w, h, phase_offset=math.pi * 0.5, freq_multiplier=0.8, amp_scale=0.65
        )

        fill_path = QPainterPath(wave2_path)
        fill_path.lineTo(w, h)
        fill_path.lineTo(0, h)
        fill_path.closeSubpath()

        fill_grad = QLinearGradient(0, 0, 0, h)
        fill_color_top = QColor(palette["gradient_mid"])
        fill_color_top.setAlphaF(
            palette["fill_opacity"] * max(0.3, self._current_amplitude + 0.4)
        )
        fill_color_bot = QColor(palette["gradient_start"])
        fill_color_bot.setAlphaF(0.0)
        fill_grad.setColorAt(0.0, fill_color_top)
        fill_grad.setColorAt(1.0, fill_color_bot)

        painter.fillPath(fill_path, QBrush(fill_grad))

        # ── 3. Layer 2: Secondary Harmonic Wave Glow & Line ──
        sub_pen = QPen(palette["gradient_mid"], 1.2)
        sub_color = QColor(palette["gradient_mid"])
        sub_color.setAlphaF(0.55)
        sub_pen.setColor(sub_color)
        painter.setPen(sub_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(wave2_path)

        # ── 4. Layer 3: Primary Wave Outer Glow ──
        wave1_path, wave1_points = self._build_wave_path(
            w, h, phase_offset=0.0, freq_multiplier=1.1, amp_scale=1.0
        )

        glow_pen = QPen(palette["glow_color"], palette["glow_pen_width"])
        glow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        glow_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(glow_pen)
        painter.drawPath(wave1_path)

        # ── 5. Layer 4: Primary Wave Crisp Core Ribbon ──
        core_pen = QPen(QBrush(grad), palette["core_pen_width"])
        core_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        core_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(core_pen)
        painter.drawPath(wave1_path)

        # ── 6. Layer 5: Resonant Bouncing Orb (Bouncing Ball + Energy Rings) ──
        # Compute orb position riding the dynamic wave crest
        if len(wave1_points) > 1:
            if self._is_transcribing:
                # Smooth sinusoidal ping-pong bounce between left and right margins
                bounce_factor = (math.sin(self._phase * 2.0) + 1.0) / 2.0  # 0.0 to 1.0
                margin = 8.0
                orb_x = margin + bounce_factor * (w - 2.0 * margin)
                # Interpolate y coordinate along wave1_points based on orb_x
                norm_pos = (orb_x / w) * (len(wave1_points) - 1)
                idx_low = max(0, min(len(wave1_points) - 2, int(norm_pos)))
                t = max(0.0, min(1.0, norm_pos - idx_low))
                orb_y = (
                    wave1_points[idx_low].y() * (1.0 - t)
                    + wave1_points[idx_low + 1].y() * t
                )
            else:
                mid_idx = len(wave1_points) // 2
                center_pt = wave1_points[mid_idx]
                orb_x = center_pt.x()
                orb_y = center_pt.y()

            # Dynamic bounce & pulse calculation
            orb_base_radius = max(3.5, min(6.5, h * 0.18))
            energy_boost = (
                (math.sin(self._phase * 4.0) * 1.2 + 1.2)
                if self._is_transcribing
                else self._current_amplitude * 4.5
            )
            pulse = math.sin(self._phase * 3.5) * 0.8
            orb_r = orb_base_radius + energy_boost + pulse

            # A. Concentric Resonance Shockwave Rings (Expanding Ripple when speaking or transcribing)
            if self._current_amplitude > 0.08 or self._is_transcribing:
                ring_strength = (
                    0.55 if self._is_transcribing else self._current_amplitude
                )
                for ring_i in range(2):
                    ring_phase = (self._phase * 2.5 + ring_i * math.pi) % (
                        2.0 * math.pi
                    )
                    ring_norm = ring_phase / (2.0 * math.pi)
                    ring_r = orb_r + ring_norm * (h * 0.38)
                    ring_alpha = int(
                        max(
                            0,
                            (1.0 - ring_norm) * min(180, ring_strength * 210),
                        )
                    )

                    ring_pen = QPen(palette["glow_color"], 1.2)
                    ring_color = QColor(palette["glow_color"])
                    ring_color.setAlpha(ring_alpha)
                    ring_pen.setColor(ring_color)
                    painter.setPen(ring_pen)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawEllipse(
                        QRectF(
                            orb_x - ring_r, orb_y - ring_r, ring_r * 2.0, ring_r * 2.0
                        )
                    )

            # B. Outer Radiant Glow Halo for Bouncing Orb
            halo_r = orb_r * 2.2
            halo_grad = QLinearGradient(
                orb_x - halo_r, orb_y - halo_r, orb_x + halo_r, orb_y + halo_r
            )
            halo_c1 = QColor(palette["gradient_start"])
            halo_c1.setAlpha(int(min(160, 60 + self._current_amplitude * 140)))
            halo_c2 = QColor(palette["gradient_end"])
            halo_c2.setAlpha(0)
            halo_grad.setColorAt(0.0, halo_c1)
            halo_grad.setColorAt(1.0, halo_c2)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(halo_grad))
            painter.drawEllipse(
                QRectF(orb_x - halo_r, orb_y - halo_r, halo_r * 2.0, halo_r * 2.0)
            )

            # C. Solid Inner Resonating Orb Core with gradient
            orb_grad = QLinearGradient(
                orb_x - orb_r, orb_y - orb_r, orb_x + orb_r, orb_y + orb_r
            )
            orb_grad.setColorAt(0.0, QColor(255, 255, 255, 245))
            orb_grad.setColorAt(0.45, palette["gradient_start"])
            orb_grad.setColorAt(1.0, palette["gradient_mid"])
            painter.setBrush(QBrush(orb_grad))
            painter.drawEllipse(
                QRectF(orb_x - orb_r, orb_y - orb_r, orb_r * 2.0, orb_r * 2.0)
            )

            # D. Hot Core Specular Reflection
            spec_r = max(1.0, orb_r * 0.35)
            spec_x = orb_x - orb_r * 0.28
            spec_y = orb_y - orb_r * 0.28
            painter.setBrush(QBrush(QColor(255, 255, 255, 220)))
            painter.drawEllipse(
                QRectF(spec_x - spec_r, spec_y - spec_r, spec_r * 2.0, spec_r * 2.0)
            )
