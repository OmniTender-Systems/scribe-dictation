"""UI module for scribe-dictation."""

from scribe_dictation.ui.profiles_dialog import ProfilesDialog
from scribe_dictation.ui.snippets_dialog import SnippetsDialog
from scribe_dictation.ui.transform_palette import (
    TransformPalette,
    grab_selected_text,
    _simulate_copy,
    _simulate_paste,
)

__all__ = [
    "ProfilesDialog",
    "SnippetsDialog",
    "TransformPalette",
    "grab_selected_text",
    "_simulate_copy",
    "_simulate_paste",
]
