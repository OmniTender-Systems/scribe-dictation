"""
Voice Snippets & Macros Management Dialog for Privacy Scribe Pro.

Provides a rich visual management interface to configure spoken trigger phrases,
variable substitutions ({date}, {time}, {clipboard}, {cursor}, {uuid}), and dynamic
macro template expansions.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
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

from scribe_dictation.formatters.snippets import (
    VoiceSnippetManager,
    expand_variables,
)


class SnippetsDialog(QDialog):
    """Manage voice snippets, spoken macros, and variable expansions."""

    def __init__(self, manager: VoiceSnippetManager, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle("Voice Snippets & Macros — Privacy Scribe Pro")
        self.setMinimumSize(780, 620)
        self.resize(840, 660)

        self._setup_ui()
        self._load_data()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # Header banner
        header = QLabel(
            "<b>Voice Snippets & Macro Expander</b><br>"
            "<span style='color: #718096; font-size: 11px;'>"
            "Speak a trigger phrase (e.g., <i>'insert signature'</i>, <i>'meeting notes template'</i>, <i>'insert date'</i>) "
            "to instantly expand rich boilerplate text with live dynamic variables."
            "</span>"
        )
        main_layout.addWidget(header)

        # Top Control Bar: Master toggle & Reset
        top_bar = QHBoxLayout()
        self.enable_check = QCheckBox("Enable Voice Snippets & Macro Expansion")
        self.enable_check.setChecked(self.manager.enabled)
        self.enable_check.toggled.connect(self._toggle_enabled)
        top_bar.addWidget(self.enable_check)

        top_bar.addStretch()

        reset_defaults_btn = QPushButton("↺ Reset to Defaults...")
        reset_defaults_btn.clicked.connect(self._reset_defaults)
        top_bar.addWidget(reset_defaults_btn)

        main_layout.addLayout(top_bar)

        # Main horizontal splitter / layout: Table on Left, Editor & Live Preview on Right
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Left: Snippets Table & Management ────────────────────────
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        table_label = QLabel("<b>Configured Voice Snippets</b>")
        table_label.setStyleSheet("font-size: 11px;")
        left_layout.addWidget(table_label)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(
            ["Trigger Phrase", "Description", "Active"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.itemChanged.connect(self._on_table_item_changed)
        left_layout.addWidget(self.table)

        table_btn_layout = QHBoxLayout()
        self.remove_btn = QPushButton("🗑️ Remove Selected")
        self.remove_btn.clicked.connect(self._remove_selected)
        table_btn_layout.addWidget(self.remove_btn)

        table_btn_layout.addStretch()
        left_layout.addLayout(table_btn_layout)

        splitter.addWidget(left_widget)

        # ── Right: Add / Edit Form & Live Preview ────────────────────
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        form_group = QGroupBox("Snippet Editor")
        form_layout = QVBoxLayout(form_group)
        form_layout.setContentsMargins(10, 10, 10, 10)
        form_layout.setSpacing(8)

        # Trigger phrase input
        trigger_layout = QHBoxLayout()
        trigger_lbl = QLabel("Trigger Phrase:")
        trigger_lbl.setStyleSheet("font-weight: bold; font-size: 11px;")
        self.trigger_input = QLineEdit()
        self.trigger_input.setPlaceholderText("e.g. insert signature, bug report...")
        trigger_layout.addWidget(trigger_lbl)
        trigger_layout.addWidget(self.trigger_input)
        form_layout.addLayout(trigger_layout)

        # Description input
        desc_layout = QHBoxLayout()
        desc_lbl = QLabel("Description:")
        desc_lbl.setStyleSheet("font-size: 11px; color: #4a5568;")
        self.desc_input = QLineEdit()
        self.desc_input.setPlaceholderText("e.g. Sign-off with contact info")
        desc_layout.addWidget(desc_lbl)
        desc_layout.addWidget(self.desc_input)
        form_layout.addLayout(desc_layout)

        # Variable insertion pills
        var_box = QHBoxLayout()
        var_lbl = QLabel("Insert Variable:")
        var_lbl.setStyleSheet("font-size: 10px; color: #718096;")
        var_box.addWidget(var_lbl)

        for var_name in ["{date}", "{time}", "{clipboard}", "{cursor}", "{uuid}"]:
            btn = QPushButton(var_name)
            btn.setStyleSheet(
                "font-size: 10px; padding: 2px 6px; font-family: monospace;"
            )
            btn.clicked.connect(
                lambda checked=False, v=var_name: self._insert_variable(v)
            )
            var_box.addWidget(btn)
        var_box.addStretch()
        form_layout.addLayout(var_box)

        # Expansion template editor
        tmpl_lbl = QLabel("Expansion Template:")
        tmpl_lbl.setStyleSheet("font-weight: bold; font-size: 11px;")
        form_layout.addWidget(tmpl_lbl)

        self.template_edit = QPlainTextEdit()
        self.template_edit.setPlaceholderText(
            "Enter the expansion text or macro template here..."
        )
        self.template_edit.textChanged.connect(self._update_live_preview)
        form_layout.addWidget(self.template_edit, 2)

        # Live Preview section
        preview_lbl = QLabel("Live Expansion Preview:")
        preview_lbl.setStyleSheet("font-weight: bold; font-size: 11px; color: #2d3748;")
        form_layout.addWidget(preview_lbl)

        self.preview_box = QPlainTextEdit()
        self.preview_box.setReadOnly(True)
        self.preview_box.setPlaceholderText(
            "Live evaluated template output will appear here..."
        )
        self.preview_box.setStyleSheet(
            "background-color: #f7fafc; color: #1a202c; font-family: monospace; font-size: 11px;"
        )
        form_layout.addWidget(self.preview_box, 1)

        # Form action buttons
        btn_action_layout = QHBoxLayout()
        self.save_btn = QPushButton("💾 Save / Add Snippet")
        self.save_btn.setStyleSheet("font-weight: bold;")
        self.save_btn.clicked.connect(self._save_snippet)
        btn_action_layout.addWidget(self.save_btn)

        self.clear_form_btn = QPushButton("Clear Form")
        self.clear_form_btn.clicked.connect(self._clear_form)
        btn_action_layout.addWidget(self.clear_form_btn)
        form_layout.addLayout(btn_action_layout)

        right_layout.addWidget(form_group)
        splitter.addWidget(right_widget)

        splitter.setSizes([340, 460])
        main_layout.addWidget(splitter, 1)

        # Dialog bottom buttons
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(self.accept)
        main_layout.addWidget(btn_box)

    def _load_data(self):
        """Populate the snippets table with existing manager snippets."""
        self.table.blockSignals(True)
        self.table.setRowCount(0)

        for snippet in self.manager.get_snippets():
            row = self.table.rowCount()
            self.table.insertRow(row)

            # Trigger item
            trigger_item = QTableWidgetItem(snippet.trigger_phrase)
            trigger_item.setData(Qt.ItemDataRole.UserRole, snippet.trigger_phrase)
            self.table.setItem(row, 0, trigger_item)

            # Description item
            desc_item = QTableWidgetItem(snippet.description)
            self.table.setItem(row, 1, desc_item)

            # Checkbox item for enabled
            enabled_item = QTableWidgetItem()
            enabled_item.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
            )
            enabled_item.setCheckState(
                Qt.CheckState.Checked if snippet.enabled else Qt.CheckState.Unchecked
            )
            self.table.setItem(row, 2, enabled_item)

        self.table.blockSignals(False)
        self._update_live_preview()

    def _on_selection_changed(self):
        """When user clicks a row in the table, populate the editor form."""
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return

        row = selected_rows[0].row()
        trigger_item = self.table.item(row, 0)
        if not trigger_item:
            return

        trigger_phrase = (
            trigger_item.data(Qt.ItemDataRole.UserRole) or trigger_item.text()
        )
        snippet = self.manager.get_snippet(trigger_phrase)
        if snippet:
            self.trigger_input.setText(snippet.trigger_phrase)
            self.desc_input.setText(snippet.description)
            self.template_edit.setPlainText(snippet.expansion_template)
            self._update_live_preview()

    def _on_table_item_changed(self, item: QTableWidgetItem):
        """Handle toggling the active checkbox directly in the table."""
        if item.column() == 2:
            row = item.row()
            trigger_item = self.table.item(row, 0)
            if trigger_item:
                trigger = (
                    trigger_item.data(Qt.ItemDataRole.UserRole) or trigger_item.text()
                )
                is_checked = item.checkState() == Qt.CheckState.Checked
                self.manager.set_snippet_enabled(trigger, is_checked)

    def _insert_variable(self, var_name: str):
        """Insert variable tag into the template editor at current cursor."""
        self.template_edit.insertPlainText(var_name)
        self.template_edit.setFocus()

    def _update_live_preview(self):
        """Update live preview with variables expanded."""
        template_text = self.template_edit.toPlainText()
        if not template_text:
            self.preview_box.setPlainText("")
            return
        expanded = expand_variables(template_text)
        self.preview_box.setPlainText(expanded)

    def _save_snippet(self):
        """Add or update the snippet from form inputs."""
        trigger = self.trigger_input.text().strip()
        template = self.template_edit.toPlainText()
        description = self.desc_input.text().strip()

        if not trigger:
            QMessageBox.warning(
                self,
                "Missing Trigger Phrase",
                "Please enter a spoken trigger phrase (e.g. 'insert signature').",
            )
            self.trigger_input.setFocus()
            return

        if not template:
            QMessageBox.warning(
                self,
                "Missing Template",
                "Please enter the expansion template text.",
            )
            self.template_edit.setFocus()
            return

        self.manager.add_snippet(
            trigger_phrase=trigger,
            expansion_template=template,
            enabled=True,
            description=description,
        )

        self._load_data()

        # Reselect the newly added / edited item
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.text().lower() == trigger.lower():
                self.table.selectRow(row)
                break

    def _remove_selected(self):
        """Remove the selected snippet."""
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.information(
                self, "No Selection", "Please select a snippet to remove."
            )
            return

        row = selected_rows[0].row()
        trigger_item = self.table.item(row, 0)
        if not trigger_item:
            return

        trigger = trigger_item.data(Qt.ItemDataRole.UserRole) or trigger_item.text()
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete the snippet '{trigger}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.manager.remove_snippet(trigger)
            self._clear_form()
            self._load_data()

    def _clear_form(self):
        """Clear the input fields."""
        self.trigger_input.clear()
        self.desc_input.clear()
        self.template_edit.clear()
        self.preview_box.clear()
        self.table.clearSelection()

    def _reset_defaults(self):
        """Reset all snippets to default starter templates."""
        reply = QMessageBox.question(
            self,
            "Reset Snippets",
            "Reset all voice snippets to the default starter templates? "
            "Any custom snippets you created will be replaced.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.manager.reset_to_defaults()
            self._clear_form()
            self._load_data()

    def _toggle_enabled(self, enabled: bool):
        """Toggle global snippets expansion."""
        self.manager.enabled = enabled
        self.manager.save()
