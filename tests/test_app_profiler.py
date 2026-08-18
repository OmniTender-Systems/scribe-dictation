import os
import sys
from unittest.mock import patch

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from scribe_dictation.formatters import (
    AppProfile,
    AppProfileManager,
    DEFAULT_APP_PROFILES,
    detect_active_window,
)
from scribe_dictation.ui import app as app_module
from scribe_dictation.ui.app import ScribeDictationWindow
from scribe_dictation.ui.profiles_dialog import ProfilesDialog


@pytest.fixture
def qapp():
    """Provide a QApplication using the offscreen platform for headless tests."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    yield instance


# ---------------------------------------------------------------------------
# AppProfile Dataclass Tests
# ---------------------------------------------------------------------------


class TestAppProfileDataclass:
    """Test AppProfile dataclass creation, defaults, and serialization."""

    def test_app_profile_init_and_defaults(self):
        prof = AppProfile(app_identifier="code.exe", mode_id="code_comment")
        assert prof.app_identifier == "code.exe"
        assert prof.mode_id == "code_comment"
        assert prof.enabled is True
        assert prof.description == ""
        assert prof.match_type == "process"

    def test_app_profile_serialization_roundtrip(self):
        prof = AppProfile(
            app_identifier="slack.exe",
            mode_id="clean",
            enabled=False,
            description="Slack Client",
            match_type="process",
        )
        d = prof.to_dict()
        assert d == {
            "app_identifier": "slack.exe",
            "mode_id": "clean",
            "enabled": False,
            "description": "Slack Client",
            "match_type": "process",
        }
        restored = AppProfile.from_dict(d)
        assert restored == prof


# ---------------------------------------------------------------------------
# AppProfileManager Built-in Defaults & Rule Resolution
# ---------------------------------------------------------------------------


class TestAppProfileManagerRules:
    """Test standard application resolution rules."""

    @pytest.fixture
    def manager(self):
        return AppProfileManager(settings=None, enabled=True, fallback_mode="raw")

    def test_default_mappings_match_spec(self, manager):
        # Code editors / IDEs -> code_comment
        assert manager.resolve_mode(process_name="code.exe") == "code_comment"
        assert manager.resolve_mode(process_name="cursor.exe") == "code_comment"
        assert manager.resolve_mode(process_name="pycharm64.exe") == "code_comment"
        assert manager.resolve_mode(process_name="idea64.exe") == "code_comment"
        assert manager.resolve_mode(process_name="devenv.exe") == "code_comment"
        assert manager.resolve_mode(process_name="windsurf.exe") == "code_comment"

        # Email clients -> email
        assert manager.resolve_mode(process_name="outlook.exe") == "email"
        assert manager.resolve_mode(process_name="thunderbird.exe") == "email"
        assert manager.resolve_mode(process_name="mail.exe") == "email"

        # Chat / messaging -> clean
        assert manager.resolve_mode(process_name="slack.exe") == "clean"
        assert manager.resolve_mode(process_name="discord.exe") == "clean"
        assert manager.resolve_mode(process_name="teams.exe") == "clean"
        assert manager.resolve_mode(process_name="ms-teams.exe") == "clean"

        # Document & Notes -> meeting_notes or bullets
        assert manager.resolve_mode(process_name="winword.exe") == "meeting_notes"
        assert manager.resolve_mode(process_name="notion.exe") == "meeting_notes"
        assert manager.resolve_mode(process_name="obsidian.exe") == "bullets"

        # Unknown -> fallback
        assert manager.resolve_mode(process_name="calc.exe") == "raw"
        assert manager.resolve_mode(process_name="explorer.exe") == "raw"

    def test_case_insensitivity_and_extension_stripping(self, manager):
        assert manager.resolve_mode(process_name="CODE.EXE") == "code_comment"
        assert manager.resolve_mode(process_name="Cursor") == "code_comment"
        assert manager.resolve_mode(process_name="OUTLOOK.EXE") == "email"
        assert manager.resolve_mode(process_name="Slack") == "clean"

    def test_window_title_matching(self, manager):
        # Even if process_name is generic, window title matching should resolve
        assert (
            manager.resolve_mode(window_title="main.py - Visual Studio Code")
            == "code_comment"
        )
        assert manager.resolve_mode(window_title="Inbox - Microsoft Outlook") == "email"
        assert manager.resolve_mode(window_title="#general - Slack") == "clean"

    def test_disabled_manager_returns_fallback(self, manager):
        manager.enabled = False
        manager.fallback_mode = "clean"
        assert manager.resolve_mode(process_name="code.exe") == "clean"

    def test_regex_matching_profile(self, manager):
        manager.add_profile(
            r".*python.*", "code_comment", enabled=True, match_type="regex"
        )
        assert manager.resolve_mode(process_name="pythonw.exe") == "code_comment"
        assert (
            manager.resolve_mode(window_title="Editing python script") == "code_comment"
        )


# ---------------------------------------------------------------------------
# AppProfileManager CRUD Operations
# ---------------------------------------------------------------------------


class TestAppProfileManagerCRUD:
    """Test CRUD operations on AppProfileManager."""

    @pytest.fixture
    def manager(self):
        return AppProfileManager(settings=None, enabled=True)

    def test_add_and_get_profile(self, manager):
        prof = manager.add_profile(
            "custom_editor.exe", "code_comment", True, "My Custom Editor"
        )
        assert prof.app_identifier == "custom_editor.exe"
        assert prof.mode_id == "code_comment"

        retrieved = manager.get_profile("CUSTOM_EDITOR.EXE")
        assert retrieved is not None
        assert retrieved.app_identifier == "custom_editor.exe"

    def test_update_existing_profile(self, manager):
        manager.add_profile("custom.exe", "clean")
        assert manager.resolve_mode(process_name="custom.exe") == "clean"

        # Update mode
        manager.add_profile("custom.exe", "email")
        assert manager.resolve_mode(process_name="custom.exe") == "email"

    def test_remove_profile(self, manager):
        assert manager.get_profile("code.exe") is not None
        assert manager.remove_profile("code.exe") is True
        assert manager.get_profile("code.exe") is None
        assert manager.remove_profile("nonexistent.exe") is False

    def test_set_profile_enabled(self, manager):
        assert manager.set_profile_enabled("code.exe", False) is True
        prof = manager.get_profile("code.exe")
        assert prof.enabled is False
        # When disabled, should not match and fall back to fallback_mode
        assert manager.resolve_mode(process_name="code.exe") == manager.fallback_mode

    def test_set_profile_mode(self, manager):
        assert manager.set_profile_mode("code.exe", "bullets") is True
        assert manager.resolve_mode(process_name="code.exe") == "bullets"

    def test_reset_to_defaults(self, manager):
        manager.remove_profile("code.exe")
        manager.add_profile("test_app.exe", "bullets")
        assert manager.get_profile("code.exe") is None

        manager.reset_to_defaults()
        assert manager.get_profile("code.exe") is not None
        assert manager.get_profile("test_app.exe") is None


# ---------------------------------------------------------------------------
# Serialization & QSettings Persistence Tests
# ---------------------------------------------------------------------------


class TestAppProfilePersistence:
    """Test JSON serialization and QSettings storage."""

    def test_json_roundtrip(self):
        mgr1 = AppProfileManager(settings=None, enabled=False, fallback_mode="clean")
        mgr1.add_profile("myapp.exe", "email", description="Test App")
        json_data = mgr1.to_json()

        mgr2 = AppProfileManager(settings=None)
        mgr2.from_json(json_data)
        assert mgr2.enabled is False
        assert mgr2.fallback_mode == "clean"
        assert mgr2.get_profile("myapp.exe") is not None
        assert mgr2.get_profile("myapp.exe").mode_id == "email"

    def test_from_json_corrupt_or_empty_falls_back_to_defaults(self):
        mgr = AppProfileManager(settings=None)
        mgr.from_json("")
        assert len(mgr.profiles) == len(DEFAULT_APP_PROFILES)

        mgr.from_json("invalid json {[")
        assert len(mgr.profiles) == len(DEFAULT_APP_PROFILES)

    def test_qsettings_persistence(self, qapp):
        settings = QSettings("PrivacyScribeTest", "AppProfilerTest")
        settings.clear()

        mgr1 = AppProfileManager(settings=settings, enabled=True, fallback_mode="clean")
        mgr1.add_profile("persisted_app.exe", "bullets", description="Persisted")
        mgr1.save_to_settings(settings)

        mgr2 = AppProfileManager(settings=settings)
        assert mgr2.enabled is True
        assert mgr2.fallback_mode == "clean"
        assert mgr2.get_profile("persisted_app.exe") is not None
        assert mgr2.get_profile("persisted_app.exe").mode_id == "bullets"
        settings.clear()


# ---------------------------------------------------------------------------
# Foreground Window Detection Mocking Tests
# ---------------------------------------------------------------------------


class TestWindowDetection:
    """Test foreground window and process detection across platforms."""

    def test_detect_active_window_windows_mock(self):
        with patch("sys.platform", "win32"):
            with patch(
                "scribe_dictation.formatters.app_profiler._detect_active_window_windows",
                return_value=("code.exe", "main.py - VS Code"),
            ):
                proc, title = detect_active_window(12345)
                assert proc == "code.exe"
                assert title == "main.py - VS Code"

    def test_detect_active_window_macos_mock(self):
        with patch("sys.platform", "darwin"):
            with patch(
                "scribe_dictation.formatters.app_profiler._detect_active_window_macos",
                return_value=("Slack", "Slack - general"),
            ):
                proc, title = detect_active_window()
                assert proc == "Slack"
                assert title == "Slack - general"

    def test_detect_active_window_linux_mock(self):
        with patch("sys.platform", "linux"):
            with patch(
                "scribe_dictation.formatters.app_profiler._detect_active_window_linux",
                return_value=("gnome-terminal", "Terminal"),
            ):
                proc, title = detect_active_window()
                assert proc == "gnome-terminal"
                assert title == "Terminal"

    def test_detect_active_window_unknown_platform(self):
        with patch("sys.platform", "freebsd"):
            proc, title = detect_active_window()
            assert proc is None
            assert title is None


# ---------------------------------------------------------------------------
# UI ProfilesDialog Tests
# ---------------------------------------------------------------------------


class TestProfilesDialogUI:
    """Test UI dialog for managing profiles and smart detection."""

    def test_dialog_init_and_table_population(self, qapp):
        mgr = AppProfileManager(settings=None)
        dialog = ProfilesDialog(mgr)

        assert dialog.table.rowCount() == len(mgr.profiles)
        assert dialog.enable_check.isChecked() == mgr.enabled
        assert dialog.fallback_combo.currentData() == mgr.fallback_mode

    def test_dialog_toggle_enabled_and_fallback(self, qapp):
        mgr = AppProfileManager(settings=None, enabled=True)
        dialog = ProfilesDialog(mgr)

        dialog.enable_check.setChecked(False)
        assert mgr.enabled is False

        dialog.fallback_combo.setCurrentIndex(dialog.fallback_combo.findData("clean"))
        assert mgr.fallback_mode == "clean"

    def test_dialog_add_profile_flow(self, qapp):
        mgr = AppProfileManager(settings=None)
        dialog = ProfilesDialog(mgr)

        dialog.app_input.setText("new_tool.exe")
        dialog.desc_input.setText("Brand New Tool")
        dialog.mode_combo.setCurrentIndex(dialog.mode_combo.findData("bullets"))
        dialog._add_profile()

        prof = mgr.get_profile("new_tool.exe")
        assert prof is not None
        assert prof.mode_id == "bullets"
        assert prof.description == "Brand New Tool"

    def test_dialog_detect_active_window_flow(self, qapp):
        mgr = AppProfileManager(settings=None)
        dialog = ProfilesDialog(mgr)

        with patch(
            "scribe_dictation.ui.profiles_dialog.detect_active_window",
            return_value=("pycharm64.exe", "test.py"),
        ):
            dialog._detect_current_window()
            assert dialog.app_input.text() == "pycharm64.exe"
            assert "test.py" in dialog.desc_input.text()

    def test_dialog_remove_selected_flow(self, qapp):
        mgr = AppProfileManager(settings=None)
        dialog = ProfilesDialog(mgr)

        initial_count = dialog.table.rowCount()
        dialog.table.setCurrentCell(0, 1)
        dialog._remove_selected()
        assert dialog.table.rowCount() == initial_count - 1


# ---------------------------------------------------------------------------
# ScribeDictationWindow App Profiling Integration Tests
# ---------------------------------------------------------------------------


class TestAppProfilingIntegrationInWindow:
    """Test dynamic context detection in ScribeDictationWindow."""

    def test_window_app_profile_resolution_code_comment(self, qapp):
        with (
            patch.object(ScribeDictationWindow, "_setup_global_hotkey"),
            patch.object(ScribeDictationWindow, "_setup_tray"),
            patch.object(ScribeDictationWindow, "_setup_transcriber"),
            patch.object(ScribeDictationWindow, "_is_pro", return_value=True),
            patch.object(app_module, "_copy_to_clipboard"),
            patch.object(app_module, "_simulate_paste"),
        ):
            window = ScribeDictationWindow()
            window._target_process = "code.exe"
            window._target_title = "server.py - Visual Studio Code"

            raw_text = "um, compute the sha256 checksum of the file"
            window._on_transcription_complete(raw_text)

            displayed_text = window.text_display.toPlainText()
            # Code comment mode should wrap in docstrings
            assert displayed_text.startswith('"""')
            assert displayed_text.endswith('"""')
            assert "compute the sha256 checksum" in displayed_text

    def test_window_app_profile_resolution_email(self, qapp):
        with (
            patch.object(ScribeDictationWindow, "_setup_global_hotkey"),
            patch.object(ScribeDictationWindow, "_setup_tray"),
            patch.object(ScribeDictationWindow, "_setup_transcriber"),
            patch.object(ScribeDictationWindow, "_is_pro", return_value=True),
            patch.object(app_module, "_copy_to_clipboard"),
            patch.object(app_module, "_simulate_paste"),
        ):
            window = ScribeDictationWindow()
            window._target_process = "outlook.exe"
            window._target_title = "New Email - Outlook"

            raw_text = "Please submit your weekly report by end of day Friday."
            window._on_transcription_complete(raw_text)

            displayed_text = window.text_display.toPlainText()
            # Email mode offline fallback template
            assert "Subject:" in displayed_text
            assert "Hi there," in displayed_text
            assert "weekly report" in displayed_text
