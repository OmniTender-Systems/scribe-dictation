"""Unit tests for sound bank synthesis, tiering, and audio playback cues."""

import wave
import io

from scribe_dictation.audio.sound_bank import (
    SOUND_THEMES,
    FREE_SOUND_THEMES,
    BASIC_SOUND_THEMES,
    PRO_SOUND_THEMES,
    DEFAULT_SOUND_THEME,
    get_sound_theme,
    get_sound_themes_for_tier,
    get_theme_wav_buffers,
    preview_sound,
)


def test_sound_themes_tier_counts():
    """Verify exact tier allocations."""
    # Free / Trial has 3 core themes
    assert len(FREE_SOUND_THEMES) == 3
    assert "classic_beep" in FREE_SOUND_THEMES
    assert "subtle_tick" in FREE_SOUND_THEMES
    assert "soft_chime" in FREE_SOUND_THEMES

    # Basic tier has 7 themes (3 free + 4 basic)
    assert len(BASIC_SOUND_THEMES) == 7
    for free_theme in FREE_SOUND_THEMES:
        assert free_theme in BASIC_SOUND_THEMES
    assert "gentle_bubble" in BASIC_SOUND_THEMES
    assert "digital_blip" in BASIC_SOUND_THEMES
    assert "wooden_tap" in BASIC_SOUND_THEMES
    assert "modern_pop" in BASIC_SOUND_THEMES

    # Pro tier has all themes (18 themes)
    assert len(PRO_SOUND_THEMES) >= 15
    for basic_theme in BASIC_SOUND_THEMES:
        assert basic_theme in PRO_SOUND_THEMES
    assert "tactile_thock" in PRO_SOUND_THEMES
    assert "tape_recorder" in PRO_SOUND_THEMES
    assert "fighter_hud" in PRO_SOUND_THEMES
    assert "cosmic_warp" in PRO_SOUND_THEMES
    assert "typewriter_bell" in PRO_SOUND_THEMES
    assert "marimba_chord" in PRO_SOUND_THEMES
    assert "zen_bowl" in PRO_SOUND_THEMES


def test_get_sound_themes_for_tier_filter():
    """Test get_sound_themes_for_tier helper."""
    free_themes = get_sound_themes_for_tier("free")
    assert len(free_themes) == 3
    assert all(t.tier == "free" for t in free_themes)

    basic_themes = get_sound_themes_for_tier("basic")
    assert len(basic_themes) == 7
    assert all(t.tier in ("free", "basic") for t in basic_themes)

    pro_themes = get_sound_themes_for_tier("pro")
    assert len(pro_themes) == len(SOUND_THEMES)


def test_all_synthesizers_generate_valid_wavs():
    """Verify that every registered sound theme synthesizes valid 16-bit 44.1kHz mono WAV buffers."""
    for theme_id in SOUND_THEMES.keys():
        start_wav, stop_wav = get_theme_wav_buffers(theme_id)
        assert len(start_wav) > 44, f"Start WAV for {theme_id} is too short"
        assert len(stop_wav) > 44, f"Stop WAV for {theme_id} is too short"

        # Verify start WAV header
        with wave.open(io.BytesIO(start_wav), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 44100
            assert wf.getnframes() > 0

        # Verify stop WAV header
        with wave.open(io.BytesIO(stop_wav), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 44100
            assert wf.getnframes() > 0


def test_get_sound_theme_lookup():
    """Test lookup by ID."""
    th = get_sound_theme("tactile_thock")
    assert th is not None
    assert th.id == "tactile_thock"
    assert th.tier == "pro"
    assert th.is_pro is True

    # Unknown ID returns None
    assert get_sound_theme("unknown_theme_123") is None


def test_fallback_on_unknown_theme():
    """Requesting an unknown theme defaults to classic_beep."""
    start_wav, stop_wav = get_theme_wav_buffers("non_existent_id")
    cb_start, cb_stop = get_theme_wav_buffers(DEFAULT_SOUND_THEME)
    assert start_wav == cb_start
    assert stop_wav == cb_stop


def test_preview_sound_does_not_crash():
    """preview_sound executes without throwing."""
    for theme_id in list(SOUND_THEMES.keys())[:3]:
        preview_sound(theme_id, start=True)
        preview_sound(theme_id, start=False)
