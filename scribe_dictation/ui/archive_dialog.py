"""Searchable History & Local Audio Archive Dialog for Privacy Scribe Pro."""

from __future__ import annotations

import os
import time
from typing import Any, Optional

from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from scribe_dictation.export import to_markdown, to_srt, to_txt
from scribe_dictation.history.archive import ArchiveEntry, TranscriptionArchive

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
except ImportError:
    QMediaPlayer = None  # type: ignore
    QAudioOutput = None  # type: ignore


class ArchiveDialog(QDialog):
    """Searchable transcription history with encrypted audio playback and batch export."""

    def __init__(
        self, archive: Optional[TranscriptionArchive] = None, parent=None
    ) -> None:
        super().__init__(parent)
        self.archive = archive or TranscriptionArchive()
        self.current_entries: list[ArchiveEntry] = []
        self.selected_entry: Optional[ArchiveEntry] = None

        # Media Player setup for audio playback
        self.player: Optional[Any] = None
        self.audio_output: Optional[Any] = None
        self._temp_playback_file: Optional[str] = None
        self._init_player()

        self.setWindowTitle(
            "Transcription History & Local Audio Archive — Privacy Scribe Pro"
        )
        self.setMinimumSize(850, 560)
        self.resize(920, 620)

        self._setup_ui()
        self._load_entries()

    def _init_player(self) -> None:
        if QMediaPlayer is not None and QAudioOutput is not None:
            try:
                self.player = QMediaPlayer(self)
                self.audio_output = QAudioOutput(self)
                self.player.setAudioOutput(self.audio_output)
            except Exception:
                self.player = None

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header
        header = QLabel(
            "<b>📜 Transcription History & Encrypted Audio Vault</b><br>"
            "<span style='color: #718096; font-size: 11px;'>"
            "Search past dictations, listen to recorded audio snippets, filter by mode or tag, and export records."
            "</span>"
        )
        layout.addWidget(header)

        # Search and Filter Toolbar
        filter_bar = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "🔍 Search transcription keywords or tags..."
        )
        self.search_input.textChanged.connect(self._on_search_changed)
        filter_bar.addWidget(self.search_input)

        self.mode_filter = QComboBox()
        self.mode_filter.addItem("All Modes", "")
        self.mode_filter.addItem("Raw Verbatim", "raw")
        self.mode_filter.addItem("Clean Speech", "clean")
        self.mode_filter.addItem("Bullet Points", "bullets")
        self.mode_filter.addItem("Meeting Notes", "meeting_notes")
        self.mode_filter.addItem("Email Draft", "email")
        self.mode_filter.addItem("Code Comments", "code_comment")
        self.mode_filter.currentIndexChanged.connect(self._on_search_changed)
        filter_bar.addWidget(self.mode_filter)

        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.clicked.connect(self._load_entries)
        filter_bar.addWidget(refresh_btn)

        layout.addLayout(filter_bar)

        # Splitter: Table on left, Details & Playback on right
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Table widget
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(
            ["Timestamp", "Mode", "Duration", "Transcription Preview"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        splitter.addWidget(self.table)

        # Right Panel: Inspector & Controls
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(10)

        # Full Text Box
        right_layout.addWidget(QLabel("<b>Full Transcription:</b>"))
        self.text_preview = QPlainTextEdit()
        self.text_preview.setReadOnly(True)
        self.text_preview.setStyleSheet(
            "font-size: 13px; line-height: 1.4; padding: 6px;"
        )
        right_layout.addWidget(self.text_preview)

        # Audio Playback Controls
        self.audio_box = QWidget()
        audio_layout = QHBoxLayout(self.audio_box)
        audio_layout.setContentsMargins(0, 0, 0, 0)

        self.play_btn = QPushButton("▶️ Play Audio")
        self.play_btn.setEnabled(False)
        self.play_btn.clicked.connect(self._toggle_audio_play)
        audio_layout.addWidget(self.play_btn)

        self.export_audio_btn = QPushButton("💾 Export Audio")
        self.export_audio_btn.setEnabled(False)
        self.export_audio_btn.clicked.connect(self._export_audio)
        audio_layout.addWidget(self.export_audio_btn)

        right_layout.addWidget(self.audio_box)

        # Export & Manage Row
        actions_box = QHBoxLayout()
        self.export_txt_btn = QPushButton("Export Text (.txt / .md)")
        self.export_txt_btn.setEnabled(False)
        self.export_txt_btn.clicked.connect(self._export_text)
        actions_box.addWidget(self.export_txt_btn)

        self.delete_btn = QPushButton("🗑️ Delete")
        self.delete_btn.setEnabled(False)
        self.delete_btn.setStyleSheet("color: #e53e3e;")
        self.delete_btn.clicked.connect(self._delete_entry)
        actions_box.addWidget(self.delete_btn)

        right_layout.addLayout(actions_box)
        splitter.addWidget(right_panel)

        splitter.setSizes([520, 380])
        layout.addWidget(splitter)

        # Bottom Bar: Stats & Close
        bottom_bar = QHBoxLayout()
        self.count_label = QLabel("0 entries found")
        self.count_label.setStyleSheet("color: #718096; font-size: 11px;")
        bottom_bar.addWidget(self.count_label)

        bottom_bar.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        bottom_bar.addWidget(close_btn)
        layout.addLayout(bottom_bar)

    def _load_entries(self) -> None:
        query = self.search_input.text().strip()
        mode = self.mode_filter.currentData()

        self.current_entries = self.archive.search(
            query=query, mode=mode if mode else None
        )
        self.table.setRowCount(len(self.current_entries))

        for row, entry in enumerate(self.current_entries):
            # Formatted time
            dt_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(entry.timestamp))
            item_time = QTableWidgetItem(dt_str)
            item_time.setFlags(item_time.flags() & ~Qt.ItemFlag.ItemIsEditable)

            item_mode = QTableWidgetItem(entry.mode)
            item_mode.setFlags(item_mode.flags() & ~Qt.ItemFlag.ItemIsEditable)

            dur_str = f"{entry.duration:.1f}s" if entry.duration > 0 else "—"
            item_dur = QTableWidgetItem(dur_str)
            item_dur.setFlags(item_dur.flags() & ~Qt.ItemFlag.ItemIsEditable)

            preview = entry.text.replace("\n", " ")[:120]
            item_text = QTableWidgetItem(preview)
            item_text.setFlags(item_text.flags() & ~Qt.ItemFlag.ItemIsEditable)

            self.table.setItem(row, 0, item_time)
            self.table.setItem(row, 1, item_mode)
            self.table.setItem(row, 2, item_dur)
            self.table.setItem(row, 3, item_text)

        self.count_label.setText(
            f"{len(self.current_entries)} dictation entries in archive"
        )
        self._update_inspector(None)

    def _on_search_changed(self) -> None:
        self._load_entries()

    def _on_selection_changed(self) -> None:
        selected_rows = self.table.selectedIndexes()
        if not selected_rows:
            self._update_inspector(None)
            return

        row = selected_rows[0].row()
        if 0 <= row < len(self.current_entries):
            entry = self.current_entries[row]
            self._update_inspector(entry)

    def _update_inspector(self, entry: Optional[ArchiveEntry]) -> None:
        self.selected_entry = entry
        if not entry:
            self.text_preview.setPlainText("")
            self.play_btn.setEnabled(False)
            self.export_audio_btn.setEnabled(False)
            self.export_txt_btn.setEnabled(False)
            self.delete_btn.setEnabled(False)
            return

        self.text_preview.setPlainText(entry.text)
        has_audio = bool(entry.audio_path and os.path.exists(entry.audio_path))
        self.play_btn.setEnabled(has_audio)
        self.export_audio_btn.setEnabled(has_audio)
        self.export_txt_btn.setEnabled(True)
        self.delete_btn.setEnabled(True)

    def _toggle_audio_play(self) -> None:
        if not self.selected_entry or not self.selected_entry.audio_path:
            return

        if not self.player:
            QMessageBox.information(
                self,
                "Audio Playback",
                "Qt Multimedia playback is not available in this environment.",
            )
            return

        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.stop()
            self.play_btn.setText("▶️ Play Audio")
            return

        # Prepare audio file (decrypt temporary copy if encrypted)
        try:
            temp_path = self.selected_entry.audio_path
            # Check if vault encrypted
            with open(temp_path, "rb") as f:
                header = f.read(10)
            if header.startswith(b"VAULT_ENC:"):
                import tempfile

                fd, tmp = tempfile.mkstemp(suffix=".wav")
                os.close(fd)
                self.archive.export_audio(self.selected_entry.id, tmp)
                self._temp_playback_file = tmp
                playback_target = tmp
            else:
                playback_target = temp_path

            self.player.setSource(QUrl.fromLocalFile(playback_target))
            self.player.play()
            self.play_btn.setText("⏹️ Stop Audio")
        except Exception as e:
            QMessageBox.critical(self, "Playback Error", f"Failed to play audio: {e}")

    def _export_audio(self) -> None:
        if not self.selected_entry or not self.selected_entry.audio_path:
            return

        default_name = f"scribe_{self.selected_entry.id[:8]}.wav"
        dest_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Audio Recording",
            default_name,
            "WAV Audio (*.wav);;All Files (*)",
        )
        if dest_path:
            try:
                self.archive.export_audio(self.selected_entry.id, dest_path)
                QMessageBox.information(
                    self,
                    "Export Complete",
                    f"Audio exported successfully to:\n{dest_path}",
                )
            except Exception as e:
                QMessageBox.critical(
                    self, "Export Failed", f"Could not export audio: {e}"
                )

    def _export_text(self) -> None:
        if not self.selected_entry:
            return

        default_name = f"dictation_{self.selected_entry.id[:8]}.md"
        dest_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Transcription Text",
            default_name,
            "Markdown (*.md);;Plain Text (*.txt);;SRT Subtitles (*.srt)",
        )
        if dest_path:
            try:
                text = self.selected_entry.text
                if dest_path.endswith(".srt") or "SRT" in selected_filter:
                    formatted = to_srt(
                        [
                            {
                                "text": text,
                                "start": 0.0,
                                "end": self.selected_entry.duration or 3.0,
                            }
                        ]
                    )
                elif dest_path.endswith(".md") or "Markdown" in selected_filter:
                    formatted = to_markdown(
                        text, title=f"Dictation {self.selected_entry.id[:8]}"
                    )
                else:
                    formatted = to_txt(text)

                with open(dest_path, "w", encoding="utf-8") as f:
                    f.write(formatted)

                QMessageBox.information(
                    self, "Export Complete", f"Transcription exported to:\n{dest_path}"
                )
            except Exception as e:
                QMessageBox.critical(
                    self, "Export Failed", f"Could not export text: {e}"
                )

    def _delete_entry(self) -> None:
        if not self.selected_entry:
            return

        reply = QMessageBox.question(
            self,
            "Delete Transcription",
            "Are you sure you want to permanently delete this dictation and its stored audio recording?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.archive.delete_entry(self.selected_entry.id, delete_audio_file=True)
            self._load_entries()

    def closeEvent(self, event) -> None:
        if self.player:
            self.player.stop()
        if self._temp_playback_file and os.path.exists(self._temp_playback_file):
            try:
                os.remove(self._temp_playback_file)
            except Exception:
                pass
        super().closeEvent(event)
