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

from scribe_dictation.export import (
    to_markdown,
    to_srt,
    to_txt,
    to_json,
    to_html,
    TranscriptionResult,
    Segment,
)
from scribe_dictation.export.formats import _format_clock
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
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
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

        self.cut_snippet_btn = QPushButton("✂️ Cut Snippet")
        self.cut_snippet_btn.setEnabled(False)
        self.cut_snippet_btn.clicked.connect(self._cut_audio_snippet)
        audio_layout.addWidget(self.cut_snippet_btn)

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
        selected_ranges = self.table.selectedRanges()
        if not selected_ranges:
            self._update_inspector(None)
            self.export_txt_btn.setText("Export Text (.txt / .md)")
            return

        selected_rows = []
        for r in selected_ranges:
            for row in range(r.topRow(), r.bottomRow() + 1):
                if row not in selected_rows:
                    selected_rows.append(row)
        selected_rows.sort()

        if not selected_rows:
            self._update_inspector(None)
            self.export_txt_btn.setText("Export Text (.txt / .md)")
            return

        row = selected_rows[0]
        if 0 <= row < len(self.current_entries):
            entry = self.current_entries[row]
            self._update_inspector(entry)

        if len(selected_rows) > 1:
            self.export_txt_btn.setText(f"Export Selected ({len(selected_rows)} items)")
        else:
            self.export_txt_btn.setText("Export Text (.txt / .md)")

    def _update_inspector(self, entry: Optional[ArchiveEntry]) -> None:
        self.selected_entry = entry
        if not entry:
            self.text_preview.setPlainText("")
            self.play_btn.setEnabled(False)
            self.export_audio_btn.setEnabled(False)
            self.cut_snippet_btn.setEnabled(False)
            self.export_txt_btn.setEnabled(False)
            self.delete_btn.setEnabled(False)
            return

        self.text_preview.setPlainText(entry.text)
        has_audio = bool(entry.audio_path and os.path.exists(entry.audio_path))
        self.play_btn.setEnabled(has_audio)
        self.export_audio_btn.setEnabled(has_audio)
        self.cut_snippet_btn.setEnabled(has_audio)
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
        selected_ranges = self.table.selectedRanges()
        selected_rows = []
        for r in selected_ranges:
            for row in range(r.topRow(), r.bottomRow() + 1):
                if row not in selected_rows:
                    selected_rows.append(row)
        selected_rows.sort()

        if not selected_rows:
            return

        entries = [
            self.current_entries[r]
            for r in selected_rows
            if 0 <= r < len(self.current_entries)
        ]
        if not entries:
            return

        if len(entries) > 1:
            self._export_batch(entries)
            return

        # Single entry export
        entry = entries[0]
        default_name = f"dictation_{entry.id[:8]}.md"
        dest_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Transcription Text",
            default_name,
            "Markdown (*.md);;Plain Text (*.txt);;SRT Subtitles (*.srt);;JSON (*.json);;HTML (*.html)",
        )
        if dest_path:
            try:
                result = self._result_from_entry(entry)

                if dest_path.endswith(".srt") or "SRT" in selected_filter:
                    formatted = to_srt(result)
                elif dest_path.endswith(".json") or "JSON" in selected_filter:
                    formatted = to_json(result)
                elif dest_path.endswith(".html") or "HTML" in selected_filter:
                    formatted = to_html(result)
                elif dest_path.endswith(".md") or "Markdown" in selected_filter:
                    formatted = to_markdown(result)
                else:
                    formatted = to_txt(result)

                with open(dest_path, "w", encoding="utf-8") as f:
                    f.write(formatted)

                QMessageBox.information(
                    self, "Export Complete", f"Transcription exported to:\n{dest_path}"
                )
            except Exception as e:
                QMessageBox.critical(
                    self, "Export Failed", f"Could not export text: {e}"
                )

    def _export_batch(self, entries: list[ArchiveEntry]) -> None:
        from PySide6.QtWidgets import QInputDialog

        formats_list = [
            "Markdown (.md)",
            "Plain Text (.txt)",
            "SRT Subtitles (.srt)",
            "JSON (.json)",
            "HTML (.html)",
        ]
        selected_format_str, ok1 = QInputDialog.getItem(
            self,
            "Batch Export Format",
            f"Select format for {len(entries)} items:",
            formats_list,
            0,
            False,
        )
        if not ok1 or not selected_format_str:
            return

        ext = {
            "Markdown (.md)": "md",
            "Plain Text (.txt)": "txt",
            "SRT Subtitles (.srt)": "srt",
            "JSON (.json)": "json",
            "HTML (.html)": "html",
        }[selected_format_str]

        types_list = [
            "Separate Files in Folder",
            "Single Combined Document",
            "ZIP Archive (with Audio)",
        ]
        selected_type, ok2 = QInputDialog.getItem(
            self,
            "Batch Export Option",
            "Choose export destination type:",
            types_list,
            0,
            False,
        )
        if not ok2 or not selected_type:
            return

        if selected_type == "Separate Files in Folder":
            dest_dir = QFileDialog.getExistingDirectory(self, "Select Export Directory")
            if not dest_dir:
                return
            count = 0
            for entry in entries:
                try:
                    result = self._result_from_entry(entry)
                    formatted = self._format_result(result, ext)
                    filename = f"dictation_{entry.id[:8]}.{ext}"
                    with open(
                        os.path.join(dest_dir, filename), "w", encoding="utf-8"
                    ) as f:
                        f.write(formatted)
                    count += 1
                except Exception as e:
                    print(f"Failed to export {entry.id}: {e}")
            QMessageBox.information(
                self,
                "Export Complete",
                f"Successfully exported {count} files to:\n{dest_dir}",
            )

        elif selected_type == "Single Combined Document":
            default_name = f"combined_export.{ext}"
            dest_path, _ = QFileDialog.getSaveFileName(
                self, "Save Combined Document", default_name, f"Files (*.{ext})"
            )
            if not dest_path:
                return
            try:
                combined_content = []
                for entry in entries:
                    result = self._result_from_entry(entry)
                    combined_content.append(self._format_result(result, ext))

                if ext == "md":
                    separator = "\n\n---\n\n"
                elif ext == "json":
                    import json

                    results_list = []
                    for entry in entries:
                        res = self._result_from_entry(entry)
                        segments_list = [
                            {"start": s.start, "end": s.end, "text": s.text}
                            for s in res.segments
                        ]
                        results_list.append(
                            {
                                "title": res.title,
                                "created_at": res.created_at.isoformat(),
                                "text": res.text,
                                "segments": segments_list,
                            }
                        )
                    combined_text = json.dumps(
                        results_list, indent=2, ensure_ascii=False
                    )
                elif ext == "html":
                    bodies = []
                    for entry in entries:
                        res = self._result_from_entry(entry)
                        inner_body = ""
                        for segment in res.segments:
                            start_str = _format_clock(segment.start)
                            inner_body += (
                                f'<div class="segment" style="margin-bottom: 12px; padding: 6px; border-left: 3px solid #3182ce; padding-left: 10px;">'
                                f'<span class="time" style="color: #718096; font-family: monospace; font-size: 12px; margin-right: 10px;">[{start_str}]</span>'
                                f'<span class="text" style="color: #2d3748; font-size: 14px;">{segment.text}</span>'
                                f"</div>"
                            )
                        bodies.append(
                            f'<div class="entry" style="margin-bottom: 40px;">'
                            f"<h2>{res.title}</h2>"
                            f'<div class="meta" style="font-size: 12px; color: #a0aec0; margin-bottom: 20px;">{res.created_at.strftime("%Y-%m-%d %H:%M:%S")}</div>'
                            f'<div class="transcript">{inner_body}</div>'
                            f"</div>"
                        )
                    combined_text = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Combined Export</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            line-height: 1.6;
            max-width: 800px;
            margin: 40px auto;
            padding: 0 20px;
            background-color: #f7fafc;
            color: #2d3748;
        }}
        .container {{
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
        }}
        h1 {{
            color: #1a202c;
            margin-top: 0;
            border-bottom: 2px solid #e2e8f0;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #2d3748;
            border-bottom: 1px solid #e2e8f0;
            padding-bottom: 5px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Combined Transcription Export</h1>
        {"<hr style='margin: 40px 0; border: 0; border-top: 1px solid #e2e8f0;'>".join(bodies)}
    </div>
</body>
</html>
"""
                else:
                    separator = "\n\n========================================\n\n"

                if ext not in ("json", "html"):
                    combined_text = separator.join(combined_content)

                with open(dest_path, "w", encoding="utf-8") as f:
                    f.write(combined_text)
                QMessageBox.information(
                    self, "Export Complete", f"Combined document saved to:\n{dest_path}"
                )
            except Exception as e:
                QMessageBox.critical(
                    self, "Export Failed", f"Could not create combined document: {e}"
                )

        elif selected_type == "ZIP Archive (with Audio)":
            dest_path, _ = QFileDialog.getSaveFileName(
                self, "Save ZIP Archive", "batch_export.zip", "ZIP Archive (*.zip)"
            )
            if not dest_path:
                return
            import zipfile
            import tempfile

            try:
                with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
                    for entry in entries:
                        result = self._result_from_entry(entry)
                        formatted = self._format_result(result, ext)

                        txt_filename = f"dictation_{entry.id[:8]}.{ext}"
                        zip_file.writestr(txt_filename, formatted)

                        if entry.audio_path and os.path.exists(entry.audio_path):
                            audio_filename = f"audio_{entry.id[:8]}.wav"
                            with open(entry.audio_path, "rb") as f:
                                header = f.read(10)
                            if header.startswith(b"VAULT_ENC:"):
                                fd, tmp = tempfile.mkstemp(suffix=".wav")
                                os.close(fd)
                                try:
                                    self.archive.export_audio(entry.id, tmp)
                                    zip_file.write(tmp, audio_filename)
                                finally:
                                    try:
                                        os.remove(tmp)
                                    except Exception:
                                        pass
                            else:
                                zip_file.write(entry.audio_path, audio_filename)
                QMessageBox.information(
                    self, "Export Complete", f"ZIP archive saved to:\n{dest_path}"
                )
            except Exception as e:
                QMessageBox.critical(
                    self, "Export Failed", f"Could not create ZIP archive: {e}"
                )

    def _result_from_entry(self, entry: ArchiveEntry) -> TranscriptionResult:
        from datetime import datetime

        title = f"Dictation {entry.id[:8]}"
        created = datetime.fromtimestamp(entry.timestamp)
        segments = []
        if entry.metadata and "segments" in entry.metadata:
            for s in entry.metadata["segments"]:
                segments.append(
                    Segment(
                        start=float(s.get("start", 0.0)),
                        end=float(s.get("end", 0.0)),
                        text=s.get("text", ""),
                    )
                )
        if not segments:
            res = TranscriptionResult.from_text(
                entry.text, duration=entry.duration, title=title
            )
            object.__setattr__(res, "created_at", created)
            return res
        return TranscriptionResult(segments=segments, title=title, created_at=created)

    def _format_result(self, result: TranscriptionResult, ext: str) -> str:
        if ext == "srt":
            return to_srt(result)
        elif ext == "json":
            return to_json(result)
        elif ext == "html":
            return to_html(result)
        elif ext == "md":
            return to_markdown(result)
        else:
            return to_txt(result)

    def _delete_entry(self) -> None:
        selected_ranges = self.table.selectedRanges()
        selected_rows = []
        for r in selected_ranges:
            for row in range(r.topRow(), r.bottomRow() + 1):
                if row not in selected_rows:
                    selected_rows.append(row)
        selected_rows.sort()

        if not selected_rows:
            return

        entries = [
            self.current_entries[r]
            for r in selected_rows
            if 0 <= r < len(self.current_entries)
        ]
        if not entries:
            return

        if len(entries) > 1:
            reply = QMessageBox.question(
                self,
                "Delete Multiple Transcriptions",
                f"Are you sure you want to permanently delete {len(entries)} selected dictations and their audio?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                for entry in entries:
                    self.archive.delete_entry(entry.id, delete_audio_file=True)
                self._load_entries()
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

    def _cut_audio_snippet(self) -> None:
        if not self.selected_entry or not self.selected_entry.audio_path:
            return

        entry = self.selected_entry
        duration = entry.duration or 60.0

        from PySide6.QtWidgets import QInputDialog

        start_val, ok1 = QInputDialog.getDouble(
            self,
            "Cut Audio Snippet",
            f"Enter start time in seconds (0.0 to {duration:.2f}):",
            0.0,
            0.0,
            duration,
            2,
        )
        if not ok1:
            return

        end_val, ok2 = QInputDialog.getDouble(
            self,
            "Cut Audio Snippet",
            f"Enter end time in seconds ({start_val:.2f} to {duration:.2f}):",
            min(start_val + 5.0, duration),
            start_val,
            duration,
            2,
        )
        if not ok2:
            return

        if end_val <= start_val:
            QMessageBox.warning(
                self, "Invalid Ranges", "End time must be greater than start time."
            )
            return

        default_name = (
            f"snippet_{entry.id[:8]}_{int(start_val)}s_to_{int(end_val)}s.wav"
        )
        dest_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Cut Audio Snippet",
            default_name,
            "WAV Audio (*.wav)",
        )
        if not dest_path:
            return

        import wave
        import tempfile

        temp_src = None
        try:
            src_path = entry.audio_path
            with open(src_path, "rb") as f:
                header = f.read(10)
            if header.startswith(b"VAULT_ENC:"):
                fd, tmp = tempfile.mkstemp(suffix=".wav")
                os.close(fd)
                self.archive.export_audio(entry.id, tmp)
                temp_src = tmp
                src_path = tmp

            with wave.open(src_path, "rb") as src:
                params = src.getparams()
                sample_rate = params.framerate

                start_frame = int(start_val * sample_rate)
                end_frame = int(end_val * sample_rate)
                num_frames = end_frame - start_frame

                src.setpos(start_frame)
                frames_data = src.readframes(num_frames)

            with wave.open(dest_path, "wb") as dst:
                dst.setparams(params)
                dst.writeframes(frames_data)

            QMessageBox.information(
                self,
                "Snippet Extracted",
                f"Successfully extracted {end_val - start_val:.2f}s audio snippet to:\n{dest_path}",
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Extraction Failed", f"Failed to cut snippet: {e}"
            )
        finally:
            if temp_src and os.path.exists(temp_src):
                try:
                    os.remove(temp_src)
                except Exception:
                    pass

    def closeEvent(self, event) -> None:
        if self.player:
            self.player.stop()
        if self._temp_playback_file and os.path.exists(self._temp_playback_file):
            try:
                os.remove(self._temp_playback_file)
            except Exception:
                pass
        super().closeEvent(event)
