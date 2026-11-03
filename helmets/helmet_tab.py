"""'Helmets' tab for the NCAA 05 editor: install the helmet pack into PLADATA.DAT and pick each helmet's finish."""
import os
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout, QComboBox, QPushButton,
                             QLabel, QFileDialog, QMessageBox, QPlainTextEdit)
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt

from . import helmet_pack as HP

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
