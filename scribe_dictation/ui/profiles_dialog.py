"""
App Profiles & Smart Context Detection Dialog for Privacy Scribe Pro.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from scribe_dictation.formatters.app_profiler import (
    AppProfileManager,
    detect_active_window,
)
from scribe_dictation.formatters.modes import BUILTIN_MODES, RAW_MODE


class ProfilesDialog(QDialog):
    """Manage application-specific formatting profiles and smart context detection."""

    def __init__(self, manager: AppProfileManager, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle("App Profiles & Smart Detection — Privacy Scribe Pro")
        self.setMinimumSize(680, 520)
        self.resize(720, 560)

        self._setup_ui()
        self._load_data()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header
        header = QLabel(
            "<b>Automatic Foreground App Formatting Profiles</b><br>"
            "<span style='color: #718096; font-size: 11px;'>"
            "Automatically format dictation based on your active window "
            "(e.g. IDEs \u2192 Code Comments, Outlook \u2192 Email, Word/Notion \u2192 Meeting Notes/Bullets)."
            "</span>"
        )
        layout.addWidget(header)

        # Global Profiling Toggle & Fallback Mode
        controls_layout = QHBoxLayout()
        self.enable_check = QCheckBox("Enable Smart Context Detection")
        self.enable_check.setChecked(self.manager.enabled)
        self.enable_check.toggled.connect(self._toggle_enabled)
        controls_layout.addWidget(self.enable_check)

        controls_layout.addSpacing(20)

        fallback_label = QLabel("Fallback Mode:")
        fallback_label.setStyleSheet("color: #4a5568; font-size: 11px;")
        controls_layout.addWidget(fallback_label)

        self.fallback_combo = QComboBox()
        for mode_key, mode_obj in BUILTIN_MODES.items():
            self.fallback_combo.addItem(mode_obj.name, mode_key)
        idx = self.fallback_combo.findData(self.manager.fallback_mode)
        if idx >= 0:
            self.fallback_combo.setCurrentIndex(idx)
        self.fallback_combo.currentIndexChanged.connect(self._on_fallback_changed)
        controls_layout.addWidget(self.fallback_combo)
        controls_layout.addStretch()

        layout.addLayout(controls_layout)

        # Add Profile Form
        form_box = QVBoxLayout()
        form_title = QLabel("<b>Add or Customize App Profile</b>")
        form_title.setStyleSheet("font-size: 11px;")
        form_box.addWidget(form_title)

        inputs_layout = QHBoxLayout()
        self.app_input = QLineEdit()
        self.app_input.setPlaceholderText(
            "Process / Identifier (e.g. code.exe, outlook.exe)..."
        )

        self.desc_input = QLineEdit()
        self.desc_input.setPlaceholderText("Description (optional)...")

        self.mode_combo = QComboBox()
        for mode_key, mode_obj in BUILTIN_MODES.items():
            self.mode_combo.addItem(mode_obj.name, mode_key)
        self.mode_combo.setCurrentIndex(self.mode_combo.findData("code_comment") or 0)

        self.match_type_combo = QComboBox()
        self.match_type_combo.addItem("Process Name", "process")
        self.match_type_combo.addItem("Window Title", "title")
        self.match_type_combo.addItem("Regex", "regex")

        add_btn = QPushButton("+ Add Profile")
        add_btn.clicked.connect(self._add_profile)

        inputs_layout.addWidget(self.app_input, 2)
        inputs_layout.addWidget(self.desc_input, 2)
        inputs_layout.addWidget(self.mode_combo, 2)
        inputs_layout.addWidget(self.match_type_combo, 1)
        inputs_layout.addWidget(add_btn, 1)
        form_box.addLayout(inputs_layout)

        # Helper Button: Detect Active Window
        detect_layout = QHBoxLayout()
        detect_btn = QPushButton("🎯 Detect Current Active Window")
        detect_btn.setToolTip(
            "Capture process name from your current foreground window"
        )
        detect_btn.clicked.connect(self._detect_current_window)
        detect_layout.addWidget(detect_btn)
        detect_layout.addStretch()
        form_box.addLayout(detect_layout)

        layout.addLayout(form_box)

        # Profiles Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            [
                "Active",
                "App / Process Identifier",
                "Description",
                "Formatting Mode",
                "Match Type",
            ]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.ResizeToContents
        )
        layout.addWidget(self.table)

        # Action Buttons below table
        actions_layout = QHBoxLayout()
        remove_btn = QPushButton("Remove Selected Profile")
        remove_btn.clicked.connect(self._remove_selected)
        actions_layout.addWidget(remove_btn)

        reset_btn = QPushButton("Reset to Built-in Defaults")
        reset_btn.clicked.connect(self._reset_defaults)
        actions_layout.addWidget(reset_btn)

        actions_layout.addStretch()
        layout.addLayout(actions_layout)

        # Dialog Standard Button Box
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(self.accept)
        layout.addWidget(btn_box)

    def _load_data(self):
        """Populate the table with profiles from the manager."""
        self.table.blockSignals(True)
        self.table.setRowCount(0)

        for profile in self.manager.profiles:
            row = self.table.rowCount()
            self.table.insertRow(row)

            # Column 0: Enabled checkbox item
            check_item = QTableWidgetItem()
            check_item.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
            )
            check_item.setCheckState(
                Qt.CheckState.Checked if profile.enabled else Qt.CheckState.Unchecked
            )
            self.table.setItem(row, 0, check_item)

            # Column 1: App Identifier
            ident_item = QTableWidgetItem(profile.app_identifier)
            self.table.setItem(row, 1, ident_item)

            # Column 2: Description
            desc_item = QTableWidgetItem(profile.description)
            self.table.setItem(row, 2, desc_item)

            # Column 3: Mode Combo
            mode_combo = QComboBox()
            for mode_key, mode_obj in BUILTIN_MODES.items():
                mode_combo.addItem(mode_obj.name, mode_key)
            m_idx = mode_combo.findData(profile.mode_id)
            if m_idx >= 0:
                mode_combo.setCurrentIndex(m_idx)
            mode_combo.currentIndexChanged.connect(
                lambda idx,
                p=profile.app_identifier,
                cb=mode_combo: self._on_table_mode_changed(p, cb.currentData())
            )
            self.table.setCellWidget(row, 3, mode_combo)

            # Column 4: Match Type
            match_item = QTableWidgetItem(profile.match_type.capitalize())
            match_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            )
            self.table.setItem(row, 4, match_item)

        self.table.itemChanged.connect(self._on_item_changed)
        self.table.blockSignals(False)

    def _toggle_enabled(self, checked: bool):
        self.manager.enabled = checked
        if self.manager.settings is not None:
            self.manager.save_to_settings(self.manager.settings)

    def _on_fallback_changed(self, idx: int):
        mode_id = self.fallback_combo.currentData()
        if mode_id:
            self.manager.fallback_mode = mode_id
            if self.manager.settings is not None:
                self.manager.save_to_settings(self.manager.settings)

    def _on_table_mode_changed(self, app_identifier: str, mode_id: str):
        self.manager.set_profile_mode(app_identifier, mode_id)

    def _on_item_changed(self, item: QTableWidgetItem):
        row = item.row()
        col = item.column()
        ident_item = self.table.item(row, 1)
        if not ident_item:
            return

        ident = ident_item.text().strip()
        if col == 0:
            enabled = item.checkState() == Qt.CheckState.Checked
            self.manager.set_profile_enabled(ident, enabled)
        elif col == 2:
            prof = self.manager.get_profile(ident)
            if prof:
                prof.description = item.text().strip()
                if self.manager.settings is not None:
                    self.manager.save_to_settings(self.manager.settings)

    def _add_profile(self):
        ident = self.app_input.text().strip()
        if not ident:
            return

        mode_id = self.mode_combo.currentData() or RAW_MODE.id
        desc = self.desc_input.text().strip()
        match_type = self.match_type_combo.currentData() or "process"

        self.manager.add_profile(
            app_identifier=ident,
            mode_id=mode_id,
            enabled=True,
            description=desc,
            match_type=match_type,
        )

        self.app_input.clear()
        self.desc_input.clear()
        self._load_data()

    def _detect_current_window(self):
        """Detect current foreground window and prefill input."""
        proc, title = detect_active_window()
        if proc:
            self.app_input.setText(proc)
            if title and not self.desc_input.text():
                self.desc_input.setText(title[:40])
        elif title:
            self.app_input.setText(title)
            self.match_type_combo.setCurrentIndex(1)  # Window title
        else:
            QMessageBox.information(
                self,
                "Window Detection",
                "No active external window detected. Switch to another app and retry, or type process name manually.",
            )

    def _remove_selected(self):
        row = self.table.currentRow()
        if row < 0:
            return
        ident_item = self.table.item(row, 1)
        if ident_item:
            self.manager.remove_profile(ident_item.text().strip())
            self._load_data()

    def _reset_defaults(self):
        reply = QMessageBox.question(
            self,
            "Reset Profiles",
            "Reset all app profiles to default settings?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.manager.reset_to_defaults()
            if self.manager.settings is not None:
                self.manager.save_to_settings(self.manager.settings)
            self._load_data()
