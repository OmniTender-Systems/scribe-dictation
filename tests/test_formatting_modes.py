"""Unit tests for formatting modes, rule cleaners, and FormatEngine."""

from unittest.mock import MagicMock
import pytest

from scribe_dictation.formatters.modes import (
    FormatEngine,
    RAW_MODE,
    CLEAN_MODE,
    BULLETS_MODE,
    MEETING_NOTES_MODE,
    EMAIL_MODE,
    CODE_COMMENT_MODE,
    BUILTIN_MODES,
    clean_filler_words,
    clean_stutters,
    clean_numbers,
    clean_punctuation_and_capitalization,
)


class TestRuleCleaners:
    """Test offline rule-based cleaner functions."""

    def test_clean_filler_words(self):
        sample = "Um, so like, we should basically, uh, complete this task, you know?"
        cleaned = clean_filler_words(sample)
        assert "um" not in cleaned.lower()
        assert "like" not in cleaned.lower()
        assert "basically" not in cleaned.lower()
        assert "you know" not in cleaned.lower()
        assert "uh" not in cleaned.lower()
        assert "we should complete this task" in cleaned

    def test_clean_stutters(self):
        sample = "The the quick brown fox jumps jumps over the lazy dog"
        cleaned = clean_stutters(sample)
        assert "The the" not in cleaned
        assert "jumps jumps" not in cleaned
        assert cleaned == "The quick brown fox jumps over the lazy dog"

    def test_clean_stutters_hyphenated(self):
        sample = "We need to go-go to the market"
        cleaned = clean_stutters(sample)
        assert cleaned == "We need to go to the market"

    def test_clean_numbers(self):
        sample = "I have three apples and two oranges plus five pears"
        cleaned = clean_numbers(sample)
        assert cleaned == "I have 3 apples and 2 oranges plus 5 pears"

    def test_clean_punctuation_and_capitalization(self):
        sample = "hello world. this is a test"
        cleaned = clean_punctuation_and_capitalization(sample)
        assert cleaned == "Hello world. This is a test."

    def test_empty_string_cleaners(self):
        assert clean_filler_words("") == ""
        assert clean_stutters("") == ""
        assert clean_numbers("") == ""
        assert clean_punctuation_and_capitalization("") == ""


class TestBuiltinModes:
    """Test built-in mode definitions and attributes."""

    def test_all_builtin_modes_registered(self):
        expected_ids = {
            "raw",
            "clean",
            "bullets",
            "meeting_notes",
            "email",
            "code_comment",
        }
        assert set(BUILTIN_MODES.keys()) == expected_ids

    def test_raw_mode_properties(self):
        assert RAW_MODE.id == "raw"
        assert RAW_MODE.is_pro is False
        assert len(RAW_MODE.rule_cleaners) == 0
        assert RAW_MODE.system_prompt == ""

    def test_clean_mode_properties(self):
        assert CLEAN_MODE.id == "clean"
        assert CLEAN_MODE.is_pro is False
        assert len(CLEAN_MODE.rule_cleaners) > 0
        assert "filler" in CLEAN_MODE.system_prompt.lower()

    def test_pro_modes(self):
        for mode in [BULLETS_MODE, MEETING_NOTES_MODE, EMAIL_MODE, CODE_COMMENT_MODE]:
            assert mode.is_pro is True
            assert mode.system_prompt != ""


class TestFormatEngine:
    """Test FormatEngine behavior with rule cleaners, offline fallbacks, and LLM mocks."""

    @pytest.fixture
    def engine(self):
        return FormatEngine()

    def test_get_mode_by_id_or_object(self, engine):
        assert engine.get_mode("raw") == RAW_MODE
        assert engine.get_mode("RAW") == RAW_MODE
        assert engine.get_mode("bullets") == BULLETS_MODE
        assert engine.get_mode(CLEAN_MODE) == CLEAN_MODE

        with pytest.raises(ValueError, match="Unknown formatting mode"):
            engine.get_mode("nonexistent_mode")

    def test_clean_rule_based(self, engine):
        text = "Um, the the meeting is at two pm"
        # Clean mode applies stutters and filler removal
        cleaned = engine.clean_rule_based(text, CLEAN_MODE)
        assert "um" not in cleaned.lower()
        assert "the the" not in cleaned.lower()
        assert "The meeting is at two pm." == cleaned

    def test_format_raw_mode(self, engine):
        text = "Um, uh, hello world"
        result = engine.format(text, mode=RAW_MODE)
        assert result == text

    def test_format_empty_or_whitespace(self, engine):
        assert engine.format("") == ""
        assert engine.format("   ") == "   "

    def test_format_clean_mode_offline_fallback(self, engine):
        text = "um, hello this is a test, you know"
        result = engine.format(text, mode=CLEAN_MODE, use_llm=False)
        assert "um" not in result.lower()
        assert "you know" not in result.lower()
        assert result.startswith("Hello this is a test")

    def test_format_bullets_offline_fallback(self, engine):
        text = "First task is to review the code. Second task is to run the tests."
        result = engine.format(text, mode=BULLETS_MODE, use_llm=False)
        lines = result.strip().splitlines()
        assert len(lines) == 2
        assert lines[0].startswith("- First task")
        assert lines[1].startswith("- Second task")

    def test_format_meeting_notes_offline_fallback(self, engine):
        text = "Discussed Q3 goals with the leadership team."
        result = engine.format(text, mode=MEETING_NOTES_MODE, use_llm=False)
        assert "### Summary" in result
        assert "### Key Decisions" in result
        assert "### Action Items" in result
        assert "Discussed Q3 goals" in result

    def test_format_email_offline_fallback(self, engine):
        text = "Please send over the updated financial spreadsheet by Friday."
        result = engine.format(text, mode=EMAIL_MODE, use_llm=False)
        assert "Subject:" in result
        assert "Hi there," in result
        assert "Best regards," in result
        assert "financial spreadsheet" in result

    def test_format_code_comment_offline_fallback(self, engine):
        text = "Compute the hash of input data using sha256."
        result = engine.format(text, mode=CODE_COMMENT_MODE, use_llm=False)
        assert result.startswith('"""')
        assert result.endswith('"""')
        assert "Compute the hash" in result

    def test_format_with_custom_llm_client(self):
        def custom_llm(prompt: str, text: str) -> str:
            return "* Point 1\n* Point 2"

        engine = FormatEngine(llm_client=custom_llm)
        text = "Um, point one and point two"
        result = engine.format(text, mode=BULLETS_MODE, use_llm=True)

        assert result == "* Point 1\n* Point 2"

    def test_format_with_openai_client_mock(self):
        mock_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "Subject: Hello\n\nBody"
        mock_response = MagicMock(choices=[mock_choice])
        mock_client.chat.completions.create.return_value = mock_response

        engine = FormatEngine(llm_client=mock_client)
        result = engine.format("hello test email", mode=EMAIL_MODE, use_llm=True)

        assert result == "Subject: Hello\n\nBody"
        mock_client.chat.completions.create.assert_called_once()
