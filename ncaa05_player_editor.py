#!/usr/bin/env python3
"""
NCAA Football 2005 Player Editor (PyQt5 GUI)
v1.4.0 - All PLAY fields + generic table editor (GCI)

Features:
- Browse players from GCI, LEAGUE.DAT, or ISO
- GCI mode: edit player names, position, and ALL 85 PLAY fields
  (friendly labels where known, raw field code always shown)
- GCI mode: "Tables" tab — generic editor for every table in the
  save's embedded DB directory (PLAY, DCHT, TDYN in the roster GCI;
  TEAM/COCH/etc. appear automatically if a save's DB contains them)
- Save changes with automatic backup (GCI)

Status: PLAY table format reverse-engineered. Desktop editor uses the
real gci_play_parser / iso_play_parser plus the generic gci_db_parser.
"""

import sys
import shutil
from pathlib import Path
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QListWidget, QVBoxLayout, QHBoxLayout,
    QWidget, QPushButton, QFileDialog, QLabel, QMessageBox, QSplitter,
    QFormLayout, QLineEdit, QSpinBox, QComboBox, QGroupBox, QScrollArea,
    QTabWidget
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
    from gci_db_parser import GCIDatabase
    GCIDB_AVAILABLE = True
except ImportError:
    GCIDB_AVAILABLE = False

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

# Key rating fields to expose (quick view; in GCI mode these are also
# part of the all-fields grid below)
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

# Friendly labels for PLAY fields (from the NCAA-DB-Editor field
# dictionary, ~/workspace/recon/ncaa05/PLAY_FIELDS.md).  Fields not
# listed here are shown with their raw code only.
FIELD_LABELS = {
    'PGID': 'Player ID',
    'PPOS': 'Position',
    'PJEN': 'Jersey Number',
    'PHGT': 'Height',
    'PWGT': 'Weight',
    'PTEN': 'Tendency',
    'POVR': 'Overall',
    'PTHA': 'Throw Accuracy',
    'PTHP': 'Throw Power',
    'PSPD': 'Speed',
    'PACC': 'Acceleration',
    'PAGI': 'Agility',
    'PAWR': 'Awareness',
    'PSTR': 'Strength',
    'PSTA': 'Stamina',
    'PCTH': 'Catching',
    'PCAR': 'Carrying',
    'PBTK': 'Break Tackle',
    'PTAK': 'Tackling',
    'PPBK': 'Pass Block',
    'PRBK': 'Run Block',
    'PKAC': 'Kick Accuracy',
    'PKPR': 'Kick Power',
    'PKPW': 'Kick Power',
    'PJMP': 'Jumping',
    'PINJ': 'Injury',
    'PHED': 'Head',
    'PHCL': 'Hair Color',
    'PEYE': 'Eye Paint',
    'PVIS': 'Visor',
    # TDYN (team ratings) fields
    'TRLB': 'Team Rating - Linebackers',
    'TRQB': 'Team Rating - Quarterbacks',
    'TRRB': 'Team Rating - Running Backs',
    'TRDE': 'Team Rating - Defense',
    'TROF': 'Team Rating - Offense',
    'TRDL': 'Team Rating - Defensive Line',
    'TROL': 'Team Rating - Offensive Line',
    'TRDB': 'Team Rating - Defensive Backs',
    'TOID': 'Team/Object ID',
}


def field_label(code):
    """Friendly label for a field code, or None if unknown."""
    if code in FIELD_LABELS:
        return FIELD_LABELS[code]
    if code.startswith('PF') and code[2:].isdigit():
        return f"First Name Letter {int(code[2:])}"
    if code.startswith('PL') and code[2:].isdigit():
        return f"Last Name Letter {int(code[2:])}"
    return None


class PlayerEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NCAA Football 2005 Player Editor v1.4.0")
        self.setGeometry(100, 100, 1100, 720)

        self.mode = None          # 'gci' or 'iso'
        self.table = None         # GCIPlayTable or IsoPlayTable
        self.db = None            # GCIDatabase (GCI mode only)
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

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_players_tab(), "Players")
        self.tabs.addTab(self._build_tables_tab(), "Tables (GCI)")
        main_layout.addWidget(self.tabs)

    # ------------------------------------------------------------------
    # Players tab (original editor, plus the all-fields grid)
    # ------------------------------------------------------------------
    def _build_players_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

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

        # Quick ratings (both modes; in GCI mode these mirror the
        # all-fields grid, which is authoritative on Apply)
        self.ratings_group = QGroupBox("Ratings (quick view)")
        ratings_layout = QFormLayout()
        self.rating_spins = {}
        for field, label in RATINGS:
            spin = QSpinBox()
            spin.setRange(0, 99)
            spin.setValue(50)
            self.rating_spins[field] = spin
            ratings_layout.addRow(label + ":", spin)
        self.ratings_group.setLayout(ratings_layout)
        right_layout.addWidget(self.ratings_group)

        # ALL PLAY fields (GCI mode only; built on file load)
        self.all_fields_group = QGroupBox("All PLAY Fields (GCI)")
        self.all_fields_layout = QFormLayout()
        self.all_fields_group.setLayout(self.all_fields_layout)
        self.field_spins = {}
        all_scroll = QScrollArea()
        all_scroll.setWidget(self.all_fields_group)
        all_scroll.setWidgetResizable(True)
        right_layout.addWidget(all_scroll)

        self.apply_btn = QPushButton("Apply Changes to Player")
        self.apply_btn.clicked.connect(self.apply_changes)
        self.apply_btn.setEnabled(False)
        right_layout.addWidget(self.apply_btn)

        format_label = QLabel(
            "Format: EA TDB / YALP (GameCube)\n"
            "PLAY table: 85 fields, 52-byte records\n"
            "Names: 6-bit packed (PF01-PF10, PL01-PL13)\n"
            "v1.4.0 — all PLAY fields editable (GCI); generic table editor on the Tables tab"
        )
        format_label.setStyleSheet("color: #666; font-size: 10px; padding: 10px;")
        format_label.setAlignment(Qt.AlignCenter)
        right_layout.addWidget(format_label)

        splitter.addWidget(right_widget)
        splitter.setSizes([340, 760])
        layout.addWidget(splitter)
        return tab

    # ------------------------------------------------------------------
    # Tables tab (generic DB table editor, GCI mode)
    # ------------------------------------------------------------------
    def _build_tables_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.tables_info_label = QLabel(
            "Open a GCI save to edit every table in its embedded database.\n"
            "The roster GCI's DB directory lists DCHT, PLAY and TDYN — it "
            "contains no TEAM or COCH table.\n"
            "If a save (e.g. a dynasty save) contains TEAM/COCH or any "
            "other table, it will appear here automatically."
        )
        self.tables_info_label.setWordWrap(True)
        layout.addWidget(self.tables_info_label)

        row = QHBoxLayout()
        row.addWidget(QLabel("Table:"))
        self.table_combo = QComboBox()
        self.table_combo.currentIndexChanged.connect(self._on_table_changed)
        row.addWidget(self.table_combo)
        row.addWidget(QLabel("Record:"))
        self.record_spin = QSpinBox()
        self.record_spin.setRange(0, 0)
        self.record_spin.valueChanged.connect(self._on_record_changed)
        row.addWidget(self.record_spin)
        self.record_summary_label = QLabel("")
        row.addWidget(self.record_summary_label)
        row.addStretch()
        layout.addLayout(row)

        self.table_fields_group = QGroupBox("Record Fields")
        self.table_fields_layout = QFormLayout()
        self.table_fields_group.setLayout(self.table_fields_layout)
        self.table_field_spins = {}
        scroll = QScrollArea()
        scroll.setWidget(self.table_fields_group)
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll)

        self.table_apply_btn = QPushButton("Apply Changes to Record")
        self.table_apply_btn.clicked.connect(self._apply_table_changes)
        self.table_apply_btn.setEnabled(False)
        layout.addWidget(self.table_apply_btn)
        return tab

    # ------------------------------------------------------------------
    # File loading
    # ------------------------------------------------------------------
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
            self.db = None
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
                if GCIDB_AVAILABLE:
                    self.db = GCIDatabase(str(path))
                    self._build_all_fields_grid()
                    self._populate_tables_tab()
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
                self._clear_gci_only_views()
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
                self._clear_gci_only_views()

            self._populate_player_list()
            self.save_btn.setEnabled(True)
            self.modified = False

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load:\n{e}")
            self.status_label.setText("Load failed")

    def _clear_gci_only_views(self):
        """ISO mode: no generic DB, so empty the GCI-only views."""
        self.field_spins = {}
        while self.all_fields_layout.count():
            self.all_fields_layout.takeAt(0)
        self.table_combo.clear()
        self.table_field_spins = {}
        while self.table_fields_layout.count():
            self.table_fields_layout.takeAt(0)
        self.table_apply_btn.setEnabled(False)

    def _build_all_fields_grid(self):
        """One spin box per PLAY schema field (GCI mode)."""
        self.field_spins = {}
        while self.all_fields_layout.count():
            self.all_fields_layout.takeAt(0)
        if self.db is None or 'PLAY' not in self.db.tables:
            return
        play = self.db.tables['PLAY']
        # Display in record (bit-offset) order
        ordered = sorted(play.fields.items(), key=lambda kv: kv[1][1])
        for code, (size, bit) in ordered:
            spin = QSpinBox()
            spin.setRange(0, (1 << size) - 1)
            label = field_label(code)
            text = f"{label} [{code}]" if label else code
            self.field_spins[code] = spin
            self.all_fields_layout.addRow(text + ":", spin)

    def _populate_player_list(self):
        self.player_list.clear()
        if self.table is None:
            return

        if self.mode == 'gci':
            count = self.table.record_count
        else:
            count = len(self.table.index)

        # Show all players. Full list: Qt handles the whole roster fine.
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

        self.status_label.setText(
            self.status_label.text() + f"  |  Showing {min(count, display_limit)} players"
        )

    # ------------------------------------------------------------------
    # Players tab behaviour
    # ------------------------------------------------------------------
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
                # All-fields grid
                for code, spin in self.field_spins.items():
                    try:
                        spin.setValue(int(self.table.get_field(idx, code)))
                    except Exception:
                        spin.setValue(0)
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

            if self.mode == 'gci' and self.field_spins:
                # All-fields grid is authoritative in GCI mode: it
                # covers every schema field, including the 12 ratings.
                for code, spin in self.field_spins.items():
                    if code == 'PPOS':
                        continue  # handled via the position combo
                    try:
                        self.table.set_field(idx, code, spin.value())
                    except Exception:
                        pass
                # Mirror the quick ratings view
                for field, _ in RATINGS:
                    if field in self.field_spins:
                        self.rating_spins[field].setValue(
                            self.field_spins[field].value())
            else:
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
                if self.mode == 'gci' and 'POVR' in self.field_spins:
                    ovr = self.field_spins['POVR'].value()
                item.setText(f"[{idx:4d}] {name} ({pos_name}) OVR:{ovr}")

            self.status_label.setText(f"Player {idx} updated (in memory) — click Save to write file")
        except Exception as e:
            QMessageBox.warning(self, "Apply failed", str(e))

    # ------------------------------------------------------------------
    # Tables tab behaviour
    # ------------------------------------------------------------------
    def _populate_tables_tab(self):
        self.table_combo.clear()
        if self.db is None:
            return
        found = []
        for name in self.db.table_order:
            t = self.db.tables[name]
            found.append(name)
            self.table_combo.addItem(
                f"{name} ({t.gc_name}) — {len(t.fields)} fields, "
                f"{t.record_count} records x {t.record_size} bytes",
                userData=name,
            )
        missing = [n for n in ('TEAM', 'COCH') if n not in self.db.tables]
        if missing:
            self.tables_info_label.setText(
                f"Tables in this save's DB directory: {', '.join(found)}. "
                f"No {' or '.join(missing)} table is present in this "
                "file, so there is nothing of it to edit here — if "
                "another save's DB directory lists it, it will appear "
                "in this editor automatically."
            )
        else:
            self.tables_info_label.setText(
                f"Tables in this save's DB directory: {', '.join(found)}."
            )
        self.table_apply_btn.setEnabled(True)
        if self.table_combo.count():
            self.table_combo.setCurrentIndex(0)
            self._on_table_changed(0)

    def _current_table(self):
        if self.db is None or self.table_combo.currentData() is None:
            return None
        return self.db.tables[self.table_combo.currentData()]

    def _on_table_changed(self, _index):
        t = self._current_table()
        self.table_field_spins = {}
        while self.table_fields_layout.count():
            self.table_fields_layout.takeAt(0)
        if t is None:
            return
        self.table_fields_group.setTitle(
            f"Record Fields — {t.name} ({t.gc_name}), "
            f"records at DB+0x{t.records_offset:X}")
        self.record_spin.setRange(0, max(0, t.record_count - 1))
        self.record_spin.setValue(0)
        ordered = sorted(t.fields.items(), key=lambda kv: kv[1][1])
        for code, (size, bit) in ordered:
            spin = QSpinBox()
            spin.setRange(0, (1 << size) - 1)
            label = field_label(code)
            text = f"{label} [{code}]" if label else code
            text += f" ({size} bits @ {bit})"
            self.table_field_spins[code] = spin
            self.table_fields_layout.addRow(text + ":", spin)
        self._on_record_changed(0)

    def _on_record_changed(self, _value):
        t = self._current_table()
        if t is None:
            return
        idx = self.record_spin.value()
        for code, spin in self.table_field_spins.items():
            try:
                spin.setValue(int(t.get_field(idx, code)))
            except Exception:
                spin.setValue(0)
        # Short summary: first few field values of this record
        parts = []
        for code in list(self.table_field_spins)[:5]:
            try:
                parts.append(f"{code}={t.get_field(idx, code)}")
            except Exception:
                pass
        self.record_summary_label.setText("  ".join(parts))

    def _apply_table_changes(self):
        t = self._current_table()
        if t is None:
            return
        idx = self.record_spin.value()
        try:
            for code, spin in self.table_field_spins.items():
                t.set_field(idx, code, spin.value())
                # Keep the Players tab's PLAY view in sync when the
                # generic editor edits the PLAY table.
                if t.name == 'PLAY' and self.mode == 'gci' \
                        and self.table is not None:
                    try:
                        self.table.set_field(idx, code, spin.value())
                    except Exception:
                        pass
            self.modified = True
            self.status_label.setText(
                f"{t.name} record {idx} updated (in memory) — click Save to write file")
            self._on_record_changed(idx)
        except Exception as e:
            QMessageBox.warning(self, "Apply failed", str(e))

    # ------------------------------------------------------------------
    # Saving
    # ------------------------------------------------------------------
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
                if self.db is not None:
                    self._save_gci_merged(out)
                else:
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

    def _save_gci_merged(self, out):
        """Write the GCI from the generic DB, with the PLAY record
        region taken from GCIPlayTable (the Players tab's store), so
        edits from both tabs are preserved."""
        from gci_play_parser import PLAY_RECORDS_OFFSET, PLAY_RECORD_SIZE
        merged_db = bytearray(self.db.db_data)
        start = PLAY_RECORDS_OFFSET
        end = start + self.table.record_count * PLAY_RECORD_SIZE
        merged_db[start:end] = self.table.db_data[start:end]
        gci = bytearray(self.db.gci_data)
        gci[self.db.db_offset:self.db.db_offset + len(merged_db)] = merged_db
        Path(out).write_bytes(bytes(gci))
        print(f"Saved modified GCI to {out}")


def main():
    app = QApplication(sys.argv)
    window = PlayerEditor()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
