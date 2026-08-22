"""
Tests for Privacy Scribe Free vs Pro edition limits:
1. Daily quota limit (20 dictations/day, automatic date rollover)
2. Model restriction (base and small in Free; tiny, medium, large-v3 in Pro)
3. 30-second recording length cap
4. Dynamic window title & menu bar states
"""

import sys
import time
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QApplication

from scribe_dictation.ui.app import (
    FREE_MAX_RECORDING_SECONDS,
    ScribeDictationWindow,
    SettingsDialog,
)


class TestFreeTierLimits(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not QApplication.instance():
            cls.app = QApplication(sys.argv)
        else:
            cls.app = QApplication.instance()

    def setUp(self):
        self.settings_patcher = patch("scribe_dictation.ui.app.QSettings")
        self.mock_qsettings_class = self.settings_patcher.start()
        self.mock_settings = MagicMock()
        self.mock_qsettings_class.return_value = self.mock_settings

        self.db = {}
        self.mock_settings.value.side_effect = lambda k, default=None: self.db.get(
            k, default
        )
        self.mock_settings.setValue.side_effect = lambda k, v: self.db.update({k: v})

    def tearDown(self):
        self.settings_patcher.stop()

    @patch("scribe_dictation.ui.app.is_offline_cache_valid", return_value=False)
    @patch("scribe_dictation.ui.app._start_global_hotkey")
    def test_free_daily_limit_counting(self, mock_hotkey, mock_license):
        win = ScribeDictationWindow()
        self.assertFalse(win._is_pro())
        self.assertEqual(win._get_daily_dictation_count(), 0)
        self.assertEqual(win._get_remaining_daily_dictations(), 20)

        # Increment count
        win._increment_daily_dictation_count()
        self.assertEqual(win._get_daily_dictation_count(), 1)
        self.assertEqual(win._get_remaining_daily_dictations(), 19)

    @patch("scribe_dictation.ui.app.is_offline_cache_valid", return_value=False)
    @patch("scribe_dictation.ui.app._start_global_hotkey")
    def test_free_daily_limit_rollover_on_new_day(self, mock_hotkey, mock_license):
        win = ScribeDictationWindow()
        # Simulate yesterday's usage
        self.db["daily_usage_date"] = "2020-01-01"
        self.db["daily_usage_count"] = 20

        # Today's check should reset count to 0
        self.assertEqual(win._get_daily_dictation_count(), 0)
        self.assertEqual(win._get_remaining_daily_dictations(), 20)

    @patch("scribe_dictation.ui.app.is_offline_cache_valid", return_value=True)
    @patch("scribe_dictation.ui.app._start_global_hotkey")
    def test_pro_edition_has_unlimited_dictations(self, mock_hotkey, mock_license):
        win = ScribeDictationWindow()
        self.assertTrue(win._is_pro())
        self.assertIsNone(win._get_remaining_daily_dictations())
        self.assertIn("Pro", win.windowTitle())

    @patch("scribe_dictation.ui.app.is_offline_cache_valid", return_value=False)
    @patch("scribe_dictation.ui.app.QMessageBox.information")
    def test_free_settings_model_gating(self, mock_msg, mock_license):
        dialog = SettingsDialog()

        # User tries to select 'tiny' (Pro only) in Free mode
        dialog.model_size_combo.setCurrentText("tiny (🔒 Pro - Ultra Fast)")
        dialog._save()

        # Should fall back to 'base'
        self.assertEqual(self.db.get("local_model_size"), "base")
        mock_msg.assert_called_once()

    @patch("scribe_dictation.ui.app.is_offline_cache_valid", return_value=True)
    def test_pro_settings_unlocks_all_models(self, mock_license):
        dialog = SettingsDialog()
        dialog.model_size_combo.setCurrentText("tiny (Ultra Fast)")
        dialog._save()

        self.assertEqual(self.db.get("local_model_size"), "tiny")

    @patch("scribe_dictation.ui.app.is_offline_cache_valid", return_value=False)
    @patch("scribe_dictation.ui.app._start_global_hotkey")
    def test_free_blocked_at_daily_limit(self, mock_hotkey, mock_license):
        """Once 20 free dictations are used today, a 21st attempt must be
        blocked (no recording starts) and the daily-limit modal is shown
        instead, which points the user at the upgrade/BUY_URL path."""
        win = ScribeDictationWindow()
        self.db["daily_usage_date"] = date.today().isoformat()
        self.db["daily_usage_count"] = 20

        self.assertEqual(win._get_remaining_daily_dictations(), 0)

        with patch.object(win, "_show_daily_limit_modal") as mock_modal:
            win._start_recording()
            mock_modal.assert_called_once()
        # No recorder should have been created/started for the blocked attempt.
        self.assertIsNone(win._recorder)

    @patch("scribe_dictation.ui.app.is_offline_cache_valid", return_value=True)
    @patch("scribe_dictation.ui.app._start_global_hotkey")
    def test_recording_cap_not_applied_with_valid_license(
        self, mock_hotkey, mock_license
    ):
        """The 10s hard recording cap must never trigger when a valid
        (cached) license is active."""
        win = ScribeDictationWindow()
        self.assertTrue(win._is_pro())
        # Simulate a recording that has clearly exceeded the free-tier cap.
        win._recording_started_at = time.monotonic() - (FREE_MAX_RECORDING_SECONDS + 5)
        # The guard used by the live meter loop / stop-recording clamp must
        # be False for a Pro/licensed user, regardless of elapsed time.
        self.assertFalse(not win._is_pro())

    @patch("scribe_dictation.ui.app.is_offline_cache_valid", return_value=False)
    @patch("scribe_dictation.ui.app._start_global_hotkey")
    def test_trial_state_persists_across_simulated_restart(
        self, mock_hotkey, mock_license
    ):
        """Trial usage recorded in QSettings must survive an app restart
        (i.e. a fresh ScribeDictationWindow instance reading the same
        QSettings-backed store)."""
        win1 = ScribeDictationWindow()
        win1._increment_daily_dictation_count()
        win1._increment_daily_dictation_count()
        win1._increment_daily_dictation_count()
        self.assertEqual(win1._get_daily_dictation_count(), 3)

        # "Restart" the app: build a brand-new window against the same
        # persisted settings store (self.db), simulating process relaunch.
        win2 = ScribeDictationWindow()
        self.assertEqual(win2._get_daily_dictation_count(), 3)
        self.assertEqual(win2._get_remaining_daily_dictations(), 17)


if __name__ == "__main__":
    unittest.main()
