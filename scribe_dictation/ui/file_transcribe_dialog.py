"""
Batch Audio File Transcriber Dialog for Privacy Scribe Pro.
"""

import os
import threading
from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QProgressBar,
    QPlainTextEdit,
    QFileDialog,
    QMessageBox,
)

from scribe_dictation.audio.file_transcriber import transcribe_audio_file
from scribe_dictation.export import to_markdown, to_srt, to_txt


class FileTranscribeDialog(QDialog):
    """Transcribe audio & video files with progress tracking."""

    progress_signal = Signal(float, str)
    finished_signal = Signal(object)
    error_signal = Signal(str)

    def __init__(self, transcriber, parent=None):
        super().__init__(parent)
        self.transcriber = transcriber
        self.result = None

        self.setWindowTitle("Transcribe Audio File — Privacy Scribe Pro")
        self.setMinimumSize(580, 440)
        self.resize(640, 480)

        self.progress_signal.connect(self._on_progress)
        self.finished_signal.connect(self._on_finished)
        self.error_signal.connect(self._on_error)

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header = QLabel(
            "<b>Batch Audio & Video File Transcription</b><br>"
            "<span style='color: #718096; font-size: 11px;'>"
            "Select any .mp3, .wav, .m4a, .ogg, .flac, or .mp4 file to transcribe offline or via API."
            "</span>"
        )
        layout.addWidget(header)

        # File selector row
        file_row = QHBoxLayout()
        self.file_path_input = QLineEdit()
        self.file_path_input.setPlaceholderText("Select an audio or video file...")
        self.file_path_input.setReadOnly(True)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_file)

        self.start_btn = QPushButton("Transcribe")
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self._start_transcription)

        file_row.addWidget(self.file_path_input)
        file_row.addWidget(browse_btn)
        file_row.addWidget(self.start_btn)
        layout.addLayout(file_row)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #4a5568; font-size: 11px;")
        layout.addWidget(self.status_label)

        # Output text area
        self.output_text = QPlainTextEdit()
        self.output_text.setPlaceholderText("Transcription output will appear here...")
        layout.addWidget(self.output_text)

        # Action buttons
        btn_row = QHBoxLayout()
        self.copy_btn = QPushButton("📋 Copy Text")
        self.copy_btn.setEnabled(False)
        self.copy_btn.clicked.connect(self._copy_output)

        self.export_btn = QPushButton("💾 Export...")
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self._export_output)

        btn_row.addWidget(self.copy_btn)
        btn_row.addWidget(self.export_btn)
        btn_row.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)

        layout.addLayout(btn_row)

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Audio / Video File",
            "",
            "Audio & Video Files (*.mp3 *.wav *.m4a *.ogg *.flac *.mp4);;All Files (*.*)",
        )
        if path:
            self.file_path_input.setText(path)
            self.start_btn.setEnabled(True)

    def _start_transcription(self):
        path = self.file_path_input.text()
        if not path or not os.path.exists(path):
            QMessageBox.warning(
                self, "Invalid File", "Please select a valid audio file."
            )
            return

        self.start_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("Starting transcription...")
        self.output_text.clear()

        def _worker():
            try:

                def _cb(progress, msg):
                    self.progress_signal.emit(progress, msg)

                result = transcribe_audio_file(
                    path, self.transcriber, progress_callback=_cb
                )
                self.finished_signal.emit(result)
            except Exception as e:
                self.error_signal.emit(str(e))

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    @Slot(float, str)
    def _on_progress(self, progress: float, msg: str):
        self.progress_bar.setValue(int(progress * 100))
        self.status_label.setText(msg)

    @Slot(object)
    def _on_finished(self, result):
        self.result = result
        self.progress_bar.setValue(100)
        self.status_label.setText("✓ Transcription Complete!")
        self.start_btn.setEnabled(True)
        self.copy_btn.setEnabled(True)
        self.export_btn.setEnabled(True)
        self.output_text.setPlainText(result.text)

    @Slot(str)
    def _on_error(self, err_msg: str):
        self.start_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText(f"Error: {err_msg}")
        QMessageBox.critical(
            self, "Transcription Error", f"Failed to transcribe file:\n{err_msg}"
        )

    def _copy_output(self):
        import pyperclip

        pyperclip.copy(self.output_text.toPlainText())
        self.status_label.setText("✓ Copied to clipboard!")

    def _export_output(self):
        if not self.result:
            return
        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export File Transcription",
            "file_transcription.txt",
            "Plain Text (*.txt);;Markdown (*.md);;SubRip Subtitle (*.srt)",
        )
        if not path:
            return
        if path.endswith(".md") or "Markdown" in selected_filter:
            content = to_markdown(self.result)
        elif path.endswith(".srt") or "SubRip" in selected_filter:
            content = to_srt(self.result)
        else:
            content = to_txt(self.result)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        self.status_label.setText(f"✓ Exported to {path}")
