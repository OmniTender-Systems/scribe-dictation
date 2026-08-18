"""Tests for transcription history buffer limits."""

import os
import sys
from unittest.mock import patch

import pytest
from PySide6.QtCore import QSettings

from scribe_dictation.ui import app as app_module
from scribe_dictation.ui.app import (
    DEFAULT_HISTORY_LIMIT,
    SETTINGS_HISTORY_LIMIT,
    SettingsDialog,
    ScribeDictationWindow,
)


@pytest.fixture
def qapp():
    """Provide a QApplication using the offscreen platform for headless tests."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    yield instance


def _make_window(qapp, history_limit=1):
    with (
        patch.object(ScribeDictationWindow, "_setup_global_hotkey"),
        patch.object(ScribeDictationWindow, "_setup_tray"),
        patch.object(ScribeDictationWindow, "_setup_transcriber"),
    ):
        window = ScribeDictationWindow()
    window._set_history_limit(history_limit)
    return window


class TestHistoryLimit:
    """Test suite verifying transcription buffer history limits."""

    def test_default_history_limit_is_one(self, qapp):
        settings = QSettings(app_module.ORGANIZATION, app_module.APP_NAME)
        settings.remove(SETTINGS_HISTORY_LIMIT)
        with (
            patch.object(ScribeDictationWindow, "_setup_global_hotkey"),
            patch.object(ScribeDictationWindow, "_setup_tray"),
            patch.object(ScribeDictationWindow, "_setup_transcriber"),
        ):
            window = ScribeDictationWindow()
        assert window._history_limit == 1
        assert DEFAULT_HISTORY_LIMIT == 1

    def test_limit_one_only_keeps_last_transcription(self, qapp):
        window = _make_window(qapp, history_limit=1)

        with (
            patch.object(app_module, "_copy_to_clipboard"),
            patch.object(app_module, "_simulate_paste"),
        ):
            window._on_transcription_complete("First sentence.")
            assert window.text_display.toPlainText() == "First sentence."
            assert len(window._segments) == 1
            assert window._segments[0].text == "First sentence."

            window._on_transcription_complete("Second sentence.")
            assert window.text_display.toPlainText() == "Second sentence."
            assert len(window._segments) == 1
            assert window._segments[0].text == "Second sentence."

            window._on_transcription_complete("Third sentence.")
            assert window.text_display.toPlainText() == "Third sentence."
            assert len(window._segments) == 1
            assert window._segments[0].text == "Third sentence."

    def test_limit_three_keeps_last_three_transcriptions(self, qapp):
        window = _make_window(qapp, history_limit=3)

        with (
            patch.object(app_module, "_copy_to_clipboard"),
            patch.object(app_module, "_simulate_paste"),
        ):
            window._on_transcription_complete("One")
            window._on_transcription_complete("Two")
            assert window.text_display.toPlainText() == "One\n\nTwo"
            assert len(window._segments) == 2

            window._on_transcription_complete("Three")
            assert window.text_display.toPlainText() == "One\n\nTwo\n\nThree"
            assert len(window._segments) == 3

            window._on_transcription_complete("Four")
            assert window.text_display.toPlainText() == "Two\n\nThree\n\nFour"
            assert len(window._segments) == 3
            assert [s.text for s in window._segments] == ["Two", "Three", "Four"]

    def test_unlimited_keeps_all_transcriptions(self, qapp):
        window = _make_window(qapp, history_limit=0)

        with (
            patch.object(app_module, "_copy_to_clipboard"),
            patch.object(app_module, "_simulate_paste"),
        ):
            for i in range(10):
                window._on_transcription_complete(f"Sentence {i}")

            assert len(window._segments) == 10
            assert len(window._transcription_history) == 10
            assert "Sentence 0" in window.text_display.toPlainText()
            assert "Sentence 9" in window.text_display.toPlainText()

    def test_changing_limit_dynamically_trims_existing_buffer(self, qapp):
        window = _make_window(qapp, history_limit=5)

        with (
            patch.object(app_module, "_copy_to_clipboard"),
            patch.object(app_module, "_simulate_paste"),
        ):
            for i in range(5):
                window._on_transcription_complete(f"Item {i}")

            assert len(window._transcription_history) == 5

            # Change limit to 2
            window._set_history_limit(2)
            assert len(window._transcription_history) == 2
            assert len(window._segments) == 2
            assert window._transcription_history == ["Item 3", "Item 4"]
            assert window.text_display.toPlainText() == "Item 3\n\nItem 4"

    def test_clear_text_clears_history(self, qapp):
        window = _make_window(qapp, history_limit=3)

        with (
            patch.object(app_module, "_copy_to_clipboard"),
            patch.object(app_module, "_simulate_paste"),
        ):
            window._on_transcription_complete("Item 1")
            window._on_transcription_complete("Item 2")
            assert len(window._transcription_history) == 2

            window._clear_text()
            assert window.text_display.toPlainText() == ""
            assert len(window._transcription_history) == 0
            assert len(window._segments) == 0

    def test_history_menu_actions(self, qapp):
        window = _make_window(qapp, history_limit=1)
        assert hasattr(window, "_history_actions")
        assert 1 in window._history_actions
        assert 2 in window._history_actions
        assert 3 in window._history_actions
        assert 4 in window._history_actions
        assert 5 in window._history_actions
        assert 0 in window._history_actions

        # Triggering an action changes the limit
        window._history_actions[3].trigger()
        assert window._history_limit == 3
        assert window.settings.value(SETTINGS_HISTORY_LIMIT) == 3

    def test_settings_dialog_history_combo(self, qapp):
        dialog = SettingsDialog()
        dialog.history_combo.setCurrentIndex(dialog.history_combo.findData(4))
        dialog._save()

        settings = QSettings(app_module.ORGANIZATION, app_module.APP_NAME)
        assert int(settings.value(SETTINGS_HISTORY_LIMIT)) == 4
