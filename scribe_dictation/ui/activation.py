"""
Beautiful activation and paywall dialog for Scribe Dictation.
Designed with rich aesthetics: dark theme, gradients, rounded corners, and clean typography.

Hardened: captures machine fingerprint at activation time, passes it to LicenseService
so the cached license is bound to this machine. Falls back to self-signed verification.
"""

import threading
from typing import Optional
from PySide6.QtCore import Qt, Signal, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QPalette
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QGraphicsDropShadowEffect,
)
from scribe_dictation.licensing import LicenseService
from scribe_dictation.licensing.hardware import get_machine_fingerprint

BUY_URL = "https://gumroad.com/l/eyiexi"


class ActivationDialog(QDialog):
    """A gorgeous activation and paywall dialog for Scribe Dictation."""

    activated = Signal(str, dict)

    def __init__(self, parent=None, license_service: Optional[LicenseService] = None):
        super().__init__(parent)
        self.license_service = license_service or LicenseService()
        self._setup_ui()
        self._apply_styles()

    def _setup_ui(self):
        self.setWindowTitle("Activate Scribe Dictation")
        self.setFixedSize(480, 420)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(16)

        self.title_label = QLabel("Scribe Dictation")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle_label = QLabel("Private, instant, AI-powered desktop dictation.")
        self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.prompt_label = QLabel(
            "Enter your activation key to unlock lifetime access."
        )
        self.prompt_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.prompt_label.setWordWrap(True)

        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("Paste your license key here...")
        self.key_input.setFocus()

        self.activate_btn = QPushButton("Activate License")
        self.activate_btn.clicked.connect(self._on_activate_clicked)

        self.machine_label = QLabel("")
        self.machine_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.machine_label.setWordWrap(True)

        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setWordWrap(True)

        bottom_layout = QHBoxLayout()
        self.buy_btn = QPushButton("Don't have a key? Purchase one here →")
        self.buy_btn.setFlat(True)
        self.buy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.buy_btn.clicked.connect(self._on_buy_clicked)
        bottom_layout.addWidget(self.buy_btn)

        main_layout.addWidget(self.title_label)
        main_layout.addWidget(self.subtitle_label)
        main_layout.addWidget(self.prompt_label)
        main_layout.addWidget(self.key_input)
        main_layout.addWidget(self.activate_btn)
        main_layout.addWidget(self.machine_label)
        main_layout.addWidget(self.status_label)
        main_layout.addLayout(bottom_layout)

        main_layout.addLayout(bottom_layout)

    def _apply_styles(self):
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#121214"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#F3F4F6"))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        self.setStyleSheet("""
            QDialog { background: #121214; border-radius: 12px; }
            QLabel#title { font-size: 24px; font-weight: 700; color: #F3F4F6; }
            QLabel#subtitle { font-size: 14px; color: #A1A1AA; margin-bottom: 8px; }
            QLabel#prompt { font-size: 13px; color: #D4D4D8; margin-bottom: 4px; }
            QLineEdit {
                padding: 12px 16px; border: 1px solid #3F3F46; border-radius: 8px;
                background: #18181B; color: #F3F4F6; font-size: 14px; letter-spacing: 0.8px;
                selection-background-color: #8B5CF6;
            }
            QLineEdit:focus { border: 1px solid #8B5CF6; background: #1C1C1F; }
            QPushButton {
                background: #8B5CF6; color: white; border: none; border-radius: 8px;
                padding: 12px 24px; font-size: 14px; font-weight: 600;
            }
            QPushButton:hover { background: #7C3AED; }
            QPushButton:pressed { background: #6D28D9; }
            QPushButton:disabled { background: #3F3F46; color: #71717A; }
            QPushButton[flat="true"] {
                background: transparent; color: #8B5CF6; font-size: 12px; font-weight: 500;
                border: none; padding: 4px;
            }
            QPushButton[flat="true"]:hover { color: #A78BFA; }
            QLabel#status_err { color: #EF4444; font-size: 12px; font-weight: 500; }
            QLabel#status_ok { color: #10B981; font-size: 12px; font-weight: 500; }
            QLabel#status_info { color: #3B82F6; font-size: 12px; }
            QLabel#machine_label { color: #52525B; font-size: 10px; }
        """)
        self.title_label.setObjectName("title")
        self.subtitle_label.setObjectName("subtitle")
        self.prompt_label.setObjectName("prompt")
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 160))
        shadow.setOffset(0, 8)
        self.setGraphicsEffect(shadow)

    def _on_activate_clicked(self):
        key = self.key_input.text().strip()
        if not key:
            self._set_status("Please enter a license key.", is_error=True)
            return
        self.activate_btn.setEnabled(False)
        self.key_input.setEnabled(False)
        self._set_status("Verifying license key...", is_error=False, is_info=True)
        fingerprint = get_machine_fingerprint()
        threading.Thread(
            target=self._verify_async, args=(key, fingerprint), daemon=True
        ).start()

    def _verify_async(self, key: str, fingerprint: str):
        from scribe_dictation.licensing import cache_activation_v2

        svc = self.license_service
        is_valid, msg, meta = svc.verify_license_online(key, fingerprint)
        if is_valid:
            cache = svc.build_cache(key, fingerprint, meta)
            cache_activation_v2(cache)
        else:
            # Fall back to self-signed verification
            from scribe_dictation.licensing import verify_license_key, cache_activation

            if verify_license_key(key):
                is_valid = True
                msg = "Self-signed license activated."
                cache_activation(key)
        QTimer.singleShot(0, lambda: self._on_verification_complete(is_valid, msg, key))

    def _on_verification_complete(self, is_valid: bool, msg: str, key: str):
        self.activate_btn.setEnabled(True)
        self.key_input.setEnabled(True)
        if is_valid:
            self._set_status(msg, is_error=False, is_ok=True)
            short = get_machine_fingerprint()[:12]
            self.machine_label.setText(f"🔒 Bound to this machine ({short}…)")
            self.machine_label.setObjectName("machine_label")
            QTimer.singleShot(800, self.accept)
        else:
            self._set_status(
                "Invalid license key. Please check and try again.", is_error=True
            )

    def _set_status(self, text, is_error=False, is_ok=False, is_info=False):
        self.status_label.setText(text)
        if is_error:
            self.status_label.setObjectName("status_err")
        elif is_ok:
            self.status_label.setObjectName("status_ok")
        elif is_info:
            self.status_label.setObjectName("status_info")
        else:
            self.status_label.setObjectName("")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def _on_buy_clicked(self):
        QDesktopServices.openUrl(QUrl(BUY_URL))
