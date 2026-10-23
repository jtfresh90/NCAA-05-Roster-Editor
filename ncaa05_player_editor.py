#!/usr/bin/env python3
"""
NCAA Football 2005 Player Editor (PyQt5 GUI)
v1.2.0 - Real parser integration

Features:
- Browse players from GCI, LEAGUE.DAT, or ISO
- View and edit player names, position, key ratings
- Save changes with automatic backup (GCI)

Status: PLAY table format reverse-engineered. Desktop editor now uses the
real gci_play_parser / iso_play_parser instead of placeholders.
This addresses the previous "placeholder only / only a few teams visible"
problem.
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

# Import parsers
sys.path.insert(0, str(Path(__file__).parent))
try:
    from gci_play_parser import GCIPlayTable
    GCI_AVAILABLE = True
except ImportError:
    GCI_AVAILABLE = False

try:
    from iso_play_parser import IsoPlayTable
    ISO_AVAILABLE = True
except ImportError:
    ISO_AVAILABLE = False

from ncaa05_db import extract_league_dat_from_iso

# Position names (from NCAA / EA DB)
POSITIONS = [
    "QB", "HB", "FB", "WR", "TE",
    "LT", "LG", "C", "RG", "RT",
    "LE", "RE", "DT",
    "LOLB", "MLB", "ROLB",
    "CB", "FS", "SS",
    "K", "P"
]

# Key rating fields to expose
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
    ('PKAC', 'Kick Accuracy'),
    ('PKPW', 'Kick Power'),
    ('PTAK', 'Tackle'),
]


class PlayerEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NCAA Football 2005 Player Editor v1.2.0")
        self.setGeometry(100, 100, 1100, 720)

        self.mode = None          # 'gci' or 'iso'
        self.table = None         # GCIPlayTable or IsoPlayTable
        self.source_path = None
        self.current_player_idx = -1
        self.modified = False

        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # Toolbar
        toolbar = QHBoxLayout()
        self.open_btn = QPushButton("Open GCI / LEAGUE.DAT / ISO")
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
        left_layout.addWidget(QLabel("Players (all loaded — scroll)"))
        self.player_list = QListWidget()
        self.player_list.itemClicked.connect(self.on_player_selected)
        left_layout.addWidget(self.player_list)
        splitter.addWidget(left_widget)

        # Right: Editor
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        info_group = QGroupBox("Player Info")
        info_layout = QFormLayout(info_group)

        self.pgid_label = QLabel("-")
        info_layout.addRow("Index:", self.pgid_label)

        self.first_name_edit = QLineEdit()
        info_layout.addRow("First Name:", self.first_name_edit)

        self.last_name_edit = QLineEdit()
        info_layout.addRow("Last Name:", self.last_name_edit)

        self.position_combo = QComboBox()
        self.position_combo.addItems(POSITIONS)
        info_layout.addRow("Position:", self.position_combo)

        right_layout.addWidget(info_group)

        # Ratings
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

        self.apply_btn = QPushButton("Apply Changes to Player")
        self.apply_btn.clicked.connect(self.apply_changes)
        self.apply_btn.setEnabled(False)
        right_layout.addWidget(self.apply_btn)

        format_label = QLabel(
            "Format: EA TDB / YALP (GameCube)\n"
            "PLAY table: ~85 fields, 52-byte records\n"
            "Names: 6-bit packed (PF01-PF10, PL01-PL13)\n"
            "v1.2.0 — real parsers, full player list (no 5-team / 100-player limit)"
        )
        format_label.setStyleSheet("color: #666; font-size: 10px; padding: 10px;")
        format_label.setAlignment(Qt.AlignCenter)
        right_layout.addWidget(format_label)

        splitter.addWidget(right_widget)
        splitter.setSizes([340, 760])
        main_layout.addWidget(splitter)

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open GCI, LEAGUE.DAT or ISO",
            "",
            "Supported (*.gci *.dat *.iso);;GCI (*.gci);;DAT (*.dat);;ISO (*.iso);;All (*)"
        )
        if not path:
            return

        path = Path(path)
        try:
            if path.suffix.lower() == '.gci':
                if not GCI_AVAILABLE:
                    raise RuntimeError("gci_play_parser.py not found")
                self.table = GCIPlayTable(str(path))
                self.mode = 'gci'
                self.source_path = path
                count = self.table.record_count
                self.status_label.setText(
                    f"GCI: {path.name} — {count} players, {len(self.table.fields)} fields"
                )
            elif path.suffix.lower() == '.iso':
                if not ISO_AVAILABLE:
                    raise RuntimeError("iso_play_parser.py not found")
                data = extract_league_dat_from_iso(str(path))
                tmp = path.with_suffix('.league.dat.tmp')
                tmp.write_bytes(data)
                try:
                    self.table = IsoPlayTable(str(tmp))
                finally:
                    if tmp.exists():
                        tmp.unlink()
                self.mode = 'iso'
                self.source_path = path
                count = len(self.table.index)
                self.status_label.setText(
                    f"ISO: {path.name} — {count} players across {len(self.table.sections)} sections"
                )
            else:
                # Assume LEAGUE.DAT
                if not ISO_AVAILABLE:
                    raise RuntimeError("iso_play_parser.py not found")
                self.table = IsoPlayTable(str(path))
                self.mode = 'iso'
                self.source_path = path
                count = len(self.table.index)
                self.status_label.setText(
                    f"LEAGUE.DAT: {path.name} — {count} players"
                )

            self._populate_player_list()
            self.save_btn.setEnabled(True)
            self.modified = False

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load:\n{e}")
            self.status_label.setText("Load failed")

    def _populate_player_list(self):
        self.player_list.clear()
        if self.table is None:
            return

        if self.mode == 'gci':
            count = self.table.record_count
        else:
            count = len(self.table.index)

        # Show all players (or a high practical limit). No more artificial 5-team / 100 limit.
        # Full list: Qt handles the whole roster fine. The old 8,000-row
        # cap left most ISO players (27,526 total) unselectable.
        display_limit = count

        for i in range(display_limit):
            try:
                if self.mode == 'gci':
                    first, last = self.table.get_player_name(i)
                    name = f"{first} {last}".strip() or f"Player {i}"
                    try:
                        pos = self.table.get_field(i, 'PPOS')
                        pos_name = POSITIONS[pos] if 0 <= pos < len(POSITIONS) else f"P{pos}"
                    except Exception:
                        pos_name = "?"
                    try:
                        ovr = self.table.get_field(i, 'POVR')
                    except Exception:
                        ovr = "?"
                else:
                    name = f"Player {i}"
                    try:
                        pos = self.table.get_field(i, 'PPOS')
                        pos_name = POSITIONS[pos] if 0 <= pos < len(POSITIONS) else f"P{pos}"
                    except Exception:
                        pos_name = "?"
                    try:
                        ovr = self.table.get_field(i, 'POVR')
                    except Exception:
                        ovr = "?"

                item_text = f"[{i:4d}] {name} ({pos_name}) OVR:{ovr}"
                self.player_list.addItem(item_text)
            except Exception:
                self.player_list.addItem(f"[{i:4d}] <error reading>")

        if count > display_limit:
            self.player_list.addItem(f"... and {count - display_limit} more (UI safety cap)")

        self.status_label.setText(
            self.status_label.text() + f"  |  Showing {min(count, display_limit)} players"
        )

    def on_player_selected(self, item):
        text = item.text()
        if text.startswith("..."):
            return
        try:
            idx = int(text.split("]")[0].strip("["))
        except ValueError:
            return

        self.current_player_idx = idx
        self.apply_btn.setEnabled(True)
        self.pgid_label.setText(str(idx))

        try:
            if self.mode == 'gci':
                first, last = self.table.get_player_name(idx)
                self.first_name_edit.setText(first)
                self.last_name_edit.setText(last)
                try:
                    pos = self.table.get_field(idx, 'PPOS')
                    if 0 <= pos < len(POSITIONS):
                        self.position_combo.setCurrentIndex(pos)
                except Exception:
                    pass
                for field, _ in RATINGS:
                    try:
                        val = self.table.get_field(idx, field)
                        self.rating_spins[field].setValue(int(val))
                    except Exception:
                        self.rating_spins[field].setValue(0)
            else:
                # ISO mode — full name decode still incomplete in IsoPlayTable
                self.first_name_edit.setText("")
                self.last_name_edit.setText("")
                try:
                    pos = self.table.get_field(idx, 'PPOS')
                    if 0 <= pos < len(POSITIONS):
                        self.position_combo.setCurrentIndex(pos)
                except Exception:
                    pass
                for field, _ in RATINGS:
                    try:
                        val = self.table.get_field(idx, field)
                        self.rating_spins[field].setValue(int(val))
                    except Exception:
                        self.rating_spins[field].setValue(0)
        except Exception as e:
            QMessageBox.warning(self, "Read error", str(e))

    def apply_changes(self):
        if self.current_player_idx < 0 or self.table is None:
            return

        idx = self.current_player_idx
        try:
            if self.mode == 'gci':
                first = self.first_name_edit.text().strip()
                last = self.last_name_edit.text().strip()
                self.table.set_player_name(idx, first, last)

            pos = self.position_combo.currentIndex()
            try:
                self.table.set_field(idx, 'PPOS', pos)
            except Exception:
                pass

            for field, _ in RATINGS:
                try:
                    val = self.rating_spins[field].value()
                    self.table.set_field(idx, field, val)
                except Exception:
                    pass

            self.modified = True
            # Refresh list item
            item = self.player_list.currentItem()
            if item:
                name = f"{self.first_name_edit.text()} {self.last_name_edit.text()}".strip() or f"Player {idx}"
                pos_name = POSITIONS[pos] if 0 <= pos < len(POSITIONS) else f"P{pos}"
                ovr = self.rating_spins['POVR'].value() if 'POVR' in self.rating_spins else "?"
                item.setText(f"[{idx:4d}] {name} ({pos_name}) OVR:{ovr}")

            self.status_label.setText(f"Player {idx} updated (in memory) — click Save to write file")
        except Exception as e:
            QMessageBox.warning(self, "Apply failed", str(e))

    def save_file(self):
        if self.table is None:
            return

        if self.mode == 'gci' and self.source_path:
            backup = self.source_path.with_suffix('.gci.bak')
            if not backup.exists():
                shutil.copy2(self.source_path, backup)
            out, _ = QFileDialog.getSaveFileName(
                self, "Save modified GCI", str(self.source_path),
                "GCI files (*.gci)"
            )
            if out:
                self.table.save_gci(out)
                QMessageBox.information(
                    self, "Saved",
                    f"Wrote {out}\nBackup of original: {backup.name}"
                )
                self.modified = False
        elif self.mode == 'iso':
            QMessageBox.information(
                self, "ISO Save",
                "For ISO mode the recommended path is still the mobile PWA\n"
                "(it rebuilds the ISO in the browser) or:\n\n"
                "  python iso_play_parser.py --patch-iso input.iso league.dat output.iso\n\n"
                "Desktop ISO write-back will be completed in a later revision."
            )
        else:
            QMessageBox.information(self, "Save", "Nothing to save or mode unsupported.")


def main():
    app = QApplication(sys.argv)
    window = PlayerEditor()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
