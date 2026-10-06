#!/usr/bin/env python3
"""
NCAA 2005 Team Browser (PyQt5 GUI)
v1.0.0 Research Preview - Team browsing only
"""

import sys
from pathlib import Path
from PyQt5.QtWidgets import (QApplication, QMainWindow, QListWidget, 
                             QVBoxLayout, QWidget, QPushButton, QFileDialog,
                             QLabel, QMessageBox)
from PyQt5.QtCore import Qt

from ncaa05_db import extract_team_names

class TeamBrowser(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NCAA Football 2005 Team Browser v1.0.0")
        self.setGeometry(100, 100, 500, 600)
        
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        
        # Info label
        self.info_label = QLabel("Research Preview - Team browsing only\nPlayer editor coming in future releases")
        self.info_label.setAlignment(Qt.AlignCenter)
        self.info_label.setStyleSheet("color: #888; padding: 10px;")
        layout.addWidget(self.info_label)
        
        # Open button
        self.open_btn = QPushButton("Open LEAGUE.DAT")
        self.open_btn.clicked.connect(self.open_file)
        layout.addWidget(self.open_btn)
        
        # Team list
        self.team_list = QListWidget()
        layout.addWidget(self.team_list)
        
        # Status
        self.status_label = QLabel("No file loaded")
        layout.addWidget(self.status_label)
    
    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open LEAGUE.DAT", "", "DAT files (*.dat);;All files (*)"
        )
        if not path:
            return
        
        try:
            teams = extract_team_names(path)
            self.team_list.clear()
            for team in sorted(teams):
                self.team_list.addItem(team)
            self.status_label.setText(f"Loaded {len(teams)} teams from {Path(path).name}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to parse file:\n{e}")

def main():
    app = QApplication(sys.argv)
    window = TeamBrowser()
    window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
