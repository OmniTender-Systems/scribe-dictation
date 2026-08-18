"""
Unit tests for AudioWaveformRibbon and VoiceCapsule visualizers.

Tests:
1. AudioWaveformRibbon initialization, property updates (is_pro, is_transcribing, is_active).
2. update_audio_level and update_audio_buffer edge cases (empty, non-empty, multi-channel, 0.0, 1.0).
3. 60 FPS animation tick interpolation and smooth decay.
4. PaintEvent execution without crashing across different states (idle, active, pro, transcribing).
5. VoiceCapsule integration with AudioWaveformRibbon, status transitions (recording, transcribing, done).
"""

import sys
import unittest
import numpy as np

from PySide6.QtWidgets import QApplication

from scribe_dictation.ui.visualizer import (
    AudioWaveformRibbon,
    CYAN_VIOLET_PALETTE,
    GOLD_AMBER_PALETTE,
    TRANSCRIBING_PALETTE,
)
from scribe_dictation.ui.overlay import VoiceCapsule


class TestAudioVisualizer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not QApplication.instance():
            cls.app = QApplication(sys.argv)
        else:
            cls.app = QApplication.instance()

    def setUp(self):
        self.ribbon = AudioWaveformRibbon(num_points=16, is_pro=False)
        self.ribbon.resize(100, 30)

    def tearDown(self):
        self.ribbon.set_active(False)
        self.ribbon.deleteLater()

    def test_ribbon_initialization(self):
        self.assertEqual(self.ribbon._num_points, 16)
        self.assertFalse(self.ribbon.is_pro)
        self.assertFalse(self.ribbon.is_transcribing)
        self.assertTrue(self.ribbon.is_active)
        self.assertEqual(self.ribbon._raw_level, 0.0)
        self.assertEqual(self.ribbon._current_amplitude, 0.0)

    def test_ribbon_pro_and_transcribing_modes(self):
        # Default Free mode palette
        palette = self.ribbon._get_palette()
        self.assertEqual(palette, CYAN_VIOLET_PALETTE)

        # Toggle Pro mode
        self.ribbon.set_pro_mode(True)
        self.assertTrue(self.ribbon.is_pro)
        palette = self.ribbon._get_palette()
        self.assertEqual(palette, GOLD_AMBER_PALETTE)

        # Toggle Transcribing mode
        self.ribbon.set_transcribing(True)
        self.assertTrue(self.ribbon.is_transcribing)
        palette = self.ribbon._get_palette()
        self.assertEqual(palette, TRANSCRIBING_PALETTE)

        # Revert Transcribing
        self.ribbon.set_transcribing(False)
        self.assertEqual(self.ribbon._get_palette(), GOLD_AMBER_PALETTE)

    def test_update_audio_level(self):
        # Silence
        self.ribbon.update_audio_level(0.0)
        self.assertEqual(self.ribbon._raw_level, 0.0)
        self.assertEqual(self.ribbon._target_amplitude, 0.0)

        # Moderate voice level
        self.ribbon.update_audio_level(0.25)
        self.assertEqual(self.ribbon._raw_level, 0.25)
        self.assertGreater(self.ribbon._target_amplitude, 0.0)
        self.assertGreater(np.max(self.ribbon._target_points), 0.0)

        # Peak loud volume clamping
        self.ribbon.update_audio_level(1.5)
        self.assertEqual(self.ribbon._raw_level, 1.0)
        self.assertEqual(self.ribbon._target_amplitude, 1.0)

    def test_update_audio_buffer(self):
        # None buffer
        self.ribbon.update_audio_buffer(None)
        self.assertEqual(self.ribbon._raw_level, 0.0)

        # Empty array
        self.ribbon.update_audio_buffer(np.array([], dtype=np.float32))
        self.assertEqual(self.ribbon._raw_level, 0.0)

        # Sine wave buffer
        t = np.linspace(0, 1, 1600, endpoint=False)
        sine = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        self.ribbon.update_audio_buffer(sine)
        self.assertGreater(self.ribbon._raw_level, 0.0)
        self.assertGreater(np.max(self.ribbon._target_points), 0.0)

        # 2D stereo buffer
        stereo = np.stack([sine, sine], axis=1)
        self.ribbon.update_audio_buffer(stereo)
        self.assertGreater(self.ribbon._raw_level, 0.0)

    def test_animation_tick_interpolation(self):
        # Set high target level
        self.ribbon.update_audio_level(0.8)
        initial_curr = self.ribbon._current_amplitude
        initial_phase = self.ribbon._phase

        # Run tick
        self.ribbon._on_tick()

        self.assertGreater(self.ribbon._current_amplitude, initial_curr)
        self.assertGreater(self.ribbon._phase, initial_phase)

    def test_paint_event_safety(self):
        """Ensure painting executes cleanly without exceptions in all states."""
        # 1. Idle state
        self.ribbon.repaint()

        # 2. Speaking / active state
        self.ribbon.update_audio_level(0.7)
        self.ribbon._on_tick()
        self.ribbon.repaint()

        # 3. Pro state
        self.ribbon.set_pro_mode(True)
        self.ribbon.repaint()

        # 4. Transcribing state
        self.ribbon.set_transcribing(True)
        self.ribbon.repaint()

    def test_voice_capsule_integration(self):
        capsule = VoiceCapsule(is_pro=False)
        try:
            self.assertIsNotNone(capsule.ribbon)
            self.assertFalse(capsule.is_pro)

            # Test show_recording
            capsule.show_recording()
            self.assertEqual(capsule._state, VoiceCapsule.STATE_RECORDING)
            self.assertTrue(capsule.ribbon.is_active)
            self.assertFalse(capsule.ribbon.is_transcribing)
            self.assertEqual(capsule.label.text(), "Listening...")

            # Test audio feed
            capsule.update_audio_level(0.4)
            self.assertGreater(capsule.ribbon._target_amplitude, 0.0)

            # Test show_transcribing
            capsule.show_transcribing()
            self.assertEqual(capsule._state, VoiceCapsule.STATE_TRANSCRIBING)
            self.assertTrue(capsule.ribbon.is_transcribing)
            self.assertEqual(capsule.label.text(), "Processing...")

            # Test show_done
            capsule.show_done()
            self.assertEqual(capsule._state, VoiceCapsule.STATE_DONE)
            self.assertFalse(capsule.ribbon.is_active)
            self.assertEqual(capsule.label.text(), "✓ Pasted")

            # Test paint event safety
            capsule.repaint()

            # Test pro mode toggle
            capsule.set_pro_mode(True)
            self.assertTrue(capsule.is_pro)
            self.assertTrue(capsule.ribbon.is_pro)
            capsule.repaint()

            capsule.hide_capsule()
            self.assertFalse(capsule.isVisible())
        finally:
            capsule.deleteLater()


if __name__ == "__main__":
    unittest.main()
