"""'Helmets' tab for the NCAA 05 editor: install the helmet pack into PLADATA.DAT and pick each helmet's finish."""
import os
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout, QComboBox, QPushButton,
                             QLabel, QFileDialog, QMessageBox, QPlainTextEdit, QTableWidget, QTableWidgetItem,
                             QHeaderView, QLineEdit)
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt

from . import helmet_pack as HP
from . import team_finish as TF

TEAM_ROWS = 256  # team ids shown in the per-team table (TOID 0-255)

PREVIEWS = {'revo': 'preview_revo_slot_speedflex.png', 'schutt': 'preview_schutt_slot_osha22.png',
            'adams': 'preview_adams_slot_zioncaesar.png'}
FINISH_LABELS = {'gloss': 'Glossy (game default)', 'matte': 'Matte', 'chrome': 'Chrome'}


class HelmetTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.src = None
        lay = QVBoxLayout(self)

        top = QHBoxLayout()
        self.open_btn = QPushButton('Open PLADATA.DAT')
        self.open_btn.clicked.connect(self.open_pladata)
        top.addWidget(self.open_btn)
        self.file_label = QLabel('No PLADATA.DAT loaded (extract it from the disc image first)')
        top.addWidget(self.file_label, 1)
        lay.addLayout(top)

        box = QGroupBox('Helmet finish (applies to every player wearing that helmet type)')
        form = QFormLayout(box)
        self.combos = {}
        for slot, (_, label) in HP.SLOTS.items():
            c = QComboBox()
            for f in HP.FINISHES:
                c.addItem(FINISH_LABELS[f], f)
            c.currentIndexChanged.connect(lambda _i, s=slot: self.show_preview(s))
            self.combos[slot] = c
            form.addRow(label + ':', c)
        lay.addWidget(box)

        note = QLabel('Logos, numbers and stickers are separate decal pieces and never get the helmet shine, so they '
                      'look the same on every finish. Chrome draws the shine twice; the farthest player model only '
                      'has room for one pass, so it stays glossy at a distance.')
        note.setWordWrap(True)
        lay.addWidget(note)

        mid = QHBoxLayout()
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(220)
        mid.addWidget(self.preview, 1)
        lay.addLayout(mid, 1)

        self.save_btn = QPushButton('Install helmet pack + finishes  ->  Save PLADATA.DAT as...')
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.save)
        lay.addWidget(self.save_btn)

        # ---- per-team finishes (main.dol) ----
        tbox = QGroupBox('Per-team helmet finish (main.dol) - overrides the helmet-type finish for that team')
        tl = QVBoxLayout(tbox)
        trow = QHBoxLayout()
        self.dol_btn = QPushButton('Open main.dol')
        self.dol_btn.clicked.connect(self.open_dol)
        trow.addWidget(self.dol_btn)
        self.names_btn = QPushButton('Team names from LEAGUE.DAT (optional)')
        self.names_btn.clicked.connect(self.load_names)
        trow.addWidget(self.names_btn)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText('filter teams...')
        self.filter.textChanged.connect(self.apply_filter)
        trow.addWidget(self.filter, 1)
        tl.addLayout(trow)
        self.dol_label = QLabel('No main.dol loaded')
        tl.addWidget(self.dol_label)
        self.team_table = QTableWidget(TEAM_ROWS, 3)
        self.team_table.setHorizontalHeaderLabels(['Team ID', 'Name (guess from LEAGUE.DAT order)', 'Finish'])
        self.team_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.team_combos = []
        for t in range(TEAM_ROWS):
            self.team_table.setItem(t, 0, QTableWidgetItem(str(t)))
            self.team_table.setItem(t, 1, QTableWidgetItem(''))
            c = QComboBox()
            for f in HP.FINISHES:
                c.addItem(FINISH_LABELS[f], f)
            self.team_table.setCellWidget(t, 2, c)
            self.team_combos.append(c)
        tl.addWidget(self.team_table, 1)
        self.dol_save_btn = QPushButton('Save main.dol as...')
        self.dol_save_btn.setEnabled(False)
        self.dol_save_btn.clicked.connect(self.save_dol)
        tl.addWidget(self.dol_save_btn)
        tnote = QLabel('Needs the helmet pack in PLADATA.DAT too (it carries the chrome shine options). Team IDs are the '
                       "game's TOID; the names column is only a guess until the ID order is confirmed in game.")
        tnote.setWordWrap(True)
        tl.addWidget(tnote)
        lay.addWidget(tbox, 2)
        self.dol_src = None

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(110)
        lay.addWidget(self.log)
        self.show_preview('revo')

    def say(self, msg):
        self.log.appendPlainText(msg)

    def show_preview(self, slot):
        p = os.path.join(HP.PACK, PREVIEWS.get(slot, ''))
        if slot in PREVIEWS and os.path.exists(p):
            pm = QPixmap(p)
            self.preview.setPixmap(pm.scaledToWidth(min(1000, max(400, self.width() - 40)), Qt.SmoothTransformation))
        else:
            self.preview.setText('Standard helmet stays stock')

    def open_pladata(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Open PLADATA.DAT', '', 'PLADATA (PLADATA.DAT *.DAT);;All files (*)')
        if not path:
            return
        try:
            state = HP.show(path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, 'Helmets', 'Could not read %s:\n%s' % (path, e))
            return
        self.src = path
        self.file_label.setText('%s  -  helmet pack %s' % (path, 'installed' if state['installed'] else 'not installed'))
        for slot, c in self.combos.items():
            f = state.get(slot) or 'gloss'
            c.setCurrentIndex(HP.FINISHES.index(f))
        self.save_btn.setEnabled(True)
        self.say('Loaded %s' % path)

    def save(self):
        if not self.src:
            return
        default = os.path.join(os.path.dirname(self.src), 'PLADATA_helmets.DAT')
        dst, _ = QFileDialog.getSaveFileName(self, 'Save patched PLADATA.DAT', default, 'DAT (*.DAT);;All files (*)')
        if not dst:
            return
        if os.path.abspath(dst) == os.path.abspath(self.src):
            bak = self.src + '.bak'
            if not os.path.exists(bak):
                import shutil
                shutil.copy2(self.src, bak)
                self.say('Backup written: %s' % bak)
        fin = {slot: c.currentData() for slot, c in self.combos.items()}
        try:
            HP.install(self.src, dst, fin, log=self.say)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, 'Helmets', 'Install failed:\n%s' % e)
            return
        QMessageBox.information(self, 'Helmets', 'Saved %s\n\nPut it back into the disc image as /PLADATA.DAT '
                                                 '(rebuild the image, the file is larger than the original).' % dst)

    # ---- per-team finish handlers ----
    def open_dol(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Open main.dol', '', 'DOL (*.dol);;All files (*)')
        if not path:
            return
        try:
            fin = TF.read_fin(open(path, 'rb').read())
            if fin is None:
                TF.apply(open(path, 'rb').read())  # validates that this is the USA main.dol
                fin = [0] * TF.NFIN
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, 'Helmets', 'Not a supported main.dol:\n%s' % e)
            return
        self.dol_src = path
        for t, c in enumerate(self.team_combos):
            c.setCurrentIndex(fin[t] if fin[t] < 3 else 0)
        self.dol_label.setText('%s  -  %s' % (path, 'team finishes patch present' if TF.read_fin(open(path, 'rb').read())
                                              else 'not patched yet (saving adds the patch)'))
        self.dol_save_btn.setEnabled(True)
        self.say('Loaded %s' % path)

    def load_names(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Open LEAGUE.DAT', '', 'LEAGUE.DAT (*.DAT);;All files (*)')
        if not path:
            return
        try:
            from ncaa05_db import extract_team_names
            names = extract_team_names(path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, 'Helmets', 'Could not read team names:\n%s' % e)
            return
        for t in range(TEAM_ROWS):
            self.team_table.item(t, 1).setText(names[t] if t < len(names) else '')
        self.say('Loaded %d team names (order assumed to match team IDs)' % len(names))

    def apply_filter(self, text):
        text = text.lower().strip()
        for t in range(TEAM_ROWS):
            name = self.team_table.item(t, 1).text().lower()
            self.team_table.setRowHidden(t, bool(text) and text not in name and text != str(t))

    def save_dol(self):
        if not self.dol_src:
            return
        default = os.path.join(os.path.dirname(self.dol_src), 'main_helmets.dol')
        dst, _ = QFileDialog.getSaveFileName(self, 'Save patched main.dol', default, 'DOL (*.dol);;All files (*)')
        if not dst:
            return
        if os.path.abspath(dst) == os.path.abspath(self.dol_src) and not os.path.exists(self.dol_src + '.bak'):
            import shutil
            shutil.copy2(self.dol_src, self.dol_src + '.bak')
            self.say('Backup written: %s.bak' % self.dol_src)
        fin = {t: c.currentData() for t, c in enumerate(self.team_combos)}
        try:
            TF.set_team_finishes(self.dol_src, dst, fin, log=self.say)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, 'Helmets', 'Saving main.dol failed:\n%s' % e)
            return
        QMessageBox.information(self, 'Helmets', 'Saved %s\n\nPut it back into the disc image as the boot DOL '
                                                 '(sys/main.dol) and rebuild the image.' % dst)
