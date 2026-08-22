"""Voice Calibration Wizard, Accuracy Training Library, and Local Model Manager Dialog."""

from __future__ import annotations

import os
import time
from typing import Optional

import numpy as np
from PySide6.QtCore import QThread, Signal, Slot, Qt, QSettings
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QTabWidget,
    QWidget,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QProgressBar,
)

from scribe_dictation.audio.capture import AudioRecorder
from scribe_dictation.tuning.voice_lab import (
    CALIBRATION_SENTENCES,
    CalibrationResult,
    VoiceCalibrationRunner,
)
from scribe_dictation.tuning.diff_learner import DiffLearner
from scribe_dictation.history.archive import TranscriptionArchive
from scribe_dictation.transcribe import CustomVocabularyManager, LocalModelManager


TRAINING_PROMPTS = [
    "The quick brown fox jumps over the lazy dog.",
    "Acoustic models adapt to unique accents and speech patterns.",
    "Privacy Scribe processes dictation securely and privately on my local computer.",
    "Python is an interpreted, high-level, general-purpose programming language.",
    "The software uses local offline whisper models for high accuracy speech recognition.",
]


class CalibrationWorker(QThread):
    """Background worker for analyzing recorded calibration audio."""

    finished_signal = Signal(object)
    error_signal = Signal(str)

    def __init__(
        self,
        runner: VoiceCalibrationRunner,
        audio_file: str,
        expected_word_count: int,
    ) -> None:
        super().__init__()
        self.runner = runner
        self.audio_file = audio_file
        self.expected_word_count = expected_word_count

    def run(self) -> None:
        try:
            result = self.runner.analyze_file(
                self.audio_file,
                expected_word_count=self.expected_word_count,
            )
            self.finished_signal.emit(result)
        except Exception as e:
            self.error_signal.emit(str(e))


class ModelDownloadWorker(QThread):
    """Background worker for downloading/updating local Whisper models."""

    finished_signal = Signal(bool, str)
    status_signal = Signal(str)

    def __init__(self, model_size: str) -> None:
        super().__init__()
        self.model_size = model_size

    def run(self) -> None:
        try:
            self.status_signal.emit(
                f"Downloading/Updating '{self.model_size}' model..."
            )
            path = LocalModelManager.download_or_update(self.model_size)
            self.finished_signal.emit(True, f"Model downloaded successfully to {path}")
        except Exception as e:
            self.finished_signal.emit(False, str(e))


class TrainingWorker(QThread):
    """Background worker for training the model (transcribing, running diff learner, acoustic calibration)."""

    finished_signal = Signal(
        int, float, float, float
    )  # rules_count, silence_thresh, silence_timeout, gain
    error_signal = Signal(str)
    status_signal = Signal(str)

    def __init__(self, archive, vocab_manager, diff_learner, calibration_runner):
        super().__init__()
        self.archive = archive
        self.vocab_manager = vocab_manager
        self.diff_learner = diff_learner
        self.calibration_runner = calibration_runner

    def run(self) -> None:
        try:
            self.status_signal.emit("Fetching training library entries...")
            entries = self.archive.search(tag="training", limit=50)
            if not entries:
                self.error_signal.emit(
                    "No training samples found in your library. Record some samples first."
                )
                return

            # Initialize local whisper model for transcribing training audio
            from scribe_dictation.transcribe.local import LocalWhisperService

            model_size = self.vocab_manager.settings.value("local_model_size", "base")
            self.status_signal.emit(f"Initializing local model '{model_size}'...")
            service = LocalWhisperService(model_size=model_size)

            learned_rules_count = 0
            all_rms = []
            all_peak = []
            all_noise = []
            all_snr = []

            for idx, entry in enumerate(entries, 1):
                if not entry.audio_path or not os.path.exists(entry.audio_path):
                    continue

                self.status_signal.emit(f"Processing sample {idx}/{len(entries)}...")
                import tempfile

                temp_src = None
                src_path = entry.audio_path
                with open(src_path, "rb") as f:
                    header = f.read(10)
                if header.startswith(b"VAULT_ENC:"):
                    fd, tmp = tempfile.mkstemp(suffix=".wav")
                    os.close(fd)
                    self.archive.export_audio(entry.id, tmp)
                    temp_src = tmp
                    src_path = tmp

                try:
                    raw_tx = service.transcribe(src_path)
                    suggestions = self.diff_learner.extract_replacements(
                        raw_tx, entry.text
                    )
                    if suggestions:
                        added = self.diff_learner.apply_to_vocabulary(
                            suggestions,
                            self.vocab_manager,
                            min_confidence=0.5,
                            save=False,
                        )
                        learned_rules_count += len(added)

                    cal_res = self.calibration_runner.analyze_file(src_path)
                    all_rms.append(cal_res.average_rms)
                    all_peak.append(cal_res.peak_amplitude)
                    all_noise.append(cal_res.noise_floor_rms)
                    all_snr.append(cal_res.snr_db)
                finally:
                    if temp_src and os.path.exists(temp_src):
                        try:
                            os.remove(temp_src)
                        except Exception:
                            pass

            self.status_signal.emit("Saving learned profile parameters...")
            self.vocab_manager.save()

            avg_noise = sum(all_noise) / len(all_noise) if all_noise else 0.005
            avg_peak = sum(all_peak) / len(all_peak) if all_peak else 0.2

            recommended_threshold = float(np.clip(avg_noise * 1.8 + 0.002, 0.005, 0.08))
            recommended_timeout = 1.5
            if all_snr:
                recommended_timeout = 1.5

            recommended_gain = 1.0
            if avg_peak > 0.01:
                recommended_gain = float(np.clip(0.75 / avg_peak, 0.5, 3.5))

            self.finished_signal.emit(
                learned_rules_count,
                recommended_threshold,
                recommended_timeout,
                recommended_gain,
            )
        except Exception as e:
            self.error_signal.emit(str(e))


class VoiceLabDialog(QDialog):
    """Voice Calibration, Training, and Local Model Manager Dialog."""

    calibration_applied = Signal(object)

    def __init__(
        self, parent=None, runner: Optional[VoiceCalibrationRunner] = None
    ) -> None:
        super().__init__(parent)
        self.runner = runner or VoiceCalibrationRunner()
        self.recorder = AudioRecorder()
        self.sentences = CALIBRATION_SENTENCES
        self.current_sentence_idx = 0
        self.recorded_file: Optional[str] = None
        self.latest_result: Optional[CalibrationResult] = None
        self._worker: Optional[CalibrationWorker] = None
        self._download_worker: Optional[ModelDownloadWorker] = None
        self._training_worker: Optional[TrainingWorker] = None

        # Try to resolve dependencies from parent
        self.settings = None
        self.archive = None
        self.vocab_manager = None
        self.diff_learner = None

        if parent:
            self.settings = getattr(parent, "settings", None)
            self.archive = getattr(parent, "archive", None)
            self.vocab_manager = getattr(parent, "vocabulary_manager", None)
            self.diff_learner = getattr(parent, "diff_learner", None)

        if not self.settings:
            self.settings = QSettings("PrivacyScribe", "Privacy Scribe")
        if not self.archive:
            self.archive = TranscriptionArchive()
        if not self.vocab_manager:
            self.vocab_manager = CustomVocabularyManager(settings=self.settings)
        if not self.diff_learner:
            self.diff_learner = DiffLearner()

        self.setWindowTitle("Voice Lab & Accuracy Calibration — Privacy Scribe Pro")
        self.setMinimumSize(750, 620)
        self.resize(800, 650)

        self._setup_ui()
        self._load_sentence(0)
        self._refresh_training_library()
        self._refresh_model_cache_status()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Tab Widget
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Tab 1: Acoustic Calibration
        self.tabs.addTab(self._create_calibration_tab(), "🎙️ Acoustic Calibration")

        # Tab 2: Voice Training Library
        self.tabs.addTab(self._create_training_tab(), "📚 Voice Training Library")

        # Tab 3: Model Manager
        self.tabs.addTab(self._create_model_tab(), "⚙️ Local Model Manager")

        # Close Row
        close_layout = QHBoxLayout()
        close_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        close_layout.addWidget(close_btn)
        layout.addLayout(close_layout)

    def _create_calibration_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        header = QLabel(
            "<b>🎙️ Acoustic Calibration Wizard</b><br>"
            "<span style='color: #718096; font-size: 11px;'>"
            "Read the phonetically balanced calibration sentence below to measure speaking speed (WPM), "
            "vocal amplitude, signal-to-noise ratio, and calibrate optimal microphone silence thresholds."
            "</span>"
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        selector_layout = QHBoxLayout()
        selector_layout.addWidget(QLabel("Calibration Target:"))
        self.sentence_combo = QComboBox()
        for s in self.sentences:
            self.sentence_combo.addItem(f"{s.target_category} ({s.word_count} words)")
        self.sentence_combo.currentIndexChanged.connect(self._on_sentence_changed)
        selector_layout.addWidget(self.sentence_combo)
        layout.addLayout(selector_layout)

        prompt_group = QGroupBox("Reading Prompt")
        prompt_layout = QVBoxLayout(prompt_group)
        self.prompt_display = QTextEdit()
        self.prompt_display.setReadOnly(True)
        self.prompt_display.setFixedHeight(90)
        self.prompt_display.setStyleSheet(
            "font-size: 14px; font-weight: 500; padding: 8px; "
            "background-color: #f7fafc; border: 1px solid #e2e8f0; border-radius: 6px;"
        )
        prompt_layout.addWidget(self.prompt_display)

        self.phoneme_label = QLabel()
        self.phoneme_label.setStyleSheet(
            "color: #4a5568; font-size: 11px; font-style: italic;"
        )
        prompt_layout.addWidget(self.phoneme_label)
        layout.addWidget(prompt_group)

        rec_layout = QHBoxLayout()
        self.record_btn = QPushButton("🔴 Start Calibration Recording")
        self.record_btn.setStyleSheet(
            "QPushButton { background-color: #e53e3e; color: white; font-weight: bold; padding: 10px; border-radius: 6px; } "
            "QPushButton:hover { background-color: #c53030; }"
        )
        self.record_btn.clicked.connect(self._toggle_recording)
        rec_layout.addWidget(self.record_btn)

        self.status_label = QLabel("Ready to record.")
        self.status_label.setStyleSheet("color: #4a5568; font-weight: bold;")
        rec_layout.addWidget(self.status_label)
        layout.addLayout(rec_layout)

        metrics_group = QGroupBox("Diagnostic Results & Acoustic Profile")
        self.metrics_layout = QGridLayout(metrics_group)
        self.metrics_layout.setSpacing(10)

        self.wpm_label = QLabel("—")
        self.snr_label = QLabel("—")
        self.rms_label = QLabel("—")
        self.threshold_label = QLabel("—")
        self.gain_label = QLabel("—")
        self.grade_label = QLabel("—")

        self._add_metric_row("Speaking Cadence (WPM):", self.wpm_label, 0)
        self._add_metric_row("Signal-to-Noise Ratio:", self.snr_label, 1)
        self._add_metric_row("Average Vocal RMS:", self.rms_label, 2)
        self._add_metric_row("Recommended Silence Gate:", self.threshold_label, 3)
        self._add_metric_row("Suggested Input Gain:", self.gain_label, 4)
        self._add_metric_row("Audio Clarity Grade:", self.grade_label, 5)

        layout.addWidget(metrics_group)

        self.feedback_box = QTextEdit()
        self.feedback_box.setReadOnly(True)
        self.feedback_box.setFixedHeight(80)
        self.feedback_box.setPlaceholderText(
            "Diagnostic feedback and recommendations will appear here after recording..."
        )
        self.feedback_box.setStyleSheet(
            "font-size: 11px; background-color: #f8fafc; color: #2d3748;"
        )
        layout.addWidget(self.feedback_box)

        btn_layout = QHBoxLayout()
        self.apply_btn = QPushButton("✨ Apply Calibrated Settings")
        self.apply_btn.setEnabled(False)
        self.apply_btn.setStyleSheet(
            "QPushButton { background-color: #3182ce; color: white; font-weight: bold; padding: 8px 16px; border-radius: 6px; } "
            "QPushButton:hover { background-color: #2b6cb0; }"
        )
        self.apply_btn.clicked.connect(self._apply_settings)
        btn_layout.addStretch()
        btn_layout.addWidget(self.apply_btn)
        layout.addLayout(btn_layout)

        return widget

    def _create_training_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)

        header = QLabel(
            "<b>📚 Voice Training Library</b><br>"
            "<span style='color: #718096; font-size: 11px;'>"
            "Record diverse training samples to adapt Scribe to your unique voice, accent, and vocabulary. "
            "Running profile adaptation trains the local dictionary and acoustic gating profile privately."
            "</span>"
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        # Training Prompts list
        prompts_group = QGroupBox("Select Training prompt to record:")
        prompts_layout = QVBoxLayout(prompts_group)
        self.train_prompt_combo = QComboBox()
        for idx, p in enumerate(TRAINING_PROMPTS, 1):
            self.train_prompt_combo.addItem(f"Prompt #{idx}: {p[:60]}...", p)
        prompts_layout.addWidget(self.train_prompt_combo)

        # Record Sample Button
        rec_row = QHBoxLayout()
        self.train_record_btn = QPushButton("🎙️ Record Training Sample")
        self.train_record_btn.setStyleSheet("font-weight: bold; padding: 8px;")
        self.train_record_btn.clicked.connect(self._toggle_training_recording)
        rec_row.addWidget(self.train_record_btn)
        self.train_rec_status = QLabel("Ready.")
        rec_row.addWidget(self.train_rec_status)
        prompts_layout.addLayout(rec_row)
        layout.addWidget(prompts_group)

        # Table of training clips
        self.train_table = QTableWidget()
        self.train_table.setColumnCount(3)
        self.train_table.setHorizontalHeaderLabels(
            ["Recorded Date", "Audio snippet", "Transcript (double-click to edit)"]
        )
        self.train_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.train_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self.train_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self.train_table.itemChanged.connect(self._on_training_item_edited)
        layout.addWidget(self.train_table)

        # Training action buttons
        actions_layout = QHBoxLayout()
        self.run_training_btn = QPushButton("⚙️ Run Profile Adaptation Training")
        self.run_training_btn.setStyleSheet(
            "QPushButton { background-color: #2b6cb0; color: white; font-weight: bold; padding: 8px; border-radius: 6px; }"
            "QPushButton:hover { background-color: #2b6cb0; }"
        )
        self.run_training_btn.clicked.connect(self._run_adaptation_training)
        actions_layout.addWidget(self.run_training_btn)

        self.clear_training_btn = QPushButton("Clear Library")
        self.clear_training_btn.clicked.connect(self._clear_training_library)
        actions_layout.addWidget(self.clear_training_btn)

        layout.addLayout(actions_layout)

        # Progress bar/label
        self.training_progress_label = QLabel("")
        self.training_progress_label.setStyleSheet("color: #2b6cb0; font-weight: bold;")
        layout.addWidget(self.training_progress_label)

        return widget

    def _create_model_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        header = QLabel(
            "<b>⚙️ Local Offline model Manager & Updater</b><br>"
            "<span style='color: #718096; font-size: 11px;'>"
            "Check local download status and pull the latest open-source Whisper model files from Hugging Face Hub. "
            "Updating ensures compatibility and patches acoustic decoder updates."
            "</span>"
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        # Model selection grid
        self.model_table = QTableWidget()
        self.model_table.setColumnCount(3)
        self.model_table.setHorizontalHeaderLabels(
            ["Model Size", "Description", "Download Status"]
        )
        self.model_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.model_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.model_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        layout.addWidget(self.model_table)

        # Actions
        actions_row = QHBoxLayout()
        self.download_model_btn = QPushButton("📥 Download / Update Selected Model")
        self.download_model_btn.setStyleSheet("font-weight: bold; padding: 8px;")
        self.download_model_btn.clicked.connect(self._download_selected_model)
        actions_row.addWidget(self.download_model_btn)

        self.check_model_updates_btn = QPushButton("🔄 Check for Updates")
        self.check_model_updates_btn.clicked.connect(self._refresh_model_cache_status)
        actions_row.addWidget(self.check_model_updates_btn)
        layout.addLayout(actions_row)

        # Progress bar
        self.model_progress = QProgressBar()
        self.model_progress.setRange(0, 0)  # Indeterminate progress
        self.model_progress.setVisible(False)
        layout.addWidget(self.model_progress)

        self.model_status_lbl = QLabel("")
        self.model_status_lbl.setStyleSheet("color: #2b6cb0; font-weight: bold;")
        layout.addWidget(self.model_status_lbl)

        return widget

    def _add_metric_row(self, title: str, label_widget: QLabel, row: int) -> None:
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("color: #4a5568; font-weight: 500;")
        label_widget.setStyleSheet("font-weight: bold; color: #1a202c;")
        self.metrics_layout.addWidget(title_lbl, row, 0)
        self.metrics_layout.addWidget(label_widget, row, 1)

    def _load_sentence(self, idx: int) -> None:
        if 0 <= idx < len(self.sentences):
            self.current_sentence_idx = idx
            s = self.sentences[idx]
            self.prompt_display.setText(s.text)
            self.phoneme_label.setText(f"Target Phonetics: {s.target_phonemes}")

    def _on_sentence_changed(self, idx: int) -> None:
        self._load_sentence(idx)

    # ── Acoustic Calibration Tab Actions ─────────────────────────────

    def _toggle_recording(self) -> None:
        if not self.recorder.is_recording:
            try:
                self.recorder.start()
                self.record_btn.setText("⏹️ Stop & Calibrate")
                self.record_btn.setStyleSheet(
                    "QPushButton { background-color: #38a169; color: white; font-weight: bold; padding: 10px; border-radius: 6px; } "
                    "QPushButton:hover { background-color: #2f855a; }"
                )
                self.status_label.setText("🎙️ Listening... Read prompt aloud.")
                self.apply_btn.setEnabled(False)
            except Exception as e:
                QMessageBox.critical(
                    self, "Recording Error", f"Failed to start audio recording: {e}"
                )
        else:
            try:
                self.status_label.setText("Analyzing audio metrics...")
                self.recorded_file = self.recorder.stop()
                self.record_btn.setText("🔴 Start Calibration Recording")
                self.record_btn.setStyleSheet(
                    "QPushButton { background-color: #e53e3e; color: white; font-weight: bold; padding: 10px; border-radius: 6px; } "
                    "QPushButton:hover { background-color: #c53030; }"
                )

                sentence = self.sentences[self.current_sentence_idx]
                self._worker = CalibrationWorker(
                    runner=self.runner,
                    audio_file=self.recorded_file,
                    expected_word_count=sentence.word_count,
                )
                self._worker.finished_signal.connect(self._on_calibration_finished)
                self._worker.error_signal.connect(self._on_calibration_error)
                self._worker.start()
            except Exception as e:
                self.status_label.setText("Recording failed.")
                QMessageBox.critical(
                    self, "Analysis Error", f"Failed to process recording: {e}"
                )

    @Slot(object)
    def _on_calibration_finished(self, result: CalibrationResult) -> None:
        self.latest_result = result
        self.status_label.setText("Calibration complete!")
        self.apply_btn.setEnabled(True)

        self.wpm_label.setText(
            f"{result.wpm} WPM ({result.spoken_word_count} words in {result.duration_seconds}s)"
        )
        self.snr_label.setText(f"{result.snr_db} dB")
        self.rms_label.setText(
            f"{result.average_rms:.4f} (Peak: {result.peak_amplitude:.2f})"
        )
        self.threshold_label.setText(
            f"{result.recommended_silence_threshold:.4f} RMS (Timeout: {result.recommended_silence_duration}s)"
        )
        self.gain_label.setText(f"{result.recommended_gain_factor}x multiplier")

        grade_color = {
            "Excellent": "#2f855a",
            "Good": "#3182ce",
            "Fair": "#dd6b20",
            "Poor": "#e53e3e",
        }.get(result.quality_grade, "#2d3748")

        self.grade_label.setText(
            f"<span style='color: {grade_color}; font-size: 13px; font-weight: bold;'>{result.quality_grade}</span>"
        )

        notes = "\n• ".join([""] + result.feedback_notes)
        self.feedback_box.setText(f"Analysis Summary:{notes}")

    @Slot(str)
    def _on_calibration_error(self, err_msg: str) -> None:
        self.status_label.setText("Calibration failed.")
        QMessageBox.warning(
            self, "Calibration Error", f"Could not analyze audio: {err_msg}"
        )

    def _apply_settings(self) -> None:
        if not self.latest_result:
            return

        self.calibration_applied.emit(self.latest_result)
        QMessageBox.information(
            self,
            "Calibration Applied",
            f"Successfully applied calibrated settings:\n"
            f"• Silence Threshold: {self.latest_result.recommended_silence_threshold}\n"
            f"• Silence Timeout: {self.latest_result.recommended_silence_duration}s\n"
            f"• Speaking Cadence: {self.latest_result.wpm} WPM",
        )

    # ── Voice Training Library Tab Actions ────────────────────────────

    def _refresh_training_library(self) -> None:
        self.train_table.blockSignals(True)
        try:
            entries = self.archive.search(tag="training", limit=50)
            self.train_table.setRowCount(len(entries))

            for idx, entry in enumerate(entries):
                dt_str = time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(entry.timestamp)
                )
                item_date = QTableWidgetItem(dt_str)
                item_date.setFlags(item_date.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item_date.setData(Qt.ItemDataRole.UserRole, entry.id)
                self.train_table.setItem(idx, 0, item_date)

                item_audio = QTableWidgetItem("🎙️ WAV file")
                item_audio.setFlags(item_audio.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.train_table.setItem(idx, 1, item_audio)

                item_text = QTableWidgetItem(entry.text)
                self.train_table.setItem(idx, 2, item_text)
        except Exception as e:
            print(f"Error loading training library: {e}")
        finally:
            self.train_table.blockSignals(False)

    def _toggle_training_recording(self) -> None:
        if not self.recorder.is_recording:
            try:
                self.recorder.start()
                self.train_record_btn.setText("⏹️ Stop Recording")
                self.train_rec_status.setText(
                    "Recording... Read the chosen prompt aloud."
                )
            except Exception as e:
                QMessageBox.critical(
                    self, "Recording Error", f"Failed to record training sample: {e}"
                )
        else:
            try:
                audio_file = self.recorder.stop()
                self.train_record_btn.setText("🎙️ Record Training Sample")
                self.train_rec_status.setText(
                    "Processing & transcribing training clip..."
                )

                prompt_text = self.train_prompt_combo.currentData()

                # Add to local archive under training tag
                self.archive.add_entry(
                    text=prompt_text,
                    audio_source_path=audio_file,
                    duration=5.0,  # approximate duration
                    tags=["training"],
                )
                self._refresh_training_library()
                self.train_rec_status.setText("Recorded & added to library.")
            except Exception as e:
                self.train_rec_status.setText("Failed to save.")
                QMessageBox.critical(
                    self, "Save Error", f"Failed to save training sample: {e}"
                )

    def _on_training_item_edited(self, item: QTableWidgetItem) -> None:
        if item.column() == 2:
            row = item.row()
            date_item = self.train_table.item(row, 0)
            if date_item:
                entry_id = date_item.data(Qt.ItemDataRole.UserRole)
                entry = self.archive.get_entry(entry_id)
                if entry:
                    # Update ground truth text in SQLite
                    self.archive.add_entry(
                        text=item.text().strip(),
                        audio_source_path=entry.audio_path,
                        duration=entry.duration,
                        tags=entry.tags,
                        metadata=entry.metadata,
                        entry_id=entry.id,
                    )

    def _clear_training_library(self) -> None:
        reply = QMessageBox.question(
            self,
            "Clear Training Library",
            "Are you sure you want to delete all training voice samples from your local storage?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            entries = self.archive.search(tag="training", limit=100)
            for entry in entries:
                self.archive.delete_entry(entry.id)
            self._refresh_training_library()

    def _run_adaptation_training(self) -> None:
        self.training_progress_label.setText("Starting profile adaptation training...")
        self.run_training_btn.setEnabled(False)

        self._training_worker = TrainingWorker(
            self.archive, self.vocab_manager, self.diff_learner, self.runner
        )
        self._training_worker.status_signal.connect(
            self.training_progress_label.setText
        )
        self._training_worker.finished_signal.connect(self._on_training_complete)
        self._training_worker.error_signal.connect(self._on_training_error)
        self._training_worker.start()

    @Slot(int, float, float, float)
    def _on_training_complete(
        self, count: int, threshold: float, timeout: float, gain: float
    ) -> None:
        self.run_training_btn.setEnabled(True)
        self.training_progress_label.setText("Training profile adaptation complete.")

        # Save Calibrated acoustic params to QSettings
        self.settings.setValue("silence_threshold", threshold)
        self.settings.setValue("silence_duration", timeout)
        self.settings.setValue("gain_factor", gain)

        QMessageBox.information(
            self,
            "Training Complete",
            f"Voice profile training complete!\n\n"
            f"• Learned Vocabulary Rules: {count} corrections added.\n"
            f"• Calibrated Silence Gate: {threshold:.4f} RMS\n"
            f"• Calibrated Speaking Timeout: {timeout:.2f}s\n"
            f"• Calibrated Input Gain: {gain:.2f}x\n\n"
            f"Settings have been saved and applied to your voice profile.",
        )

    @Slot(str)
    def _on_training_error(self, err: str) -> None:
        self.run_training_btn.setEnabled(True)
        self.training_progress_label.setText("Training failed.")
        QMessageBox.warning(self, "Training Error", err)

    # ── Model Manager Tab Actions ─────────────────────────────────────

    def _refresh_model_cache_status(self) -> None:
        models = [
            (
                "tiny",
                "tiny (Ultra Fast / ~75MB)",
                "huggingface/hub/models--Systran--faster-whisper-tiny",
            ),
            (
                "base",
                "base (Default / ~140MB)",
                "huggingface/hub/models--Systran--faster-whisper-base",
            ),
            (
                "small",
                "small (Better Quality / ~460MB)",
                "huggingface/hub/models--Systran--faster-whisper-small",
            ),
            (
                "medium",
                "medium (High Accuracy / ~1.5GB)",
                "huggingface/hub/models--Systran--faster-whisper-medium",
            ),
            (
                "large-v3",
                "large-v3 (Studio Grade / ~3.0GB)",
                "huggingface/hub/models--Systran--faster-whisper-large-v3",
            ),
        ]

        self.model_table.setRowCount(len(models))
        for idx, (size, desc, _) in enumerate(models):
            item_size = QTableWidgetItem(size)
            item_size.setFlags(item_size.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.model_table.setItem(idx, 0, item_size)

            item_desc = QTableWidgetItem(desc)
            item_desc.setFlags(item_desc.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.model_table.setItem(idx, 1, item_desc)

            cached = LocalModelManager.is_model_cached(size)
            status_str = "✅ Cached & Ready" if cached else "❌ Not Downloaded"
            item_status = QTableWidgetItem(status_str)
            item_status.setFlags(item_status.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.model_table.setItem(idx, 2, item_status)

    def _download_selected_model(self) -> None:
        selected_indexes = self.model_table.selectedIndexes()
        if not selected_indexes:
            QMessageBox.warning(
                self, "No Selection", "Please select a model row in the table first."
            )
            return

        row = selected_indexes[0].row()
        model_size = self.model_table.item(row, 0).text()

        self.download_model_btn.setEnabled(False)
        self.model_progress.setVisible(True)

        self._download_worker = ModelDownloadWorker(model_size)
        self._download_worker.status_signal.connect(self.model_status_lbl.setText)
        self._download_worker.finished_signal.connect(self._on_download_complete)
        self._download_worker.start()

    @Slot(bool, str)
    def _on_download_complete(self, success: bool, msg: str) -> None:
        self.download_model_btn.setEnabled(True)
        self.model_progress.setVisible(False)
        self._refresh_model_cache_status()

        if success:
            self.model_status_lbl.setText("Download complete.")
            QMessageBox.information(self, "Success", msg)
        else:
            self.model_status_lbl.setText("Download failed.")
            QMessageBox.warning(
                self, "Download Error", f"Failed to download model files: {msg}"
            )
