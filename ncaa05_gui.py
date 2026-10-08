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

from ncaa05_db import extract_team_names, extract_league_dat_from_iso

class TeamBrowser(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NCAA Football 2005 Team Browser v1.2.0")
        self.setGeometry(100, 100, 500, 600)
        
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        
        # Info label
        self.info_label = QLabel("Open a LEAGUE.DAT or full GameCube ISO\nISO support: LEAGUE.DAT is located automatically")
        self.info_label.setAlignment(Qt.AlignCenter)
        self.info_label.setStyleSheet("color: #888; padding: 10px;")
        layout.addWidget(self.info_label)
        
        # Open button
        self.open_btn = QPushButton("Open LEAGUE.DAT or ISO")
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
            self, "Open LEAGUE.DAT or ISO", "",
            "All supported (*.dat *.iso);;DAT files (*.dat);;ISO files (*.iso);;All files (*)"
        )
        if not path:
            return
        
        try:
            # If it's an ISO, extract LEAGUE.DAT via FST lookup first
            if path.lower().endswith('.iso'):
                self.status_label.setText("Locating LEAGUE.DAT in ISO...")
                QApplication.processEvents()
                data = extract_league_dat_from_iso(path)
                teams = extract_team_names(data)
                self.status_label.setText(f"Loaded {len(teams)} teams from ISO: {Path(path).name}")
            else:
                teams = extract_team_names(path)
                self.status_label.setText(f"Loaded {len(teams)} teams from {Path(path).name}")
            
            self.team_list.clear()
            for team in sorted(teams):
                self.team_list.addItem(team)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to parse file:\n{e}")

def main():
    app = QApplication(sys.argv)
    window = TeamBrowser()
    window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
