import webbrowser
from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QMessageBox,
)
from scribe_dictation.licensing import (
    verify_license_online,
    PRODUCT_ID,
    LICENSE_PROVIDER,
)


class ActivationWorker(QThread):
    finished_signal = Signal(bool)

    def __init__(self, license_key: str):
        super().__init__()
        self.license_key = license_key

    def run(self):
        success = verify_license_online(self.license_key)
        self.finished_signal.emit(success)


class ActivationDialog(QDialog):
    """A premium, modern dialog for user license activation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Activate Scribe Dictation Pro")
        self.setFixedSize(480, 260)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        # Style sheet for modern premium look
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e2e;
                color: #cdd6f4;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QLabel {
                color: #cdd6f4;
            }
            QLineEdit {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 10px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 1px solid #89b4fa;
            }
            QPushButton {
                background-color: #89b4fa;
                color: #11111b;
                border: none;
                border-radius: 6px;
                padding: 10px 20px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #b4befe;
            }
            QPushButton:pressed {
                background-color: #74c7ec;
            }
            QPushButton:disabled {
                background-color: #585b70;
                color: #a6adc8;
            }
            QPushButton#secondary {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
            }
            QPushButton#secondary:hover {
                background-color: #45475a;
            }
            QPushButton#buy {
                background-color: #a6e3a1;
                color: #11111b;
            }
            QPushButton#buy:hover {
                background-color: #94e2d5;
            }
        """)

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Header Title
        title_label = QLabel("Scribe Dictation Pro")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        # Subtitle instructions
        subtitle_label = QLabel(
            "Please enter your license key to activate the Pro version."
        )
        subtitle_label.setFont(QFont("Segoe UI", 10))
        subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle_label.setWordWrap(True)
        layout.addWidget(subtitle_label)

        # License Input
        self.license_input = QLineEdit()
        self.license_input.setPlaceholderText("Enter your license key here...")
        layout.addWidget(self.license_input)

        # Status & Error message label
        self.status_label = QLabel("")
        self.status_label.setFont(QFont("Segoe UI", 9))
        self.status_label.setStyleSheet("color: #f38ba8;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        # Button Layout
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.buy_btn = QPushButton("Buy Pro ($19)")
        self.buy_btn.setObjectName("buy")
        self.buy_btn.clicked.connect(self._open_buy_page)
        btn_layout.addWidget(self.buy_btn)

        self.cancel_btn = QPushButton("Quit")
        self.cancel_btn.setObjectName("secondary")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        self.activate_btn = QPushButton("Activate")
        self.activate_btn.clicked.connect(self._start_activation)
        btn_layout.addWidget(self.activate_btn)

        layout.addLayout(btn_layout)
        self.worker = None

    def _open_buy_page(self):
        # TODO: replace with the real checkout URL once the Lemon Squeezy store/product
        # exists (see LEMONSQUEEZY_SETUP.md) — currently just the bare homepage.
        url = (
            f"https://gumroad.com/l/{PRODUCT_ID}"
            if LICENSE_PROVIDER == "gumroad"
            else "https://lemonsqueezy.com"
        )
        webbrowser.open(url)

    def _start_activation(self):
        key = self.license_input.text().strip()
        if not key:
            self.status_label.setText("License key cannot be empty.")
            return

        self.status_label.setStyleSheet("color: #89b4fa;")
        self.status_label.setText("Verifying license online...")
        self._set_controls_enabled(False)

        # Launch background thread to prevent UI freezing
        self.worker = ActivationWorker(key)
        self.worker.finished_signal.connect(self._on_activation_finished)
        self.worker.start()

    @Slot(bool)
    def _on_activation_finished(self, success: bool):
        self._set_controls_enabled(True)
        if success:
            QMessageBox.information(
                self, "Success", "Scribe Dictation Pro activated successfully!"
            )
            self.accept()
        else:
            self.status_label.setStyleSheet("color: #f38ba8;")
            self.status_label.setText(
                "Invalid license key. Please check and try again."
            )

    def _set_controls_enabled(self, enabled: bool):
        self.license_input.setEnabled(enabled)
        self.buy_btn.setEnabled(enabled)
        self.cancel_btn.setEnabled(enabled)
        self.activate_btn.setEnabled(enabled)
