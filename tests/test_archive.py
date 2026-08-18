"""Tests for Local Encrypted Audio & Transcription Archive."""

import os
import pytest

from scribe_dictation.history.archive import (
    TranscriptionArchive,
    decrypt_payload,
    encrypt_payload,
)


@pytest.fixture
def temp_archive(tmp_path):
    db_file = tmp_path / "test_archive.db"
    vault_dir = tmp_path / "test_vault"
    return TranscriptionArchive(db_path=db_file, vault_dir=vault_dir)


@pytest.fixture
def encrypted_archive(tmp_path):
    db_file = tmp_path / "enc_archive.db"
    vault_dir = tmp_path / "enc_vault"
    return TranscriptionArchive(
        db_path=db_file,
        vault_dir=vault_dir,
        encryption_passphrase="SecretPassword123!",
    )


class TestTranscriptionArchive:
    """Test suite verifying local SQLite database, search, and encrypted audio vault."""

    def test_add_and_get_entry(self, temp_archive):
        entry = temp_archive.add_entry(
            text="Testing local transcription archive storage.",
            duration=4.2,
            language="en",
            mode="clean",
            tags=["work", "notes"],
        )

        assert entry.id
        assert entry.text == "Testing local transcription archive storage."
        assert entry.duration == 4.2
        assert entry.mode == "clean"
        assert "work" in entry.tags

        fetched = temp_archive.get_entry(entry.id)
        assert fetched is not None
        assert fetched.id == entry.id
        assert fetched.text == entry.text
        assert fetched.duration == 4.2

    def test_search_by_query_and_mode(self, temp_archive):
        temp_archive.add_entry(
            text="Discussing Kubernetes microservices architecture", mode="bullets"
        )
        temp_archive.add_entry(
            text="Drafting email to marketing department", mode="email"
        )
        temp_archive.add_entry(
            text="Meeting with client about pricing models", mode="meeting_notes"
        )

        # Search by query
        results = temp_archive.search(query="Kubernetes")
        assert len(results) == 1
        assert "Kubernetes" in results[0].text

        # Search by mode
        results = temp_archive.search(mode="email")
        assert len(results) == 1
        assert "marketing" in results[0].text

        # Search total
        all_entries = temp_archive.search()
        assert len(all_entries) == 3

    def test_audio_vault_storage_and_export(self, temp_archive, tmp_path):
        # Create dummy WAV file
        dummy_wav = tmp_path / "sample.wav"
        dummy_wav.write_bytes(b"RIFFdummywavdata1234567890")

        entry = temp_archive.add_entry(
            text="Audio test dictation",
            audio_source_path=str(dummy_wav),
            duration=1.5,
        )

        assert entry.audio_path is not None
        assert os.path.exists(entry.audio_path)

        # Export audio
        export_target = tmp_path / "exported.wav"
        success = temp_archive.export_audio(entry.id, export_target)
        assert success is True
        assert export_target.exists()
        assert export_target.read_bytes() == b"RIFFdummywavdata1234567890"

    def test_encrypted_archive_payload_and_audio(self, encrypted_archive, tmp_path):
        dummy_wav = tmp_path / "secret.wav"
        dummy_wav.write_bytes(b"SECRET_VOICE_AUDIO_DATA_BYTES")

        entry = encrypted_archive.add_entry(
            text="Top secret internal roadmap discussion.",
            audio_source_path=str(dummy_wav),
            duration=2.0,
        )

        # In-memory text returned is decrypted
        assert entry.text == "Top secret internal roadmap discussion."
        assert entry.is_encrypted is True

        # Directly inspect database to verify encryption at rest
        with encrypted_archive._get_connection() as conn:
            row = conn.execute(
                "SELECT text FROM archive_entries WHERE id = ?", (entry.id,)
            ).fetchone()
            db_stored_text = row["text"]
            assert db_stored_text.startswith("ENC:")
            assert "Top secret" not in db_stored_text

        # Retrieve via get_entry (should automatically decrypt with passphrase)
        retrieved = encrypted_archive.get_entry(entry.id)
        assert retrieved.text == "Top secret internal roadmap discussion."

        # Export encrypted audio
        exported_audio = tmp_path / "decrypted_voice.wav"
        ok = encrypted_archive.export_audio(entry.id, exported_audio)
        assert ok is True
        assert exported_audio.read_bytes() == b"SECRET_VOICE_AUDIO_DATA_BYTES"

    def test_delete_entry(self, temp_archive, tmp_path):
        dummy_wav = tmp_path / "to_delete.wav"
        dummy_wav.write_bytes(b"delete_me")

        entry = temp_archive.add_entry(
            text="Temporary transcription", audio_source_path=str(dummy_wav)
        )
        audio_file = entry.audio_path

        assert temp_archive.count() == 1
        assert os.path.exists(audio_file)

        deleted = temp_archive.delete_entry(entry.id, delete_audio_file=True)
        assert deleted is True
        assert temp_archive.count() == 0
        assert not os.path.exists(audio_file)

    def test_encryption_functions_direct(self):
        secret_text = "Highly confidential data string."
        password = "MasterPassword"
        encrypted = encrypt_payload(secret_text, password)
        assert encrypted.startswith("ENC:")
        assert secret_text not in encrypted

        decrypted = decrypt_payload(encrypted, password)
        assert decrypted == secret_text
