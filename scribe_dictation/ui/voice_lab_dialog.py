"""Voice Calibration Wizard & Accuracy Lab Dialog for Privacy Scribe Pro."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QThread, Signal, Slot
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
)

from scribe_dictation.audio.capture import AudioRecorder
from scribe_dictation.tuning.voice_lab import (
    CALIBRATION_SENTENCES,
    CalibrationResult,
    VoiceCalibrationRunner,
)


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


class VoiceLabDialog(QDialog):
    """Guided Voice Calibration Wizard for Privacy Scribe."""

    calibration_applied = Signal(object)  # Emits CalibrationResult when applied

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

        self.setWindowTitle("Voice Lab & Accuracy Calibration — Privacy Scribe Pro")
        self.setMinimumSize(640, 560)
        self.resize(700, 600)

        self._setup_ui()
        self._load_sentence(0)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header
        header = QLabel(
            "<b>🎙️ Voice Calibration Wizard & Accuracy Lab</b><br>"
            "<span style='color: #718096; font-size: 11px;'>"
            "Read the phonetically balanced calibration sentence below to measure speaking speed (WPM), "
            "vocal amplitude, signal-to-noise ratio, and calibrate optimal microphone silence thresholds."
            "</span>"
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        # Sentence Selector & Target Info
        selector_layout = QHBoxLayout()
        selector_layout.addWidget(QLabel("Calibration Target:"))
        self.sentence_combo = QComboBox()
        for s in self.sentences:
            self.sentence_combo.addItem(f"{s.target_category} ({s.word_count} words)")
        self.sentence_combo.currentIndexChanged.connect(self._on_sentence_changed)
        selector_layout.addWidget(self.sentence_combo)
        layout.addLayout(selector_layout)

        # Prompt Box
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

        # Recording Controls
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

        # Metrics Card
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

        # Feedback & Diagnostics Notes
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

        # Action Buttons
        btn_layout = QHBoxLayout()
        self.apply_btn = QPushButton("✨ Apply Calibrated Settings")
        self.apply_btn.setEnabled(False)
        self.apply_btn.setStyleSheet(
            "QPushButton { background-color: #3182ce; color: white; font-weight: bold; padding: 8px 16px; border-radius: 6px; } "
            "QPushButton:hover { background-color: #2b6cb0; }"
        )
        self.apply_btn.clicked.connect(self._apply_settings)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)

        btn_layout.addStretch()
        btn_layout.addWidget(self.apply_btn)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

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

    def _toggle_recording(self) -> None:
        if not self.recorder.is_recording:
            # Start recording
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
            # Stop recording and analyze
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

        # Update metrics labels
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

        # Feedback notes
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
        self.accept()
