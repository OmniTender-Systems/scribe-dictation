"""Unit tests for Voice Snippets & Macro Expander Engine.

Tests:
- VoiceSnippet dataclass initialization and serialization
- Dynamic variable substitution ({date}, {time}, {clipboard}, {cursor}, {uuid})
- VoiceSnippetManager trigger detection, standalone and embedded expansions
- Priority sorting (longer trigger phrases first)
- JSON and QSettings persistence
- Built-in default starter templates
- SnippetsDialog UI interaction and live preview
- ScribeDictationWindow pipeline integration
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from scribe_dictation.formatters.snippets import (
    DEFAULT_VOICE_SNIPPETS,
    VoiceSnippet,
    VoiceSnippetManager,
    expand_variables,
    get_default_snippets_path,
)
from scribe_dictation.ui.snippets_dialog import SnippetsDialog


@pytest.fixture
def qapp():
    """Provide a QApplication using the offscreen platform for headless tests."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    yield instance


# ---------------------------------------------------------------------------
# 1. VoiceSnippet Dataclass Tests
# ---------------------------------------------------------------------------


class TestVoiceSnippetDataclass:
    """Test VoiceSnippet dataclass creation, defaults, and serialization."""

    def test_init_and_defaults(self):
        snippet = VoiceSnippet(
            trigger_phrase="insert signature",
            expansion_template="Best regards,\nAlice",
        )
        assert snippet.trigger_phrase == "insert signature"
        assert snippet.expansion_template == "Best regards,\nAlice"
        assert snippet.enabled is True
        assert snippet.description == ""

    def test_serialization_roundtrip(self):
        snippet = VoiceSnippet(
            trigger_phrase="meeting notes",
            expansion_template="# Notes\n- {date}",
            enabled=False,
            description="Team meeting boilerplate",
        )
        data = snippet.to_dict()
        assert data == {
            "trigger_phrase": "meeting notes",
            "expansion_template": "# Notes\n- {date}",
            "enabled": False,
            "description": "Team meeting boilerplate",
        }

        restored = VoiceSnippet.from_dict(data)
        assert restored == snippet


# ---------------------------------------------------------------------------
# 2. Variable Expansion Tests
# ---------------------------------------------------------------------------


class TestVariableExpansion:
    """Test dynamic variable substitutions in templates."""

    def test_expand_empty_template(self):
        assert expand_variables("") == ""

    def test_expand_date_and_time(self):
        dt = datetime(2026, 8, 17, 14, 30, 45)
        template = "Date: {date}, Time: {time}, Full: {datetime}"
        result = expand_variables(template, current_dt=dt)
        assert result == "Date: 2026-08-17, Time: 14:30:45, Full: 2026-08-17 14:30:45"

    def test_expand_case_insensitivity(self):
        dt = datetime(2026, 8, 17, 14, 30, 45)
        template = "Date: {DATE}, Time: {Time}"
        result = expand_variables(template, current_dt=dt)
        assert result == "Date: 2026-08-17, Time: 14:30:45"

    def test_expand_clipboard(self):
        template = "Quote: > {clipboard}"
        result = expand_variables(template, clipboard_text="copied data")
        assert result == "Quote: > copied data"

    def test_expand_cursor_preserved(self):
        template = "Title:\n{cursor}\nEnd"
        result = expand_variables(template)
        assert result == "Title:\n{cursor}\nEnd"

    def test_expand_uuid(self):
        template = "ID: {uuid}"
        result = expand_variables(template)
        assert result.startswith("ID: ")
        raw_uuid = result.replace("ID: ", "").strip()
        # Verify valid uuid4
        parsed = uuid.UUID(raw_uuid, version=4)
        assert str(parsed) == raw_uuid

    def test_expand_custom_vars(self):
        template = "Hello {name}, your role is {role} on {date}"
        dt = datetime(2026, 8, 17)
        result = expand_variables(
            template,
            current_dt=dt,
            custom_vars={"name": "Alice", "role": "Engineer"},
        )
        assert result == "Hello Alice, your role is Engineer on 2026-08-17"


# ---------------------------------------------------------------------------
# 3. VoiceSnippetManager Tests
# ---------------------------------------------------------------------------


class TestVoiceSnippetManager:
    """Test VoiceSnippetManager snippet CRUD, matching, and expansion."""

    def test_default_starter_snippets(self):
        manager = VoiceSnippetManager(auto_load=False)
        snippets = manager.get_snippets()
        assert len(snippets) == len(DEFAULT_VOICE_SNIPPETS)
        assert manager.get_snippet("insert signature") is not None
        assert manager.get_snippet("insert date") is not None
        assert manager.get_snippet("meeting notes template") is not None

    def test_add_and_update_snippet(self):
        manager = VoiceSnippetManager(auto_load=False)
        manager.clear_snippets()
        assert len(manager.get_snippets()) == 0

        # Add snippet
        added = manager.add_snippet(
            "my trigger", "Template output", True, "Test snippet"
        )
        assert added.trigger_phrase == "my trigger"
        assert len(manager.get_snippets()) == 1

        # Update existing snippet (case-insensitive trigger match)
        updated = manager.add_snippet("MY TRIGGER", "Updated template", True, "Updated")
        assert len(manager.get_snippets()) == 1
        assert updated.expansion_template == "Updated template"
        assert updated.description == "Updated"

    def test_remove_snippet(self):
        manager = VoiceSnippetManager(auto_load=False)
        assert manager.remove_snippet("insert signature") is True
        assert manager.get_snippet("insert signature") is None
        assert manager.remove_snippet("nonexistent trigger") is False

    def test_toggle_snippet_enabled(self):
        manager = VoiceSnippetManager(auto_load=False)
        assert manager.set_snippet_enabled("insert signature", False) is True
        snippet = manager.get_snippet("insert signature")
        assert snippet is not None
        assert snippet.enabled is False
        assert manager.set_snippet_enabled("unknown trigger", True) is False

    def test_reset_to_defaults(self):
        manager = VoiceSnippetManager(auto_load=False)
        manager.clear_snippets()
        assert len(manager.get_snippets()) == 0
        manager.reset_to_defaults(save_after=False)
        assert len(manager.get_snippets()) == len(DEFAULT_VOICE_SNIPPETS)

    # ── Expansion Engine Tests ──────────────────────────────────────────

    def test_whole_phrase_standalone_expansion(self):
        manager = VoiceSnippetManager(auto_load=False)
        manager.clear_snippets()
        manager.add_snippet("insert signature", "Best regards,\nAlice Smith")

        # Exact match
        assert manager.expand_text("insert signature") == "Best regards,\nAlice Smith"
        # Case variation
        assert manager.expand_text("INSERT SIGNATURE") == "Best regards,\nAlice Smith"
        # Trailing period / punctuation
        assert manager.expand_text("Insert signature.") == "Best regards,\nAlice Smith"
        assert manager.expand_text("insert signature!") == "Best regards,\nAlice Smith"
        assert (
            manager.expand_text("  insert signature?  ") == "Best regards,\nAlice Smith"
        )

    def test_embedded_trigger_expansion(self):
        manager = VoiceSnippetManager(auto_load=False)
        manager.clear_snippets()
        dt = datetime(2026, 8, 17)
        manager.add_snippet("insert date", "{date}")

        text = "Please log this record for insert date as scheduled."
        result = manager.expand_text(text, current_dt=dt)
        assert result == "Please log this record for 2026-08-17 as scheduled."

    def test_multiple_triggers_in_single_text(self):
        manager = VoiceSnippetManager(auto_load=False)
        manager.clear_snippets()
        dt = datetime(2026, 8, 17, 10, 15, 0)
        manager.add_snippet("insert date", "{date}")
        manager.add_snippet("insert time", "{time}")

        text = "Start at insert time on insert date."
        result = manager.expand_text(text, current_dt=dt)
        assert result == "Start at 10:15:00 on 2026-08-17."

    def test_longest_trigger_phrase_priority(self):
        manager = VoiceSnippetManager(auto_load=False)
        manager.clear_snippets()
        manager.add_snippet("insert date", "SHORT_DATE")
        manager.add_snippet("insert date today", "FULL_TODAY_DATE")

        # Spoken text containing longer trigger phrase
        text = "Please insert date today for the header"
        result = manager.expand_text(text)
        assert result == "Please FULL_TODAY_DATE for the header"

    def test_disabled_snippet_not_expanded(self):
        manager = VoiceSnippetManager(auto_load=False)
        manager.clear_snippets()
        manager.add_snippet("insert signature", "Signed", enabled=False)

        assert manager.expand_text("insert signature") == "insert signature"

    def test_globally_disabled_manager(self):
        manager = VoiceSnippetManager(auto_load=False, enabled=False)
        manager.clear_snippets()
        manager.add_snippet("insert signature", "Signed", enabled=True)

        assert manager.expand_text("insert signature") == "insert signature"

    def test_regex_special_characters_in_trigger(self):
        manager = VoiceSnippetManager(auto_load=False)
        manager.clear_snippets()
        manager.add_snippet("[todo item]", "- [ ] {cursor}")

        assert manager.expand_text("[todo item]") == "- [ ] {cursor}"
        assert manager.expand_text("Add [todo item] here") == "Add - [ ] {cursor} here"


# ---------------------------------------------------------------------------
# 4. Persistence Tests (JSON & QSettings)
# ---------------------------------------------------------------------------


class TestSnippetsPersistence:
    """Test JSON file and QSettings persistence."""

    def test_json_file_persistence_roundtrip(self, tmp_path):
        config_file = tmp_path / "snippets_test.json"
        manager = VoiceSnippetManager(config_path=config_file, auto_load=False)
        manager.clear_snippets()
        manager.add_snippet("custom trigger", "Expanded content", True, "My desc")
        manager.save()

        assert config_file.exists()
        with open(config_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            assert data["enabled"] is True
            assert len(data["snippets"]) == 1
            assert data["snippets"][0]["trigger_phrase"] == "custom trigger"

        # Load into a new manager instance
        manager2 = VoiceSnippetManager(config_path=config_file, auto_load=True)
        assert len(manager2.get_snippets()) == 1
        assert manager2.get_snippet("custom trigger") is not None
        assert (
            manager2.get_snippet("custom trigger").expansion_template
            == "Expanded content"
        )

    def test_qsettings_persistence_roundtrip(self, qapp):
        settings = QSettings("PrivacyScribeTest", "VoiceSnippetsTest")
        settings.clear()

        manager = VoiceSnippetManager(settings=settings, auto_load=False)
        manager.clear_snippets()
        manager.add_snippet("alpha trigger", "Alpha output", True, "Alpha")
        manager.enabled = False
        manager.save()

        # Load into new manager with same settings
        manager2 = VoiceSnippetManager(settings=settings, auto_load=True)
        assert manager2.enabled is False
        assert len(manager2.get_snippets()) == 1
        assert manager2.get_snippet("alpha trigger") is not None

        settings.clear()

    def test_get_default_snippets_path(self):
        path = get_default_snippets_path()
        assert isinstance(path, Path)
        assert path.name == "snippets.json"


# ---------------------------------------------------------------------------
# 5. SnippetsDialog UI Tests
# ---------------------------------------------------------------------------


class TestSnippetsDialogUI:
    """Test SnippetsDialog UI elements and interactions."""

    def test_dialog_init_and_table_population(self, qapp):
        manager = VoiceSnippetManager(auto_load=False)
        dialog = SnippetsDialog(manager)

        assert dialog.windowTitle() == "Voice Snippets & Macros — Privacy Scribe Pro"
        assert dialog.table.rowCount() == len(DEFAULT_VOICE_SNIPPETS)
        assert dialog.enable_check.isChecked() is True

    def test_dialog_selection_populates_editor(self, qapp):
        manager = VoiceSnippetManager(auto_load=False)
        dialog = SnippetsDialog(manager)

        # Select first row
        dialog.table.selectRow(0)
        first_snippet = manager.get_snippets()[0]
        assert dialog.trigger_input.text() == first_snippet.trigger_phrase
        assert dialog.template_edit.toPlainText() == first_snippet.expansion_template

    def test_dialog_insert_variable_pills(self, qapp):
        manager = VoiceSnippetManager(auto_load=False)
        dialog = SnippetsDialog(manager)

        dialog.template_edit.clear()
        dialog._insert_variable("{date}")
        dialog._insert_variable(" ")
        dialog._insert_variable("{time}")

        assert dialog.template_edit.toPlainText() == "{date} {time}"

    def test_dialog_live_preview_updates(self, qapp):
        manager = VoiceSnippetManager(auto_load=False)
        dialog = SnippetsDialog(manager)

        dialog.template_edit.setPlainText("Static preview text")
        assert dialog.preview_box.toPlainText() == "Static preview text"

    def test_dialog_add_snippet_via_form(self, qapp):
        manager = VoiceSnippetManager(auto_load=False)
        dialog = SnippetsDialog(manager)

        dialog.trigger_input.setText("new voice macro")
        dialog.desc_input.setText("New macro description")
        dialog.template_edit.setPlainText("Hello from new macro: {date}")

        dialog._save_snippet()

        assert manager.get_snippet("new voice macro") is not None
        assert dialog.table.rowCount() == len(DEFAULT_VOICE_SNIPPETS) + 1

    def test_dialog_toggle_master_enable(self, qapp):
        manager = VoiceSnippetManager(auto_load=False)
        dialog = SnippetsDialog(manager)

        dialog.enable_check.setChecked(False)
        assert manager.enabled is False

        dialog.enable_check.setChecked(True)
        assert manager.enabled is True


# ---------------------------------------------------------------------------
# 6. ScribeDictationWindow Pipeline Integration Tests
# ---------------------------------------------------------------------------


class TestAppPipelineIntegration:
    """Test voice snippets integration inside ScribeDictationWindow."""

    @patch("scribe_dictation.ui.app.is_offline_cache_valid", return_value=True)
    def test_app_has_snippet_manager_and_expands_text(self, mock_is_pro, qapp):
        from scribe_dictation.ui.app import ScribeDictationWindow

        window = ScribeDictationWindow()
        assert hasattr(window, "snippet_manager")
        assert isinstance(window.snippet_manager, VoiceSnippetManager)

        window.snippet_manager.clear_snippets()
        window.snippet_manager.add_snippet("insert signature", "Best regards,\nAlice")

        # Simulate transcription completion
        with (
            patch.object(window.capsule, "show_done"),
            patch("scribe_dictation.ui.app._copy_to_clipboard"),
            patch("scribe_dictation.ui.app._simulate_paste"),
        ):
            window._on_transcription_complete("insert signature")

        assert "Best regards,\nAlice" in window.text_display.toPlainText()
