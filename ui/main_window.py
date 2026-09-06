"""
Desktop Companion Dashboard Window for Linux Continuity.
Developed by killindodo
"""

import os
import subprocess
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QScrollArea, QMessageBox, QFileDialog, QApplication
)
from PyQt6.QtCore import Qt, pyqtSlot, QUrl
from PyQt6.QtGui import QIcon, QFont, QDesktopServices

from ui.qr_widget import QRWidget
from ui.tray import ContinuityTrayIcon


class ContinuityWindow(QMainWindow):
    def __init__(self, project_root: str, host_ip: str, port: int = 8080):
        super().__init__()
        self.project_root = project_root
        self.host_ip = host_ip
        self.port = port
        self.url = f"http://{host_ip}:{port}"
        self.icon_path = os.path.join(project_root, "static", "icons", "icon.png")

        self._init_window()
        self._setup_ui()
        self._setup_tray()

    def _init_window(self):
        self.setWindowTitle("Linux Continuity • PC <-> Android Hub")
        self.resize(760, 520)
        self.setMinimumSize(680, 460)
        if os.path.exists(self.icon_path):
            self.setWindowIcon(QIcon(self.icon_path))

        self.setStyleSheet("""
            QMainWindow {
                background-color: #0d0f15;
            }
            QWidget {
                color: #e4e7ee;
                font-family: 'Segoe UI', 'Ubuntu', sans-serif;
            }
            QFrame#HeaderCard {
                background-color: #151822;
                border-radius: 12px;
                border: 1px solid #252a3a;
            }
            QFrame#Card {
                background-color: #151822;
                border-radius: 12px;
                border: 1px solid #252a3a;
            }
            QPushButton.primary-btn {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #007aff, stop:1 #0056b3);
                color: #ffffff;
                border: none;
                border-radius: 8px;
                padding: 9px 18px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton.primary-btn:hover {
                background: #0088ff;
            }
            QPushButton.secondary-btn {
                background-color: #202432;
                color: #c0c6d6;
                border: 1px solid #33394c;
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton.secondary-btn:hover {
                background-color: #2a3042;
                border-color: #00d2ff;
                color: #ffffff;
            }
        """)

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(14)

        # 1. Header Card
        header = QFrame()
        header.setObjectName("HeaderCard")
        hdr_layout = QHBoxLayout(header)
        hdr_layout.setContentsMargins(18, 12, 18, 12)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        lbl_title = QLabel("LINUX CONTINUITY")
        lbl_title.setStyleSheet("color: #00d2ff; font-size: 18px; font-weight: 900; letter-spacing: 1px;")

        lbl_sub = QLabel("Seamless PC <-> Android Bridge • Developed by killindodo")
        lbl_sub.setStyleSheet("color: #8b92a5; font-size: 12px;")
        title_box.addWidget(lbl_title)
        title_box.addWidget(lbl_sub)
        hdr_layout.addLayout(title_box)

        hdr_layout.addStretch()

        lbl_status = QLabel("● Active on Wi-Fi")
        lbl_status.setStyleSheet("""
            background-color: #172e21; color: #34c759;
            padding: 6px 14px; border-radius: 12px; font-size: 12px; font-weight: bold;
        """)
        hdr_layout.addWidget(lbl_status)
        main_layout.addWidget(header)

        # 2. Main Content Body: QR Code (Left) + Link & Features (Right)
        body_layout = QHBoxLayout()
        body_layout.setSpacing(14)

        # QR Code Card
        qr_card = QFrame()
        qr_card.setObjectName("Card")
        qr_box = QVBoxLayout(qr_card)
        qr_box.setContentsMargins(18, 16, 18, 16)
        qr_box.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lbl_qr_inst = QLabel("Scan with Android Camera")
        lbl_qr_inst.setStyleSheet("font-size: 13px; font-weight: bold; color: #d0d6e5; margin-bottom: 6px;")
        qr_box.addWidget(lbl_qr_inst, alignment=Qt.AlignmentFlag.AlignCenter)

        self.qr_widget = QRWidget(self.url)
        self.qr_widget.setFixedSize(200, 200)
        qr_box.addWidget(self.qr_widget, alignment=Qt.AlignmentFlag.AlignCenter)

        lbl_qr_sub = QLabel("Opens instant web hub on mobile")
        lbl_qr_sub.setStyleSheet("font-size: 11px; color: #7a8296; margin-top: 6px;")
        qr_box.addWidget(lbl_qr_sub, alignment=Qt.AlignmentFlag.AlignCenter)
        body_layout.addWidget(qr_card, stretch=1)

        # Right Card: Connection Link & Feature Checklist
        right_card = QFrame()
        right_card.setObjectName("Card")
        r_box = QVBoxLayout(right_card)
        r_box.setContentsMargins(18, 16, 18, 16)
        r_box.setSpacing(12)

        lbl_url_title = QLabel("MOBILE WEB ACCESS URL")
        lbl_url_title.setStyleSheet("font-size: 11px; font-weight: bold; color: #8b92a5;")
        r_box.addWidget(lbl_url_title)

        # URL Box & Copy Button
        url_box = QHBoxLayout()
        self.lbl_url = QLabel(self.url)
        self.lbl_url.setStyleSheet("""
            background-color: #0c0e14; color: #00d2ff;
            padding: 8px 12px; border-radius: 6px; font-family: monospace;
            font-size: 13px; font-weight: bold; border: 1px solid #232734;
        """)
        url_box.addWidget(self.lbl_url, stretch=1)

        btn_copy = QPushButton("Copy URL")
        btn_copy.setProperty("class", "primary-btn")
        btn_copy.clicked.connect(self._copy_url)
        url_box.addWidget(btn_copy)
        r_box.addLayout(url_box)

        # Features list
        lbl_feat_title = QLabel("ENABLED CONTINUITY CAPABILITIES:")
        lbl_feat_title.setStyleSheet("font-size: 11px; font-weight: bold; color: #8b92a5; margin-top: 6px;")
        r_box.addWidget(lbl_feat_title)

        features = [
            ("📟 Live Terminal Stream", "Watch & control bash/zsh with mobile touch keyboard"),
            ("📋 Universal Clipboard", "Real-time sync between Linux X11 and Android"),
            ("📁 Instant File Drop", "AirDrop-style file uploads directly to ~/Downloads"),
            ("⚡ Quick System Actions", "Lock screen, desktop pings, and downloads shortcut")
        ]

        for title, desc in features:
            f_row = QVBoxLayout()
            f_row.setSpacing(1)
            f_lbl = QLabel(title)
            f_lbl.setStyleSheet("color: #e0e4ee; font-weight: bold; font-size: 12px;")
            f_desc = QLabel(desc)
            f_desc.setStyleSheet("color: #7a8296; font-size: 11px;")
            f_row.addWidget(f_lbl)
            f_row.addWidget(f_desc)
            r_box.addLayout(f_row)

        r_box.addStretch()

        # Action Buttons
        btn_row = QHBoxLayout()
        btn_downloads = QPushButton("📂 Open ~/Downloads")
        btn_downloads.setProperty("class", "secondary-btn")
        btn_downloads.clicked.connect(self._open_downloads)
        btn_row.addWidget(btn_downloads)

        btn_browser = QPushButton("🌐 Open in Browser")
        btn_browser.setProperty("class", "secondary-btn")
        btn_browser.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self.url)))
        btn_row.addWidget(btn_browser)

        r_box.addLayout(btn_row)
        body_layout.addWidget(right_card, stretch=2)

        main_layout.addLayout(body_layout)

        # 3. Watermark Footer Card
        footer = QFrame()
        footer.setStyleSheet("""
            background-color: #141620;
            border-radius: 8px;
            border: 1px solid #232734;
            padding: 4px 10px;
        """)
        ftr_layout = QHBoxLayout(footer)
        ftr_layout.setContentsMargins(14, 6, 14, 6)

        lbl_author = QLabel("⚡ Developed by <b style='color: #00d2ff;'>killindodo</b>")
        lbl_author.setStyleSheet("color: #9aa1b5; font-size: 11px;")

        lbl_repo = QLabel("<a href='https://github.com/killindodo' style='color: #007aff; text-decoration: none;'>🔗 github.com/killindodo</a>")
        lbl_repo.setOpenExternalLinks(True)
        lbl_repo.setStyleSheet("font-size: 11px;")

        lbl_ver = QLabel("Linux Continuity Hub v1.0.0")
        lbl_ver.setStyleSheet("color: #63697a; font-size: 11px;")

        ftr_layout.addWidget(lbl_author)
        ftr_layout.addSpacing(16)
        ftr_layout.addWidget(lbl_repo)
        ftr_layout.addStretch()
        ftr_layout.addWidget(lbl_ver)
        main_layout.addWidget(footer)

    def _setup_tray(self):
        self.tray = ContinuityTrayIcon(self.icon_path, self.url, self)
        self.tray.toggle_window.connect(self.toggle_visibility)
        self.tray.open_downloads.connect(self._open_downloads)
        self.tray.quit_app.connect(self.close)
        self.tray.show()

    def toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.showNormal()
            self.activateWindow()

    def _copy_url(self):
        QApplication.clipboard().setText(self.url)
        QMessageBox.information(self, "Copied", f"URL copied to clipboard:\n{self.url}")

    def _open_downloads(self):
        subprocess.Popen(["xdg-open", os.path.expanduser("~/Downloads")])
