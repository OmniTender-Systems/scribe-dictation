"""Unit tests for verbal punctuation and formatting commands parser."""

import pytest
from scribe_dictation.formatters.verbal_commands import (
    VerbalCommandParser,
    parse_verbal_commands,
)
from scribe_dictation.formatters.modes import FormatEngine, RAW_MODE, CLEAN_MODE


class TestPunctuationCommands:
    """Test all spoken punctuation marks and symbols."""

    @pytest.fixture
    def parser(self):
        return VerbalCommandParser(enabled=True)

    def test_period_and_full_stop(self, parser):
        assert parser.parse("Hello world period") == "Hello world."
        assert parser.parse("Hello world full stop") == "Hello world."
        assert (
            parser.parse("First thought period second thought period")
            == "First thought. Second thought."
        )

    def test_comma(self, parser):
        assert (
            parser.parse("Apples comma oranges comma and bananas")
            == "Apples, oranges, and bananas"
        )

    def test_question_mark(self, parser):
        assert parser.parse("How are you question mark") == "How are you?"
        assert (
            parser.parse("What is your name question mark where are you from")
            == "What is your name? Where are you from"
        )

    def test_exclamation_mark_and_point(self, parser):
        assert parser.parse("Look out exclamation mark") == "Look out!"
        assert parser.parse("Watch out exclamation point") == "Watch out!"

    def test_colon_and_semicolon(self, parser):
        assert (
            parser.parse("Note colon take action semicolon immediately")
            == "Note: take action; immediately"
        )

    def test_quotes(self, parser):
        text = parser.parse("She said open quote hello world close quote")
        assert text == 'She said "hello world"'

        single_text = parser.parse("He said open single quote yes close single quote")
        assert "'" in single_text

    def test_parentheses(self, parser):
        text = parser.parse(
            "Estimated cost open parenthesis roughly 50 close parenthesis"
        )
        assert text == "Estimated cost (roughly 50)"

        paren_short = parser.parse("Total open paren 100 close paren")
        assert paren_short == "Total (100)"

    def test_hyphen_and_dash(self, parser):
        assert (
            parser.parse("State hyphen of hyphen the hyphen art") == "State-of-the-art"
        )
        assert parser.parse("Well dash known") == "Well-known"

    def test_ellipsis(self, parser):
        assert parser.parse("To be continued ellipsis") == "To be continued..."
        assert parser.parse("Waiting dot dot dot") == "Waiting..."

    def test_symbols(self, parser):
        assert parser.parse(
            "Contact me at sign company dot com"
        ) == "Contact me @ company. Com" or "@" in parser.parse(
            "Contact me at sign company"
        )
        assert parser.parse("Search hashtag tech") == "Search #tech"
        assert parser.parse("Price was dollar sign 50") == "Price was $50"
        assert parser.parse("Discount of 20 percent sign") == "Discount of 20%"


class TestStructuralCommands:
    """Test structural formatting commands (newlines, paragraphs, bullets, tabs)."""

    @pytest.fixture
    def parser(self):
        return VerbalCommandParser(enabled=True)

    def test_new_line(self, parser):
        text = parser.parse("First line new line second line")
        assert text == "First line\nSecond line" or text == "First line\nsecond line"
        assert "\n" in text

    def test_new_paragraph(self, parser):
        text = parser.parse("First paragraph new paragraph second paragraph")
        assert "\n\n" in text
        assert "First paragraph\n\nSecond paragraph" in text

    def test_bullet_points(self, parser):
        text = parser.parse("bullet point first item next bullet second item")
        assert "• " in text
        lines = text.splitlines()
        assert any(line.startswith("• ") for line in lines)

    def test_tab(self, parser):
        text = parser.parse("Item tab indented content")
        assert "\t" in text


class TestCasingCommands:
    """Test casing commands (all caps, capitalize)."""

    @pytest.fixture
    def parser(self):
        return VerbalCommandParser(enabled=True)

    def test_all_caps_delimited(self, parser):
        text = parser.parse("This is all caps very important end all caps right now")
        assert "VERY IMPORTANT" in text
        assert "all caps" not in text.lower()

    def test_all_caps_word(self, parser):
        text = parser.parse("This is all caps urgent")
        assert "URGENT" in text

    def test_capitalize_word(self, parser):
        text = parser.parse("my name is capitalize john")
        assert "John" in text


class TestFalsePositiveGuardrails:
    """Test context-aware guardrails preventing natural speech corruption."""

    @pytest.fixture
    def parser(self):
        return VerbalCommandParser(enabled=True)

    def test_period_of_time_guardrail(self, parser):
        sample = "We worked there for a period of time"
        assert parser.parse(sample) == "We worked there for a period of time"

        sample2 = "During this grace period of 30 days"
        assert "grace period of" in parser.parse(sample2)

    def test_comma_separated_guardrail(self, parser):
        sample = "Please return comma-separated values"
        assert parser.parse(sample) == "Please return comma-separated values"

        sample2 = "Use comma separated list"
        assert "comma separated" in parser.parse(sample2)

    def test_question_mark_guardrail(self, parser):
        sample = "She has a question mark over her head"
        assert parser.parse(sample) == "She has a question mark over her head"

        sample2 = "There is a big question mark regarding the budget"
        assert "question mark regarding" in parser.parse(sample2)

    def test_exclamation_mark_guardrail(self, parser):
        sample = "He saw an exclamation mark on the sign"
        assert parser.parse(sample) == "He saw an exclamation mark on the sign"

    def test_colon_medical_guardrail(self, parser):
        sample = "He was scheduled for colon screening and colon surgery"
        assert "colon screening" in parser.parse(sample)
        assert "colon surgery" in parser.parse(sample)

    def test_dollar_sign_noun_guardrail(self, parser):
        sample = "There is a dollar sign on the bill"
        assert "a dollar sign on the bill" in parser.parse(sample)

    def test_hashtag_noun_guardrail(self, parser):
        sample = "Search for the trending hashtag on social media"
        assert "trending hashtag" in parser.parse(sample)


class TestParserToggleAndIntegration:
    """Test toggle enable/disable functionality and FormatEngine integration."""

    def test_disabled_parser_returns_raw(self):
        parser = VerbalCommandParser(enabled=False)
        assert (
            parser.parse("Hello period new line world") == "Hello period new line world"
        )

    def test_convenience_function(self):
        assert parse_verbal_commands("Hello period", enabled=True) == "Hello."
        assert parse_verbal_commands("Hello period", enabled=False) == "Hello period"

    def test_format_engine_integration_raw_mode(self):
        engine = FormatEngine(verbal_commands_enabled=True)
        assert engine.format("Hello world period", mode=RAW_MODE) == "Hello world."

        disabled_engine = FormatEngine(verbal_commands_enabled=False)
        assert (
            disabled_engine.format("Hello world period", mode=RAW_MODE)
            == "Hello world period"
        )

    def test_format_engine_integration_clean_mode(self):
        engine = FormatEngine(verbal_commands_enabled=True)
        result = engine.format(
            "Um hello world period next bullet item one", mode=CLEAN_MODE, use_llm=False
        )
        assert "Hello world." in result
        assert "• Item one" in result or "• item one" in result or "• " in result
