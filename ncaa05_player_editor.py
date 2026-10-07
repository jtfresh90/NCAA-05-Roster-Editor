#!/usr/bin/env python3
"""
NCAA Football 2005 Player Editor (PyQt5 GUI)
v1.1.0 - Player browsing and editing

Features:
- Browse teams
- View players per team
- Edit player names, position, ratings
- Save changes to LEAGUE.DAT (with backup)

Status: PLAY table format reverse-engineered, parser in development
"""

import sys
import shutil
from pathlib import Path
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QListWidget, QVBoxLayout, QHBoxLayout,
    QWidget, QPushButton, QFileDialog, QLabel, QMessageBox, QSplitter,
    QFormLayout, QLineEdit, QSpinBox, QComboBox, QGroupBox, QScrollArea
)
from PyQt5.QtCore import Qt

# Import our parser
sys.path.insert(0, str(Path(__file__).parent))
try:
    from play_parser import decode_player, PLAY_SCHEMA
    PARSER_AVAILABLE = True
except ImportError:
    PARSER_AVAILABLE = False
    # Fallback: try recon directory
    sys.path.insert(0, str(Path.home() / "workspace/recon/ncaa05"))
    try:
        from play_parser import decode_player, PLAY_SCHEMA
        PARSER_AVAILABLE = True
    except ImportError:
        PARSER_AVAILABLE = False

# Position names (from NCAA DB Editor)
POSITIONS = [
    "QB", "HB", "FB", "WR", "TE",
    "LT", "LG", "C", "RG", "RT",
    "LE", "RE", "DT",
    "LOLB", "MLB", "ROLB",
    "CB", "FS", "SS",
    "K", "P"
]

# Rating fields
RATINGS = [
    ('PTHA', 'Throw Accuracy'),
    ('PTHP', 'Throw Power'),
    ('PACC', 'Acceleration'),
    ('PAGI', 'Agility'),
    ('PAWR', 'Awareness'),
    ('PCTH', 'Catch'),
    ('PSPD', 'Speed'),
    ('PSTR', 'Strength'),
    ('POVR', 'Overall'),
]

class PlayerEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NCAA Football 2005 Player Editor v1.1.0")
        self.setGeometry(100, 100, 1000, 700)
        
        self.league_dat_path = None
        self.players = []  # list of dicts
        self.current_player_idx = -1
        
        self._build_ui()
    
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        
        # Toolbar
        toolbar = QHBoxLayout()
        self.open_btn = QPushButton("Open LEAGUE.DAT")
        self.open_btn.clicked.connect(self.open_file)
        toolbar.addWidget(self.open_btn)
        
        self.save_btn = QPushButton("Save Changes")
        self.save_btn.clicked.connect(self.save_file)
        self.save_btn.setEnabled(False)
        toolbar.addWidget(self.save_btn)
        
        toolbar.addStretch()
        
        self.status_label = QLabel("No file loaded")
        toolbar.addWidget(self.status_label)
        
        main_layout.addLayout(toolbar)
        
        # Main splitter: player list | editor
        splitter = QSplitter(Qt.Horizontal)
        
        # Left: Player list
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.addWidget(QLabel("Players"))
        self.player_list = QListWidget()
        self.player_list.itemClicked.connect(self.on_player_selected)
        left_layout.addWidget(self.player_list)
        splitter.addWidget(left_widget)
        
        # Right: Editor
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        
        # Player info group
        info_group = QGroupBox("Player Info")
        info_layout = QFormLayout(info_group)
        
        self.pgid_label = QLabel("-")
        info_layout.addRow("PGID:", self.pgid_label)
        
        self.first_name_edit = QLineEdit()
        info_layout.addRow("First Name:", self.first_name_edit)
        
        self.last_name_edit = QLineEdit()
        info_layout.addRow("Last Name:", self.last_name_edit)
        
        self.position_combo = QComboBox()
        self.position_combo.addItems(POSITIONS)
        info_layout.addRow("Position:", self.position_combo)
        
        right_layout.addWidget(info_group)
        
        # Ratings group (scrollable)
        ratings_group = QGroupBox("Ratings")
        ratings_layout = QFormLayout()
        
        self.rating_spins = {}
        for field, label in RATINGS:
            spin = QSpinBox()
            spin.setRange(0, 99)
            spin.setValue(50)
            self.rating_spins[field] = spin
            ratings_layout.addRow(label + ":", spin)
        
        ratings_group.setLayout(ratings_layout)
        
        scroll = QScrollArea()
        scroll.setWidget(ratings_group)
        scroll.setWidgetResizable(True)
        right_layout.addWidget(scroll)
        
        # Apply button
        self.apply_btn = QPushButton("Apply Changes to Player")
        self.apply_btn.clicked.connect(self.apply_changes)
        self.apply_btn.setEnabled(False)
        right_layout.addWidget(self.apply_btn)
        
        # Format info
        format_label = QLabel(
            "Format: EA TDB (GameCube)\n"
            "PLAY table: 85 fields, 52-byte records\n"
            "Names: 6-bit encoding (PF01-PF10, PL01-PL13)"
        )
        format_label.setStyleSheet("color: #666; font-size: 10px; padding: 10px;")
        format_label.setAlignment(Qt.AlignCenter)
        right_layout.addWidget(format_label)
        
        splitter.addWidget(right_widget)
        splitter.setSizes([300, 700])
        
        main_layout.addWidget(splitter)
    
    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open LEAGUE.DAT", "",
            "DAT files (*.dat);;All files (*)"
        )
        if not path:
            return
        
        self.league_dat_path = Path(path)
        self.status_label.setText(f"Loaded {self.league_dat_path.name}")
        self.save_btn.setEnabled(True)
        
        # TODO: Parse PLAY table and populate player list
        # For now, show placeholder
        self.player_list.clear()
        if PARSER_AVAILABLE:
            self.status_label.setText(
                f"Parser ready. PLAY table parsing in development. "
                f"Schema has {len(PLAY_SCHEMA)} fields."
            )
            # Placeholder players (until record alignment is fixed)
            for i in range(10):
                self.player_list.addItem(f"Player {i+1} (PGID: {1000+i})")
        else:
            QMessageBox.warning(
                self, "Parser Unavailable",
                "play_parser.py not found. Player data cannot be loaded."
            )
    
    def on_player_selected(self, item):
        idx = self.player_list.row(item)
        self.current_player_idx = idx
        self.apply_btn.setEnabled(True)
        
        # TODO: Load player data into editor fields
        self.pgid_label.setText(str(1000 + idx))
        self.first_name_edit.setText(f"First{idx+1}")
        self.last_name_edit.setText(f"Last{idx+1}")
    
    def apply_changes(self):
        if self.current_player_idx < 0:
            return
        
        # TODO: Write changes back to record data
        first = self.first_name_edit.text()
        last = self.last_name_edit.text()
        pos = self.position_combo.currentText()
        
        # Update list item
        item = self.player_list.item(self.current_player_idx)
        if item:
            item.setText(f"{first} {last} ({pos})")
        
        QMessageBox.information(
            self, "Applied",
            f"Changes applied to player (in-memory).\n"
            f"Click 'Save Changes' to write to file."
        )
    
    def save_file(self):
        if not self.league_dat_path:
            return
        
        # Backup original
        backup = self.league_dat_path.with_suffix('.dat.bak')
        if not backup.exists():
            shutil.copy2(self.league_dat_path, backup)
            QMessageBox.information(
                self, "Backup Created",
                f"Original backed up to:\n{backup.name}"
            )
        
        # TODO: Write modified records back to file
        QMessageBox.information(
            self, "Save",
            "Save functionality in development.\n"
            "Record serialization coming soon."
        )

def main():
    app = QApplication(sys.argv)
    window = PlayerEditor()
    window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
