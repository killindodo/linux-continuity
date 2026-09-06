"""
System Tray Icon for Linux Continuity Hub.
Developed by killindodo
"""

import os
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QApplication
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtCore import pyqtSignal


class ContinuityTrayIcon(QSystemTrayIcon):
    toggle_window = pyqtSignal()
    open_downloads = pyqtSignal()
    quit_app = pyqtSignal()

    def __init__(self, icon_path: str, url: str, parent=None):
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()
        super().__init__(icon, parent)
        self.url = url
        self.setToolTip(f"Linux Continuity Hub\n{url}")
        self._setup_menu()
        self.activated.connect(self._on_activated)

    def _setup_menu(self):
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background-color: #191c26;
                color: #e2e6f0;
                border: 1px solid #2d3345;
                padding: 6px;
                border-radius: 8px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #007aff;
                color: #ffffff;
            }
            QMenu::separator {
                height: 1px;
                background-color: #2d3345;
                margin: 4px 0px;
            }
        """)

        act_open = QAction("Open Continuity Dashboard", self)
        act_open.triggered.connect(self.toggle_window.emit)
        menu.addAction(act_open)

        act_copy = QAction("Copy Mobile URL", self)
        act_copy.triggered.connect(self._copy_url)
        menu.addAction(act_copy)

        act_dl = QAction("Open ~/Downloads", self)
        act_dl.triggered.connect(self.open_downloads.emit)
        menu.addAction(act_dl)

        menu.addSeparator()

        act_quit = QAction("Quit Continuity Hub", self)
        act_quit.triggered.connect(self.quit_app.emit)
        menu.addAction(act_quit)

        self.setContextMenu(menu)

    def _copy_url(self):
        QApplication.clipboard().setText(self.url)

    def _on_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.toggle_window.emit()
