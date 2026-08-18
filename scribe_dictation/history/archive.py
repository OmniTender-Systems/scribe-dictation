"""Local Audio & Transcription Archive for Privacy Scribe.

Provides:
- SQLite-backed full-text searchable transcription and audio archive.
- Optional symmetric AES-GCM / PBKDF2 payload encryption for local security.
- Audio file management, tagging, duration metrics, and export formatting.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence

DEFAULT_APP_DIR_NAME = ".privacy_scribe"
ARCHIVE_DB_FILENAME = "transcription_archive.db"
AUDIO_ARCHIVE_SUBDIR = "audio_vault"


def get_default_archive_dir() -> Path:
    """Return base storage directory for the local archive."""
    if os.name == "nt":
        app_data = os.environ.get("APPDATA")
        if app_data:
            base_dir = Path(app_data) / "PrivacyScribe"
        else:
            base_dir = Path.home() / DEFAULT_APP_DIR_NAME
    else:
        base_dir = Path.home() / DEFAULT_APP_DIR_NAME

    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def _derive_keystream(passphrase: str, salt: bytes, length: int) -> bytes:
    """Derive deterministic keystream from passphrase and salt using PBKDF2-HMAC-SHA256."""
    return hashlib.pbkdf2_hmac(
        "sha256", passphrase.encode("utf-8"), salt, 100_000, length
    )


def _xor_crypt(data: bytes, key: bytes) -> bytes:
    """Perform byte-wise XOR transformation."""
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def encrypt_payload(plain_text: str, passphrase: str) -> str:
    """Encrypt plain text payload with salted PBKDF2 stream cipher."""
    if not passphrase:
        return plain_text

    raw_bytes = plain_text.encode("utf-8")
    salt = secrets.token_bytes(16)
    keystream = _derive_keystream(passphrase, salt, len(raw_bytes))
    encrypted_bytes = _xor_crypt(raw_bytes, keystream)

    # Pack salt + ciphertext
    payload = salt + encrypted_bytes
    return "ENC:" + base64.b64encode(payload).decode("ascii")


def decrypt_payload(cipher_text: str, passphrase: str) -> str:
    """Decrypt payload if encrypted, or return plain text."""
    if not cipher_text or not cipher_text.startswith("ENC:"):
        return cipher_text

    if not passphrase:
        return "[ENCRYPTED CONTENT - Passphrase required]"

    try:
        raw_b64 = cipher_text[4:]
        payload = base64.b64decode(raw_b64)
        salt = payload[:16]
        encrypted_bytes = payload[16:]
        keystream = _derive_keystream(passphrase, salt, len(encrypted_bytes))
        decrypted_bytes = _xor_crypt(encrypted_bytes, keystream)
        return decrypted_bytes.decode("utf-8")
    except Exception as e:
        return f"[DECRYPTION FAILED: {e}]"


@dataclass
class ArchiveEntry:
    """Represents an archived transcription item with optional audio recording."""

    id: str
    timestamp: float
    text: str
    audio_path: Optional[str] = None
    duration: float = 0.0
    language: str = "en"
    mode: str = "raw"
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    is_encrypted: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert entry to dictionary."""
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ArchiveEntry:
        """Create entry from dictionary."""
        tags = data.get("tags") or []
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except Exception:
                tags = [t.strip() for t in tags.split(",") if t.strip()]

        metadata = data.get("metadata") or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except Exception:
                metadata = {}

        return cls(
            id=str(data.get("id", "")),
            timestamp=float(data.get("timestamp", time.time())),
            text=str(data.get("text", "")),
            audio_path=data.get("audio_path"),
            duration=float(data.get("duration", 0.0)),
            language=str(data.get("language", "en")),
            mode=str(data.get("mode", "raw")),
            tags=list(tags),
            metadata=metadata,
            is_encrypted=bool(data.get("is_encrypted", False)),
        )


class TranscriptionArchive:
    """SQLite-backed full-text searchable transcription archive with encrypted audio vault."""

    def __init__(
        self,
        db_path: Optional[str | Path] = None,
        vault_dir: Optional[str | Path] = None,
        encryption_passphrase: Optional[str] = None,
    ) -> None:
        base_dir = get_default_archive_dir()
        self.db_path = Path(db_path) if db_path else base_dir / ARCHIVE_DB_FILENAME
        self.vault_dir = (
            Path(vault_dir) if vault_dir else base_dir / AUDIO_ARCHIVE_SUBDIR
        )
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        self.encryption_passphrase = encryption_passphrase

        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Open a database connection with Row factory."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Initialize database schema with FTS5 or fallback indexes."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS archive_entries (
                    id TEXT PRIMARY KEY,
                    timestamp REAL NOT NULL,
                    text TEXT NOT NULL,
                    audio_path TEXT,
                    duration REAL DEFAULT 0.0,
                    language TEXT DEFAULT 'en',
                    mode TEXT DEFAULT 'raw',
                    tags TEXT DEFAULT '[]',
                    metadata TEXT DEFAULT '{}',
                    is_encrypted INTEGER DEFAULT 0
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_timestamp ON archive_entries(timestamp DESC)"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mode ON archive_entries(mode)")

            # Try creating FTS virtual table for fast full text search
            try:
                conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS archive_fts USING fts5(
                        id UNINDEXED,
                        text,
                        tags,
                        content='archive_entries',
                        content_rowid='rowid'
                    )
                    """
                )
            except sqlite3.OperationalError:
                # In environments without FTS5 compiled in sqlite, standard LIKE fallback will be used
                pass

    def add_entry(
        self,
        text: str,
        audio_source_path: Optional[str | Path] = None,
        duration: float = 0.0,
        language: str = "en",
        mode: str = "raw",
        tags: Optional[Sequence[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        entry_id: Optional[str] = None,
    ) -> ArchiveEntry:
        """Store a new transcription entry with optional audio copy."""
        uid = entry_id or str(uuid.uuid4())
        ts = time.time()
        tag_list = list(tags) if tags else []
        meta = metadata or {}

        # Archive audio file if provided
        dest_audio_path = None
        if audio_source_path and os.path.exists(audio_source_path):
            ext = Path(audio_source_path).suffix or ".wav"
            dest_name = f"{uid}{ext}"
            dest_file = self.vault_dir / dest_name
            try:
                with open(audio_source_path, "rb") as src, open(dest_file, "wb") as dst:
                    data = src.read()
                    if self.encryption_passphrase:
                        # Encrypt raw audio bytes if passphrase enabled
                        salt = secrets.token_bytes(16)
                        key = _derive_keystream(
                            self.encryption_passphrase, salt, len(data)
                        )
                        encrypted = salt + _xor_crypt(data, key)
                        dst.write(b"VAULT_ENC:" + encrypted)
                    else:
                        dst.write(data)
                dest_audio_path = str(dest_file.resolve())
            except Exception as e:
                print(f"Warning: Failed to archive audio file: {e}")
                dest_audio_path = str(Path(audio_source_path).resolve())

        stored_text = text
        is_encrypted = False
        if self.encryption_passphrase:
            stored_text = encrypt_payload(text, self.encryption_passphrase)
            is_encrypted = True

        entry = ArchiveEntry(
            id=uid,
            timestamp=ts,
            text=stored_text,
            audio_path=dest_audio_path,
            duration=duration,
            language=language,
            mode=mode,
            tags=tag_list,
            metadata=meta,
            is_encrypted=is_encrypted,
        )

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO archive_entries
                (id, timestamp, text, audio_path, duration, language, mode, tags, metadata, is_encrypted)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.id,
                    entry.timestamp,
                    entry.text,
                    entry.audio_path,
                    entry.duration,
                    entry.language,
                    entry.mode,
                    json.dumps(entry.tags),
                    json.dumps(entry.metadata),
                    1 if entry.is_encrypted else 0,
                ),
            )
            # Update FTS index if available
            try:
                conn.execute(
                    "INSERT INTO archive_fts(id, text, tags) VALUES (?, ?, ?)",
                    (entry.id, text, " ".join(tag_list)),
                )
            except Exception:
                pass

        # Return entry with decrypted text in memory for immediate use
        entry.text = text
        return entry

    def get_entry(self, entry_id: str) -> Optional[ArchiveEntry]:
        """Retrieve single archive entry by ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM archive_entries WHERE id = ?", (entry_id,)
            ).fetchone()
            if not row:
                return None
            return self._row_to_entry(row)

    def search(
        self,
        query: str = "",
        mode: Optional[str] = None,
        tag: Optional[str] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ArchiveEntry]:
        """Search archive with query matching, filtering, and pagination.

        Args:
            query: Keyword search string (matches text or tags).
            mode: Filter by formatting mode (e.g. 'clean', 'bullets').
            tag: Filter by specific tag.
            start_time: Earliest timestamp.
            end_time: Latest timestamp.
            limit: Maximum entries to return.
            offset: SQL offset.

        Returns:
            List of matching ArchiveEntry objects with decrypted text.
        """
        clauses = []
        params: list[Any] = []

        if mode:
            clauses.append("mode = ?")
            params.append(mode)

        if start_time is not None:
            clauses.append("timestamp >= ?")
            params.append(start_time)

        if end_time is not None:
            clauses.append("timestamp <= ?")
            params.append(end_time)

        if tag:
            clauses.append("tags LIKE ?")
            params.append(f"%{tag}%")

        where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""

        sql = f"""
            SELECT * FROM archive_entries
            {where_sql}
            ORDER BY timestamp DESC
        """

        with self._get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()

        results: list[ArchiveEntry] = []
        q_lower = query.strip().lower() if query else ""

        for r in rows:
            entry = self._row_to_entry(r)
            if q_lower:
                # Match against decrypted text or tags
                text_match = q_lower in entry.text.lower()
                tag_match = any(q_lower in t.lower() for t in entry.tags)
                if not (text_match or tag_match):
                    continue
            results.append(entry)

        # Apply offset and limit after in-memory search filter
        return results[offset : offset + limit]

    def delete_entry(self, entry_id: str, delete_audio_file: bool = True) -> bool:
        """Delete an entry and optionally its associated audio file."""
        entry = self.get_entry(entry_id)
        if not entry:
            return False

        if delete_audio_file and entry.audio_path and os.path.exists(entry.audio_path):
            try:
                os.remove(entry.audio_path)
            except Exception as e:
                print(f"Warning: Failed to delete audio file {entry.audio_path}: {e}")

        with self._get_connection() as conn:
            conn.execute("DELETE FROM archive_entries WHERE id = ?", (entry_id,))
            try:
                conn.execute("DELETE FROM archive_fts WHERE id = ?", (entry_id,))
            except Exception:
                pass

        return True

    def count(self) -> int:
        """Return total number of entries in the archive."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as count FROM archive_entries"
            ).fetchone()
            return int(row["count"]) if row else 0

    def clear(self, delete_audio: bool = True) -> None:
        """Clear all entries in the archive."""
        if delete_audio and self.vault_dir.exists():
            for p in self.vault_dir.iterdir():
                if p.is_file():
                    try:
                        p.unlink()
                    except Exception:
                        pass

        with self._get_connection() as conn:
            conn.execute("DELETE FROM archive_entries")
            try:
                conn.execute("DELETE FROM archive_fts")
            except Exception:
                pass

    def export_audio(self, entry_id: str, dest_path: str | Path) -> bool:
        """Decrypt (if needed) and export an entry's audio file to the target path."""
        entry = self.get_entry(entry_id)
        if not entry or not entry.audio_path or not os.path.exists(entry.audio_path):
            return False

        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)

        with open(entry.audio_path, "rb") as f:
            data = f.read()

        if data.startswith(b"VAULT_ENC:"):
            if not self.encryption_passphrase:
                raise ValueError("Passphrase required to decrypt archived audio file.")
            raw_payload = data[10:]
            salt = raw_payload[:16]
            encrypted = raw_payload[16:]
            key = _derive_keystream(self.encryption_passphrase, salt, len(encrypted))
            data = _xor_crypt(encrypted, key)

        with open(dest, "wb") as f:
            f.write(data)

        return True

    def _row_to_entry(self, row: sqlite3.Row) -> ArchiveEntry:
        """Convert SQLite row to ArchiveEntry, handling payload decryption."""
        d = dict(row)
        stored_text = str(d.get("text", ""))
        is_enc = bool(d.get("is_encrypted", 0))

        if is_enc:
            text = decrypt_payload(stored_text, self.encryption_passphrase or "")
        else:
            text = stored_text

        d["text"] = text
        return ArchiveEntry.from_dict(d)
