"""History and Archive Module for Privacy Scribe."""

from scribe_dictation.history.archive import (
    ArchiveEntry,
    TranscriptionArchive,
    decrypt_payload,
    encrypt_payload,
    get_default_archive_dir,
)

__all__ = [
    "ArchiveEntry",
    "TranscriptionArchive",
    "encrypt_payload",
    "decrypt_payload",
    "get_default_archive_dir",
]
