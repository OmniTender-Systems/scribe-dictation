"""Unit tests for the Global 'Transform Selected Text' Quick Action Palette."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from scribe_dictation.formatters.modes import (
    FormatEngine,
)
from scribe_dictation.ui.app import ScribeDictationWindow, _is_transform_hotkey_match
from scribe_dictation.ui.transform_palette import (
    DEFAULT_TRANSFORM_ACTIONS,
    TransformPalette,
    _copy_to_clipboard,
    _simulate_copy,
    _simulate_paste,
    grab_selected_text,
)


@pytest.fixture
def qapp():
    """Ensure a QApplication instance exists with offscreen platform for headless test execution."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    yield instance


# ── 1. FormatEngine & Transform Presets Tests ─────────────────────────────────


class TestFormatEngineTransform:
    """Test FormatEngine transformation actions and fallback algorithms."""

    @pytest.fixture
    def engine(self):
        return FormatEngine()

    def test_transform_empty_or_whitespace(self, engine):
        assert engine.transform("", "clean") == ""
        assert engine.transform("   ", "bullets") == "   "

    def test_transform_clean_action(self, engine):
        raw = "Um, so like, we should basically, uh, complete the project."
        result = engine.transform(raw, action="clean", use_llm=False)
        assert "um" not in result.lower()
        assert "like" not in result.lower()
        assert "basically" not in result.lower()
        assert "complete the project" in result

    def test_transform_bullets_action(self, engine):
        text = "First review the pull request. Second run all the test suites."
        result = engine.transform(text, action="bullets", use_llm=False)
        lines = result.strip().splitlines()
        assert len(lines) == 2
        assert lines[0].startswith("- First review")
        assert lines[1].startswith("- Second run")

    def test_transform_email_action(self, engine):
        text = "Please submit the quarterly budget by end of day Friday."
        result = engine.transform(text, action="email", use_llm=False)
        assert "Subject:" in result
        assert "Hi there," in result
        assert "quarterly budget" in result
        assert "Best regards," in result

    def test_transform_summary_action(self, engine):
        text = "We decided to migrate the database to Postgres. The downtime will be minimal. Team leads must notify their members."
        result = engine.transform(text, action="summary", use_llm=False)
        assert "### Executive Summary" in result
        assert "We decided to migrate the database to Postgres." in result
        assert "### Key Takeaways" in result
        assert "- The downtime will be minimal" in result

    def test_transform_translate_en_action(self, engine):
        # Offline fallback returns text
        text = "Bonjour le monde"
        result = engine.transform(text, action="translate_en", use_llm=False)
        assert result == "Bonjour le monde"

    def test_transform_custom_instruction_offline(self, engine):
        text = "Um, this is sample input text."
        result = engine.transform(
            text, action="custom", custom_instruction="Make concise", use_llm=False
        )
        assert "this is sample input text" in result

    def test_transform_with_custom_llm_callable(self):
        def mock_llm(prompt: str, user_text: str) -> str:
            if "translate" in prompt.lower():
                return "Hello world"
            return f"PROCESSED: {user_text}"

        engine = FormatEngine(llm_client=mock_llm)
        translated = engine.transform(
            "Bonjour le monde", action="translate_en", use_llm=True
        )
        assert translated == "Hello world"

        summary = engine.transform("Test text", action="summary", use_llm=True)
        assert summary == "PROCESSED: Test text"


# ── 2. Palette Widget Initialization & UI Layout ─────────────────────────────


class TestTransformPaletteWidget:
    """Test TransformPalette widget construction, components, and layout."""

    def test_palette_initialization(self, qapp):
        engine = FormatEngine()
        palette = TransformPalette(
            format_engine=engine,
            target_hwnd=12345,
            initial_text="Sample highlighted text",
            is_pro=True,
        )

        assert palette.get_text() == "Sample highlighted text"
        assert palette.target_hwnd == 12345
        assert palette.is_pro is True
        assert len(palette.action_buttons) == len(DEFAULT_TRANSFORM_ACTIONS)
        assert palette.text_preview.toPlainText() == "Sample highlighted text"
        assert palette.custom_input is not None
        assert palette.shimmer_bar is not None
        assert palette.status_label is not None
        assert palette.windowFlags() & Qt.WindowType.FramelessWindowHint
        assert palette.windowFlags() & Qt.WindowType.WindowStaysOnTopHint

    def test_palette_set_text_and_hwnd(self, qapp):
        palette = TransformPalette()
        palette.set_text("Updated text content")
        assert palette.get_text() == "Updated text content"

        palette.set_target_hwnd(99999)
        assert palette.target_hwnd == 99999

    def test_palette_actions_list(self, qapp):
        palette = TransformPalette()
        action_ids = [btn.item.id for btn in palette.action_buttons]
        expected_ids = ["clean", "bullets", "email", "summary", "translate_en"]
        assert action_ids == expected_ids

    def test_dismiss_emits_signal(self, qapp):
        palette = TransformPalette()
        dismissed_mock = MagicMock()
        palette.dismissed.connect(dismissed_mock)

        palette.dismiss()
        dismissed_mock.assert_called_once()
        assert not palette.isVisible()


# ── 3. Action Dispatch & Transformation Execution ─────────────────────────────


class TestActionDispatch:
    """Test action triggering, background thread execution, and callbacks."""

    def test_execute_transform_empty_text_shows_warning(self, qapp):
        palette = TransformPalette(initial_text="")
        palette.execute_transform(action="clean")
        assert "Please select or enter text" in palette.status_label.text()

    def test_execute_transform_runs_worker_and_emits(self, qapp):
        def mock_llm(prompt: str, user_text: str) -> str:
            return "- Bullet point 1\n- Bullet point 2"

        engine = FormatEngine(llm_client=mock_llm)
        palette = TransformPalette(
            format_engine=engine, initial_text="Point one. Point two."
        )

        transformed_mock = MagicMock()
        palette.transformed.connect(transformed_mock)

        with (
            patch(
                "scribe_dictation.ui.transform_palette._copy_to_clipboard"
            ) as mock_copy,
            patch(
                "scribe_dictation.ui.transform_palette._simulate_paste"
            ) as mock_paste,
        ):
            palette.execute_transform(action="bullets")

            # Wait for worker thread to complete
            if palette._worker:
                palette._worker.wait(2000)

            # Process Qt event queue
            qapp.processEvents()

            transformed_mock.assert_called_once_with(
                "- Bullet point 1\n- Bullet point 2"
            )
            mock_copy.assert_called_once_with("- Bullet point 1\n- Bullet point 2")
            mock_paste.assert_called_once()
            assert "Pasted" in palette.status_label.text()

    def test_custom_instruction_execution(self, qapp):
        def mock_llm(prompt: str, user_text: str) -> str:
            return f"Custom result for: {user_text}"

        engine = FormatEngine(llm_client=mock_llm)
        palette = TransformPalette(format_engine=engine, initial_text="Input raw text")
        palette.custom_input.setText("Explain in 5 words")

        transformed_mock = MagicMock()
        palette.transformed.connect(transformed_mock)

        with (
            patch("scribe_dictation.ui.transform_palette._copy_to_clipboard"),
            patch("scribe_dictation.ui.transform_palette._simulate_paste"),
        ):
            palette._on_custom_transform()

            if palette._worker:
                palette._worker.wait(2000)
            qapp.processEvents()

            transformed_mock.assert_called_once_with(
                "Custom result for: Input raw text"
            )

    def test_worker_error_handling(self, qapp):
        mock_engine = MagicMock()
        mock_engine.transform.side_effect = RuntimeError("API connection timeout")

        palette = TransformPalette(format_engine=mock_engine, initial_text="Some text")
        palette.execute_transform(action="summary")

        if palette._worker:
            palette._worker.wait(2000)
        qapp.processEvents()

        assert "Transformation failed" in palette.status_label.text()
        assert "API connection timeout" in palette.status_label.text()


# ── 4. Clipboard Grabbing & Simulation ───────────────────────────────────────


class TestClipboardSimulation:
    """Test grab_selected_text, copy and paste simulation helpers."""

    def test_copy_to_clipboard_qt(self, qapp):
        mock_clip = MagicMock()
        with patch.object(QGuiApplication, "clipboard", return_value=mock_clip):
            result = _copy_to_clipboard("test clip text")
            assert result is True
            mock_clip.setText.assert_called_once_with("test clip text")

    def test_copy_to_clipboard_pyperclip_fallback(self, qapp):
        with patch.object(QGuiApplication, "clipboard", return_value=None):
            with patch("pyperclip.copy") as mock_pyper:
                result = _copy_to_clipboard("fallback text")
                assert result is True
                mock_pyper.assert_called_once_with("fallback text")

    def test_grab_selected_text_detects_new_text(self, qapp):
        mock_clip = MagicMock()
        mock_clip.text.side_effect = ["", "Newly copied selected text"]

        with (
            patch.object(QGuiApplication, "clipboard", return_value=mock_clip),
            patch(
                "scribe_dictation.ui.transform_palette._simulate_copy"
            ) as mock_sim_copy,
        ):
            text = grab_selected_text(target_hwnd=None, timeout=0.1)
            mock_sim_copy.assert_called_once()
            assert text == "Newly copied selected text"

    def test_simulate_copy_calls_pynput_or_win32(self):
        with (
            patch("sys.platform", "darwin"),
            patch("pynput.keyboard.Controller") as mock_ctrl_cls,
        ):
            mock_kb = MagicMock()
            mock_ctrl_cls.return_value = mock_kb
            _simulate_copy()
            mock_kb.press.assert_called()
            mock_kb.release.assert_called()

    def test_simulate_paste_calls_pynput_or_win32(self):
        with (
            patch("sys.platform", "darwin"),
            patch("pynput.keyboard.Controller") as mock_ctrl_cls,
        ):
            mock_kb = MagicMock()
            mock_ctrl_cls.return_value = mock_kb
            _simulate_paste()
            mock_kb.press.assert_called()
            mock_kb.release.assert_called()


# ── 5. Hotkey Matching & MainWindow Integration ──────────────────────────────


class TestHotkeyAndWindowIntegration:
    """Test hotkey detection helper and ScribeDictationWindow palette invocation."""

    def test_is_transform_hotkey_match(self):
        from pynput import keyboard

        # Ctrl + Alt + T
        current_keys = {keyboard.Key.ctrl, keyboard.Key.alt}
        key_t = keyboard.KeyCode.from_char("t")
        assert _is_transform_hotkey_match(current_keys, key_t) is True

        # Ctrl + Shift + T
        current_keys_shift = {keyboard.Key.ctrl, keyboard.Key.shift}
        assert _is_transform_hotkey_match(current_keys_shift, key_t) is True

        # Non-matching key (Ctrl + Alt + X)
        key_x = keyboard.KeyCode.from_char("x")
        assert _is_transform_hotkey_match(current_keys, key_x) is False

        # No modifiers (just 't')
        assert _is_transform_hotkey_match(set(), key_t) is False

    def test_window_opens_transform_palette(self, qapp):
        with (
            patch.object(ScribeDictationWindow, "_setup_global_hotkey"),
            patch.object(ScribeDictationWindow, "_setup_tray"),
            patch.object(ScribeDictationWindow, "_setup_transcriber"),
        ):
            window = ScribeDictationWindow()

        with patch(
            "scribe_dictation.ui.app.grab_selected_text",
            return_value="Selected sample text",
        ):
            window._open_transform_palette()

            assert window.transform_palette is not None
            assert window.transform_palette.get_text() == "Selected sample text"
            assert window.transform_palette.isVisible()

            window.transform_palette.dismiss()
