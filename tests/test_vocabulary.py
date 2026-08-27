import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from scribe_dictation.transcribe.local import LocalWhisperService
from scribe_dictation.transcribe.service import TranscribeService
from scribe_dictation.transcribe.vocabulary import (
    CustomVocabularyManager,
    ReplacementRule,
    apply_replacements,
    build_initial_prompt,
    diff_corrections,
)


class TestReplacementRule:
    """Tests for individual ReplacementRule objects."""

    def test_init_defaults(self):
        rule = ReplacementRule(pattern="kube cuddle", replacement="kubectl")
        assert rule.pattern == "kube cuddle"
        assert rule.replacement == "kubectl"
        assert not rule.is_regex
        assert not rule.case_sensitive
        assert rule.word_boundary

    def test_serialization(self):
        rule = ReplacementRule(
            pattern=r"\bomni\s*tender\b",
            replacement="OmniTender",
            is_regex=True,
            case_sensitive=True,
            word_boundary=False,
        )
        data = rule.to_dict()
        assert data["pattern"] == r"\bomni\s*tender\b"
        assert data["replacement"] == "OmniTender"
        assert data["is_regex"] is True
        assert data["case_sensitive"] is True
        assert data["word_boundary"] is False

        restored = ReplacementRule.from_dict(data)
        assert restored == rule

    def test_exact_word_boundary_matching(self):
        rule = ReplacementRule(pattern="cat", replacement="dog")
        # Matches whole word
        assert rule.apply("the cat sat") == "the dog sat"
        # Does NOT match partial substring inside another word
        assert (
            rule.apply("the caterpillar concatenated") == "the caterpillar concatenated"
        )
        # Matches case-insensitively by default
        assert rule.apply("The CAT is here") == "The dog is here"

    def test_phrase_replacement(self):
        rule = ReplacementRule(pattern="kube cuddle", replacement="kubectl")
        text = "Please run kube cuddle get pods in production"
        assert rule.apply(text) == "Please run kubectl get pods in production"
        # Case variation
        assert rule.apply("Kube Cuddle get pods") == "kubectl get pods"

    def test_case_sensitive_rule(self):
        rule = ReplacementRule(
            pattern="API", replacement="Interface", case_sensitive=True
        )
        assert rule.apply("Call the API endpoint") == "Call the Interface endpoint"
        assert rule.apply("call the api endpoint") == "call the api endpoint"

    def test_regex_replacement(self):
        rule = ReplacementRule(
            pattern=r"\bomni[\s\-_]+tender\b",
            replacement="OmniTender",
            is_regex=True,
        )
        assert (
            rule.apply("Welcome to omni tender today") == "Welcome to OmniTender today"
        )
        assert (
            rule.apply("Welcome to omni-tender today") == "Welcome to OmniTender today"
        )
        assert (
            rule.apply("Welcome to omni_tender today") == "Welcome to OmniTender today"
        )

    def test_regex_replacement_with_groups(self):
        rule = ReplacementRule(
            pattern=r"chapter\s+(\d+)",
            replacement=r"Ch. \1",
            is_regex=True,
        )
        assert rule.apply("Read chapter 5 please") == "Read Ch. 5 please"

    def test_malformed_regex_fails_gracefully(self):
        rule = ReplacementRule(
            pattern="[unclosed-regex", replacement="test", is_regex=True
        )
        # Should not crash; returns original text
        assert rule.apply("some input text") == "some input text"

    def test_non_word_boundary_replacement(self):
        rule = ReplacementRule(pattern="pre", replacement="post", word_boundary=False)
        assert rule.apply("preview") == "postview"


class TestPromptBuilder:
    """Tests for build_initial_prompt dictionary biasing."""

    def test_empty_words_and_base(self):
        assert build_initial_prompt([]) == ""
        assert build_initial_prompt(None) == ""
        assert build_initial_prompt([], base_prompt="Medical notes") == "Medical notes"

    def test_single_and_multiple_words(self):
        prompt = build_initial_prompt(["Kubernetes", "kubectl", "OmniTender"])
        assert prompt == "Glossary: Kubernetes, kubectl, OmniTender."

    def test_deduplication_and_stripping(self):
        words = ["  Kubernetes ", "kubernetes", "KUBERNETES", "kubectl", "", "   "]
        prompt = build_initial_prompt(words)
        assert prompt == "Glossary: Kubernetes, kubectl."

    def test_combine_with_base_prompt(self):
        base = "General cardiology consultation."
        words = ["Echocardiogram", "arrhythmia"]
        prompt = build_initial_prompt(words, base_prompt=base)
        assert (
            prompt
            == "General cardiology consultation. Glossary: Echocardiogram, arrhythmia."
        )

    def test_base_prompt_without_trailing_period(self):
        base = "Dictation for Dr. Smith"
        words = ["MRI", "CT scan"]
        prompt = build_initial_prompt(words, base_prompt=base)
        assert prompt == "Dictation for Dr. Smith. Glossary: MRI, CT scan."

    def test_max_chars_truncation(self):
        words = ["TermOne", "TermTwo", "TermThree", "TermFour", "TermFive"]
        # Limit prompt to 35 chars
        prompt = build_initial_prompt(words, max_chars=35)
        assert len(prompt) <= 35
        assert prompt.startswith("Glossary:")
        assert "TermOne" in prompt


class TestApplyReplacements:
    """Tests for apply_replacements helper function."""

    def test_apply_multiple_rules_in_order(self):
        rules = [
            ReplacementRule(pattern="kube cuddle", replacement="kubectl"),
            ReplacementRule(pattern="doc er", replacement="Docker"),
            ReplacementRule(pattern="g k e", replacement="GKE"),
        ]
        raw = "Deploy to g k e using doc er and kube cuddle."
        cleaned = apply_replacements(raw, rules)
        assert cleaned == "Deploy to GKE using Docker and kubectl."

    def test_apply_with_empty_inputs(self):
        assert apply_replacements("", []) == ""
        assert apply_replacements("test", None) == "test"
        assert apply_replacements("test", []) == "test"

    def test_apply_with_dict_rules(self):
        rules_dict = [
            {
                "pattern": "pyside",
                "replacement": "PySide6",
                "is_regex": False,
                "word_boundary": True,
            }
        ]
        assert (
            apply_replacements("Learning pyside today", rules_dict)
            == "Learning PySide6 today"
        )


class TestCustomVocabularyManager:
    """Tests for CustomVocabularyManager."""

    def test_init_in_memory(self):
        mgr = CustomVocabularyManager(
            words=["Kubernetes", "PySide6"],
            replacements=[
                ReplacementRule(pattern="kube cuddle", replacement="kubectl")
            ],
            auto_load=False,
        )
        assert mgr.get_words() == ["Kubernetes", "PySide6"]
        rules = mgr.get_replacements()
        assert len(rules) == 1
        assert rules[0].pattern == "kube cuddle"

    def test_add_and_remove_words(self):
        mgr = CustomVocabularyManager(auto_load=False)
        assert mgr.add_word("FastAPI") is True
        assert mgr.add_word("fastapi") is False  # Duplicate ignored
        assert mgr.add_word("   ") is False  # Empty ignored
        assert mgr.get_words() == ["FastAPI"]

        assert mgr.add_word("PostgreSQL") is True
        assert len(mgr.get_words()) == 2

        assert mgr.remove_word("FASTAPI") is True  # Case-insensitive removal
        assert mgr.get_words() == ["PostgreSQL"]
        assert mgr.remove_word("NonExistent") is False

    def test_set_and_clear_words(self):
        mgr = CustomVocabularyManager(auto_load=False)
        mgr.set_words(["Alpha", "Beta", "alpha", "Gamma"])
        assert mgr.get_words() == ["Alpha", "Beta", "Gamma"]

        mgr.clear_words()
        assert mgr.get_words() == []

    def test_add_and_remove_replacements(self):
        mgr = CustomVocabularyManager(auto_load=False)
        rule1 = mgr.add_replacement("kube cuddle", "kubectl")
        assert rule1.pattern == "kube cuddle"
        assert len(mgr.get_replacements()) == 1

        # Overwrite/update same pattern
        mgr.add_replacement("kube cuddle", "kubectl v2")
        assert len(mgr.get_replacements()) == 1
        assert mgr.get_replacements()[0].replacement == "kubectl v2"

        assert mgr.remove_replacement("kube cuddle") is True
        assert mgr.get_replacements() == []
        assert mgr.remove_replacement("kube cuddle") is False

    def test_prompt_generation_and_replacement(self):
        mgr = CustomVocabularyManager(
            words=["OmniTender", "Kubernetes"],
            replacements=[
                ReplacementRule("omni tender", "OmniTender"),
                ReplacementRule("kube cuddle", "kubectl"),
            ],
            auto_load=False,
        )
        prompt = mgr.build_initial_prompt(base_prompt="Deployment notes.")
        assert prompt == "Deployment notes. Glossary: OmniTender, Kubernetes."

        raw_text = "We configured omni tender and ran kube cuddle."
        cleaned = mgr.apply_replacements(raw_text)
        assert cleaned == "We configured OmniTender and ran kubectl."

    def test_json_persistence(self, tmp_path: Path):
        cfg_file = tmp_path / "custom_vocab.json"
        mgr1 = CustomVocabularyManager(
            words=["FastAPI", "SQLite"],
            replacements=[ReplacementRule("fast api", "FastAPI")],
            config_path=cfg_file,
            base_prompt="System instructions.",
            auto_load=False,
        )
        mgr1.save()

        assert cfg_file.exists()
        with open(cfg_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["words"] == ["FastAPI", "SQLite"]
        assert data["base_prompt"] == "System instructions."
        assert len(data["replacements"]) == 1

        # Load into new manager
        mgr2 = CustomVocabularyManager(config_path=cfg_file, auto_load=True)
        assert mgr2.get_words() == ["FastAPI", "SQLite"]
        assert len(mgr2.get_replacements()) == 1
        assert mgr2.get_replacements()[0].pattern == "fast api"
        assert (
            mgr2.build_initial_prompt()
            == "System instructions. Glossary: FastAPI, SQLite."
        )

    def test_qsettings_persistence(self):
        # Mock QSettings
        storage = {}

        class MockSettings:
            def setValue(self, key, value):
                storage[key] = value

            def value(self, key, default=None):
                return storage.get(key, default)

            def sync(self):
                pass

        mock_settings = MockSettings()
        mgr = CustomVocabularyManager(settings=mock_settings, auto_load=False)
        mgr.set_words(["Docker", "Podman"])
        mgr.add_replacement("doc er", "Docker")
        mgr.save()

        assert "custom_vocabulary_words" in storage
        assert "custom_vocabulary_rules" in storage

        # Restore from mock settings
        mgr_restored = CustomVocabularyManager(settings=mock_settings, auto_load=True)
        assert mgr_restored.get_words() == ["Docker", "Podman"]
        assert len(mgr_restored.get_replacements()) == 1
        assert mgr_restored.get_replacements()[0].pattern == "doc er"


class TestLocalWhisperServiceIntegration:
    """Tests for LocalWhisperService with vocabulary biasing and replacements."""

    def test_local_service_initial_prompt_building(self):
        mgr = CustomVocabularyManager(
            words=["OmniTender", "Kubernetes"],
            base_prompt="Base notes.",
            auto_load=False,
        )
        service = LocalWhisperService(vocabulary_manager=mgr)
        prompt = service.get_initial_prompt()
        assert prompt == "Base notes. Glossary: OmniTender, Kubernetes."

        # Override prompt
        override = service.get_initial_prompt("Extra context.")
        assert override == "Extra context. Glossary: OmniTender, Kubernetes."

    def test_local_service_transcribe_applies_replacements(self, tmp_path: Path):
        fake_wav = tmp_path / "audio.wav"
        fake_wav.write_bytes(b"RIFF....WAVE")

        mgr = CustomVocabularyManager(
            words=["OmniTender", "kubectl"],
            replacements=[
                ReplacementRule("omni tender", "OmniTender"),
                ReplacementRule("kube cuddle", "kubectl"),
            ],
            auto_load=False,
        )

        mock_segment1 = MagicMock()
        mock_segment1.text = " Welcome to omni tender "
        mock_segment1.start = 0.0
        mock_segment1.end = 2.5

        mock_segment2 = MagicMock()
        mock_segment2.text = " please run kube cuddle "
        mock_segment2.start = 2.5
        mock_segment2.end = 5.0

        service = LocalWhisperService(vocabulary_manager=mgr)
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (
            [mock_segment1, mock_segment2],
            MagicMock(),
        )
        service._model = mock_model

        # Synchronous transcribe
        result = service.transcribe(fake_wav)
        assert result == "Welcome to OmniTender  please run kubectl"

        # Verify initial_prompt was sent to faster-whisper transcribe
        mock_model.transcribe.assert_called_once()
        call_kwargs = mock_model.transcribe.call_args.kwargs
        assert "initial_prompt" in call_kwargs
        assert "OmniTender" in call_kwargs["initial_prompt"]

        # Transcribe segments
        mock_model.transcribe.reset_mock()
        segments = service.transcribe_segments(fake_wav)
        assert len(segments) == 2
        assert segments[0].text == "Welcome to OmniTender"
        assert segments[1].text == "please run kubectl"

    @pytest.mark.asyncio
    async def test_local_service_transcribe_async(self, tmp_path: Path):
        fake_wav = tmp_path / "audio.wav"
        fake_wav.write_bytes(b"RIFF....WAVE")

        mgr = CustomVocabularyManager(
            replacements=[ReplacementRule("kube cuddle", "kubectl")],
            auto_load=False,
        )
        mock_segment = MagicMock()
        mock_segment.text = "run kube cuddle"
        mock_segment.start = 0.0
        mock_segment.end = 1.0

        service = LocalWhisperService(vocabulary_manager=mgr)
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([mock_segment], MagicMock())
        service._model = mock_model

        result = await service.transcribe_async(fake_wav)
        assert result == "run kubectl"


class TestTranscribeServiceIntegration:
    """Tests for TranscribeService integration with vocabulary biasing and replacements."""

    @pytest.mark.asyncio
    async def test_transcribe_service_online_prompt_and_replacements(
        self, tmp_path: Path
    ):
        fake_wav = tmp_path / "audio.wav"
        fake_wav.write_bytes(b"RIFF....WAVE")

        mgr = CustomVocabularyManager(
            words=["OmniTender", "kubectl"],
            replacements=[
                ReplacementRule("kube cuddle", "kubectl"),
                ReplacementRule("omni tender", "OmniTender"),
            ],
            auto_load=False,
        )

        mock_response = MagicMock()
        mock_response.text = "Connecting to omni tender using kube cuddle."

        service = TranscribeService(api_key="test-key", vocabulary_manager=mgr)
        service._client = AsyncMock()
        service._client.audio.transcriptions.create = AsyncMock(
            return_value=mock_response
        )

        result = await service.transcribe(str(fake_wav))
        assert result == "Connecting to OmniTender using kubectl."

        # Verify prompt passed to OpenAI API
        service._client.audio.transcriptions.create.assert_called_once()
        call_kwargs = service._client.audio.transcriptions.create.call_args.kwargs
        assert "prompt" in call_kwargs
        assert "Glossary: OmniTender, kubectl." in call_kwargs["prompt"]

    @pytest.mark.asyncio
    async def test_transcribe_service_local_mode_with_vocab(self, tmp_path: Path):
        fake_wav = tmp_path / "audio.wav"
        fake_wav.write_bytes(b"RIFF....WAVE")

        mgr = CustomVocabularyManager(
            replacements=[ReplacementRule("kube cuddle", "kubectl")],
            auto_load=False,
        )

        mock_segment = MagicMock()
        mock_segment.text = "execute kube cuddle"

        service = TranscribeService(use_local=True, vocabulary_manager=mgr)
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([mock_segment], MagicMock())
        service._local_service._model = mock_model

        result = await service.transcribe(str(fake_wav))
        assert result == "execute kubectl"


class TestDiffCorrections:
    """Tests for word-level diffing between original and edited text."""

    def test_single_substitution(self):
        pairs = diff_corrections("I use scrybe daily", "I use Scribe daily")
        assert pairs == [("scrybe", "Scribe")]

    def test_no_change_returns_empty(self):
        assert diff_corrections("hello world", "hello world") == []

    def test_large_rewrite_ignored(self):
        original = "the quick brown fox jumps over the lazy dog"
        edited = "a totally different sentence about something else entirely"
        assert diff_corrections(original, edited) == []

    def test_multiple_small_substitutions(self):
        pairs = diff_corrections(
            "meet kalindra at the offsite", "meet Kalindra at the off-site"
        )
        assert ("kalindra", "Kalindra") in pairs


class TestLearnedCorrections:
    """Tests for CustomVocabularyManager.record_correction promotion."""

    def test_promotes_after_threshold(self):
        mgr = CustomVocabularyManager(auto_load=False)
        assert mgr.record_correction("scrybe", "Scribe") is False
        assert mgr.record_correction("scrybe", "Scribe") is True

        rules = mgr.get_replacements()
        assert any(r.pattern == "scrybe" and r.replacement == "Scribe" for r in rules)

    def test_ignored_when_identical(self):
        mgr = CustomVocabularyManager(auto_load=False)
        assert mgr.record_correction("scribe", "scribe") is False

    def test_skips_if_rule_already_exists(self):
        mgr = CustomVocabularyManager(
            replacements=[ReplacementRule("scrybe", "Scribe")], auto_load=False
        )
        assert mgr.record_correction("scrybe", "Scribe") is False

    def test_roundtrip_persists_pending_counts(self, tmp_path: Path):
        config_path = tmp_path / "vocab.json"
        mgr = CustomVocabularyManager(config_path=config_path, auto_load=False)
        mgr.record_correction("scrybe", "Scribe")
        mgr.save()

        reloaded = CustomVocabularyManager(config_path=config_path, auto_load=True)
        assert reloaded.record_correction("scrybe", "Scribe") is True
