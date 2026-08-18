"""
Custom Vocabulary & Replacement Rules Dialog for Privacy Scribe Pro.
"""

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QListWidget,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QTabWidget,
    QWidget,
    QDialogButtonBox,
    QCheckBox,
)

from scribe_dictation.transcribe.vocabulary import (
    CustomVocabularyManager,
    ReplacementRule,
)


class VocabularyDialog(QDialog):
    """Manage custom vocabulary terms and word replacement rules for Pro users."""

    def __init__(self, manager: CustomVocabularyManager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle("Custom Vocabulary & Dictionary — Privacy Scribe Pro")
        self.setMinimumSize(560, 420)
        self.resize(600, 450)

        self._setup_ui()
        self._load_data()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header = QLabel(
            "<b>Supervocab & Dictionary Biasing</b><br>"
            "<span style='color: #718096; font-size: 11px;'>"
            "Add custom jargon, company names, acronyms, and automatic phonetic corrections."
            "</span>"
        )
        layout.addWidget(header)

        self.tabs = QTabWidget()

        # Tab 1: Vocabulary Glossary
        vocab_tab = QWidget()
        vocab_layout = QVBoxLayout(vocab_tab)
        vocab_layout.setContentsMargins(8, 8, 8, 8)
        vocab_layout.setSpacing(8)

        v_desc = QLabel("Words and phrases to bias Whisper recognition towards:")
        v_desc.setStyleSheet("color: #4a5568; font-size: 11px;")
        vocab_layout.addWidget(v_desc)

        add_layout = QHBoxLayout()
        self.word_input = QLineEdit()
        self.word_input.setPlaceholderText(
            "Enter custom term (e.g. Kubernetes, OmniTender, PySide6)..."
        )
        self.word_input.returnPressed.connect(self._add_word)
        add_btn = QPushButton("+ Add Term")
        add_btn.clicked.connect(self._add_word)
        add_layout.addWidget(self.word_input)
        add_layout.addWidget(add_btn)
        vocab_layout.addLayout(add_layout)

        self.word_list = QListWidget()
        vocab_layout.addWidget(self.word_list)

        remove_word_btn = QPushButton("Remove Selected Term")
        remove_word_btn.clicked.connect(self._remove_word)
        vocab_layout.addWidget(remove_word_btn)

        self.tabs.addTab(vocab_tab, "🔤 Custom Terms")

        # Tab 2: Replacement Rules
        rules_tab = QWidget()
        rules_layout = QVBoxLayout(rules_tab)
        rules_layout.setContentsMargins(8, 8, 8, 8)
        rules_layout.setSpacing(8)

        r_desc = QLabel("Automatic phonetic corrections and regex replacements:")
        r_desc.setStyleSheet("color: #4a5568; font-size: 11px;")
        rules_layout.addWidget(r_desc)

        rule_form = QHBoxLayout()
        self.find_input = QLineEdit()
        self.find_input.setPlaceholderText("Find (e.g. 'kube cuddle')...")
        self.replace_input = QLineEdit()
        self.replace_input.setPlaceholderText("Replace with (e.g. 'kubectl')...")
        self.regex_check = QCheckBox("Regex")
        self.case_check = QCheckBox("Match Case")

        add_rule_btn = QPushButton("+ Add Rule")
        add_rule_btn.clicked.connect(self._add_rule)

        rule_form.addWidget(self.find_input)
        rule_form.addWidget(self.replace_input)
        rule_form.addWidget(self.regex_check)
        rule_form.addWidget(self.case_check)
        rule_form.addWidget(add_rule_btn)
        rules_layout.addLayout(rule_form)

        self.rules_table = QTableWidget()
        self.rules_table.setColumnCount(4)
        self.rules_table.setHorizontalHeaderLabels(
            ["Pattern", "Replacement", "Regex", "Match Case"]
        )
        self.rules_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.rules_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.rules_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self.rules_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents
        )
        rules_layout.addWidget(self.rules_table)

        remove_rule_btn = QPushButton("Remove Selected Rule")
        remove_rule_btn.clicked.connect(self._remove_rule)
        rules_layout.addWidget(remove_rule_btn)

        self.tabs.addTab(rules_tab, "🔄 Auto-Corrections")

        layout.addWidget(self.tabs)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(self.accept)
        layout.addWidget(btn_box)

    def _load_data(self):
        self.word_list.clear()
        for word in self.manager.get_vocabulary():
            self.word_list.addItem(word)

        self.rules_table.setRowCount(0)
        for rule in self.manager.get_rules():
            row = self.rules_table.rowCount()
            self.rules_table.insertRow(row)
            self.rules_table.setItem(row, 0, QTableWidgetItem(rule.pattern))
            self.rules_table.setItem(row, 1, QTableWidgetItem(rule.replacement))
            self.rules_table.setItem(
                row, 2, QTableWidgetItem("✓" if rule.is_regex else "")
            )
            self.rules_table.setItem(
                row, 3, QTableWidgetItem("✓" if rule.case_sensitive else "")
            )

    def _add_word(self):
        word = self.word_input.text().strip()
        if not word:
            return
        self.manager.add_word(word)
        self.word_input.clear()
        self._load_data()

    def _remove_word(self):
        item = self.word_list.currentItem()
        if not item:
            return
        self.manager.remove_word(item.text())
        self._load_data()

    def _add_rule(self):
        pattern = self.find_input.text().strip()
        replacement = self.replace_input.text().strip()
        if not pattern:
            return
        rule = ReplacementRule(
            pattern=pattern,
            replacement=replacement,
            is_regex=self.regex_check.isChecked(),
            case_sensitive=self.case_check.isChecked(),
        )
        self.manager.add_rule(rule)
        self.find_input.clear()
        self.replace_input.clear()
        self.regex_check.setChecked(False)
        self.case_check.setChecked(False)
        self._load_data()

    def _remove_rule(self):
        row = self.rules_table.currentRow()
        if row < 0:
            return
        rules = self.manager.get_rules()
        if 0 <= row < len(rules):
            self.manager.remove_rule(rules[row].pattern)
            self._load_data()
