"""
Desktop Companion Dashboard Window for Linux Continuity.
Supports Local Wi-Fi, Tailscale Mesh VPN, and Cloudflare Remote Tunnels.
Developed by killindodo
"""

import os
import subprocess
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QScrollArea, QMessageBox, QFileDialog,
    QApplication, QButtonGroup, QRadioButton
)
from PyQt6.QtCore import Qt, pyqtSlot, QUrl, QTimer
from PyQt6.QtGui import QIcon, QFont, QDesktopServices

from ui.qr_widget import QRWidget
from ui.tray import ContinuityTrayIcon
from core.tunnel import tunnel_mgr, get_tailscale_ip, get_ssh_info
from core.terminal_pty import launch_desktop_terminal
from server import auth_mgr


class ContinuityWindow(QMainWindow):
    def __init__(self, project_root: str, host_ip: str, port: int = 8080):
        super().__init__()
        self.project_root = project_root
        self.host_ip = host_ip
        self.port = port
        self.local_url = f"http://{host_ip}:{port}"
        self.current_url = self.local_url
        self.icon_path = os.path.join(project_root, "static", "icons", "icon.png")

        # Shared Tunnel manager
        self.tunnel = tunnel_mgr
        self.tunnel.local_port = port
        self.tunnel.add_url_listener(self._on_tunnel_ready)

        self._init_window()
        self._setup_ui()
        self._setup_tray()
        self._update_display_url()

    def _init_window(self):
        self.setWindowTitle("Linux Continuity • PC <-> Android Hub")
        self.resize(800, 580)
        self.setMinimumSize(720, 500)
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
            QFrame#HeaderCard, QFrame#Card {
                background-color: #151822;
                border-radius: 12px;
                border: 1px solid #252a3a;
            }
            QPushButton.primary-btn {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #007aff, stop:1 #0056b3);
                color: #ffffff;
                border: none;
                border-radius: 8px;
                padding: 8px 16px;
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
                padding: 8px 14px;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton.secondary-btn:hover {
                background-color: #2a3042;
                border-color: #00d2ff;
                color: #ffffff;
            }
            QPushButton.mode-tab {
                background-color: #1c202d;
                color: #9aa1b5;
                border: 1px solid #2d3345;
                border-radius: 8px;
                padding: 8px 14px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton.mode-tab:checked {
                background-color: #007aff;
                color: #ffffff;
                border: 1px solid #3395ff;
            }
        """)

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(12)

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

        # PIN Badge
        self.lbl_pin_badge = QLabel(f"🔒 PIN: <b>{auth_mgr.pin}</b>")
        self.lbl_pin_badge.setStyleSheet("""
            background-color: #242938; color: #00d2ff;
            padding: 6px 14px; border-radius: 12px; font-size: 12px;
            border: 1px solid #343d54;
        """)
        hdr_layout.addWidget(self.lbl_pin_badge)

        self.lbl_status = QLabel("● Active")
        self.lbl_status.setStyleSheet("""
            background-color: #172e21; color: #34c759;
            padding: 6px 14px; border-radius: 12px; font-size: 12px; font-weight: bold;
        """)
        hdr_layout.addWidget(self.lbl_status)
        main_layout.addWidget(header)

        # 2. Network Mode Bar (Local Wi-Fi vs Tailscale vs Cloudflare Tunnel)
        mode_card = QFrame()
        mode_card.setObjectName("Card")
        mode_box = QHBoxLayout(mode_card)
        mode_box.setContentsMargins(12, 8, 12, 8)
        mode_box.setSpacing(10)

        lbl_conn_type = QLabel("CONNECTION MODE:")
        lbl_conn_type.setStyleSheet("font-size: 11px; font-weight: bold; color: #8b92a5;")
        mode_box.addWidget(lbl_conn_type)

        self.btn_grp_conn = QButtonGroup(self)
        self.btn_local = QPushButton("🏠 Local Wi-Fi")
        self.btn_tailscale = QPushButton("🌐 Tailscale VPN")
        self.btn_tunnel = QPushButton("☁️ Public Remote Tunnel")

        for b in [self.btn_local, self.btn_tailscale, self.btn_tunnel]:
            b.setCheckable(True)
            b.setProperty("class", "mode-tab")
            self.btn_grp_conn.addButton(b)
            mode_box.addWidget(b)

        self.btn_local.setChecked(True)
        self.btn_local.clicked.connect(self._select_local_mode)
        self.btn_tailscale.clicked.connect(self._select_tailscale_mode)
        self.btn_tunnel.clicked.connect(self._select_tunnel_mode)

        mode_box.addStretch()
        main_layout.addWidget(mode_card)

        # 3. Main Content Body: QR Code (Left) + Link & Features (Right)
        body_layout = QHBoxLayout()
        body_layout.setSpacing(14)

        # QR Code Card
        qr_card = QFrame()
        qr_card.setObjectName("Card")
        qr_box = QVBoxLayout(qr_card)
        qr_box.setContentsMargins(18, 16, 18, 16)
        qr_box.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_qr_inst = QLabel("Scan with Android Camera")
        self.lbl_qr_inst.setStyleSheet("font-size: 13px; font-weight: bold; color: #d0d6e5; margin-bottom: 4px;")
        qr_box.addWidget(self.lbl_qr_inst, alignment=Qt.AlignmentFlag.AlignCenter)

        self.qr_widget = QRWidget(self.current_url)
        self.qr_widget.setFixedSize(200, 200)
        qr_box.addWidget(self.qr_widget, alignment=Qt.AlignmentFlag.AlignCenter)

        self.lbl_qr_sub = QLabel("Auto-authenticates with secure token")
        self.lbl_qr_sub.setStyleSheet("font-size: 11px; color: #7a8296; margin-top: 4px;")
        qr_box.addWidget(self.lbl_qr_sub, alignment=Qt.AlignmentFlag.AlignCenter)
        body_layout.addWidget(qr_card, stretch=1)

        # Right Card: Connection Link, Tunnel status, & Checklist
        right_card = QFrame()
        right_card.setObjectName("Card")
        r_box = QVBoxLayout(right_card)
        r_box.setContentsMargins(18, 16, 18, 16)
        r_box.setSpacing(10)

        lbl_url_title = QLabel("ACCESS URL")
        lbl_url_title.setStyleSheet("font-size: 11px; font-weight: bold; color: #8b92a5;")
        r_box.addWidget(lbl_url_title)

        # URL Box & Copy Button
        url_box = QHBoxLayout()
        self.lbl_url = QLabel(self.current_url)
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

        # Tunnel control banner (visible when tunnel tab is active)
        self.tunnel_frame = QFrame()
        self.tunnel_frame.setStyleSheet("""
            background-color: #1a1e2b; border-radius: 8px;
            padding: 8px 12px; border: 1px solid #2d354b;
        """)
        t_layout = QHBoxLayout(self.tunnel_frame)
        t_layout.setContentsMargins(8, 4, 8, 4)
        self.lbl_tunnel_status = QLabel("Remote Tunnel: Inactive")
        self.lbl_tunnel_status.setStyleSheet("color: #9aa1b5; font-size: 12px;")
        t_layout.addWidget(self.lbl_tunnel_status)
        t_layout.addStretch()

        self.btn_toggle_tunnel = QPushButton("⚡ Start Public Tunnel")
        self.btn_toggle_tunnel.setStyleSheet("""
            background-color: #007aff; color: #fff; font-weight: bold;
            border-radius: 6px; padding: 6px 12px; font-size: 11px;
        """)
        self.btn_toggle_tunnel.clicked.connect(self._toggle_tunnel)
        t_layout.addWidget(self.btn_toggle_tunnel)
        self.tunnel_frame.setVisible(False)
        r_box.addWidget(self.tunnel_frame)

        # Features list
        lbl_feat_title = QLabel("ENABLED CONTINUITY CAPABILITIES:")
        lbl_feat_title.setStyleSheet("font-size: 11px; font-weight: bold; color: #8b92a5; margin-top: 4px;")
        r_box.addWidget(lbl_feat_title)

        features = [
            ("📟 Shared Interactive Terminal", "Mirror & control PC terminals in real-time via tmux"),
            ("🖥️ Live Desktop Screen Mirror", "View any open window & tap to control PC desktop"),
            ("📋 Universal Shared Clipboard", "Bi-directional instant sync with X11 clipboard"),
            ("📁 AirDrop-Style File Transfers", "Send photos & docs straight to ~/Downloads"),
            ("🔒 Remote Security", f"Protected by 4-digit PIN ({auth_mgr.pin})")
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
        btn_shared_term = QPushButton("⚡ Launch Shared Terminal")
        btn_shared_term.setProperty("class", "primary-btn")
        btn_shared_term.clicked.connect(self._launch_shared_terminal)
        btn_row.addWidget(btn_shared_term)

        btn_downloads = QPushButton("📂 Downloads")
        btn_downloads.setProperty("class", "secondary-btn")
        btn_downloads.clicked.connect(self._open_downloads)
        btn_row.addWidget(btn_downloads)

        btn_browser = QPushButton("🌐 Web")
        btn_browser.setProperty("class", "secondary-btn")
        btn_browser.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self.current_url)))
        btn_row.addWidget(btn_browser)

        r_box.addLayout(btn_row)
        body_layout.addWidget(right_card, stretch=2)

        main_layout.addLayout(body_layout)

        # 4. Watermark Footer Card
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

        lbl_repo = QLabel("<a href='https://github.com/killindodo/linux-continuity' style='color: #007aff; text-decoration: none;'>🔗 github.com/killindodo/linux-continuity</a>")
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
        self.tray = ContinuityTrayIcon(self.icon_path, self.current_url, self)
        self.tray.toggle_window.connect(self.toggle_visibility)
        self.tray.open_downloads.connect(self._open_downloads)
        self.tray.quit_app.connect(self.close)
        self.tray.show()

    def _select_local_mode(self):
        self.tunnel_frame.setVisible(False)
        self.current_url = self.local_url
        self._update_display_url()

    def _select_tailscale_mode(self):
        self.tunnel_frame.setVisible(False)
        ts_ip = get_tailscale_ip()
        if ts_ip:
            self.current_url = f"http://{ts_ip}:{self.port}"
            self._update_display_url()
        else:
            QMessageBox.information(
                self,
                "Tailscale Not Active",
                "Tailscale is stopped on your PC.\n\n"
                "To use Tailscale remote mesh access from anywhere:\n"
                "1. Run in terminal: sudo tailscale up\n"
                "2. Connect your Android phone with the Tailscale app."
            )
            self.btn_local.setChecked(True)
            self._select_local_mode()

    def _select_tunnel_mode(self):
        self.tunnel_frame.setVisible(True)
        if self.tunnel.public_url:
            self.current_url = self.tunnel.public_url
            self._update_display_url()
        else:
            self.lbl_tunnel_status.setText("Remote Tunnel: Click 'Start' to generate public HTTPS link")

    def _toggle_tunnel(self):
        if not self.tunnel.public_url:
            self.btn_toggle_tunnel.setText("Starting...")
            self.lbl_tunnel_status.setText("Requesting secure tunnel from Cloudflare...")
            ok = self.tunnel.start()
            if not ok:
                QMessageBox.critical(self, "Tunnel Error", "Could not start cloudflared tunnel.")
                self.btn_toggle_tunnel.setText("⚡ Start Public Tunnel")
        else:
            self.tunnel.stop()
            self.btn_toggle_tunnel.setText("⚡ Start Public Tunnel")
            self.lbl_tunnel_status.setText("Remote Tunnel: Inactive")
            self.current_url = self.local_url
            self._update_display_url()

    def _on_tunnel_ready(self, url: str):
        # Called from background thread
        QTimer.singleShot(0, lambda: self._apply_tunnel_url(url))

    def _apply_tunnel_url(self, url: str):
        self.current_url = url
        self.lbl_tunnel_status.setText("● Public HTTPS Tunnel Active (Worldwide)")
        self.lbl_tunnel_status.setStyleSheet("color: #34c759; font-size: 12px; font-weight: bold;")
        self.btn_toggle_tunnel.setText("⏹ Stop Tunnel")
        self._update_display_url()

    def _update_display_url(self):
        self.lbl_url.setText(self.current_url)
        # Embed master token in QR code for seamless 1-tap phone pairing
        qr_target = f"{self.current_url}/?token={auth_mgr.master_token}"
        self.qr_widget.set_text(qr_target)
        if hasattr(self, "tray"):
            self.tray.url = self.current_url
            self.tray.setToolTip(f"Linux Continuity Hub\n{self.current_url}")

    def toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.showNormal()
            self.activateWindow()

    def _copy_url(self):
        QApplication.clipboard().setText(self.current_url)
        QMessageBox.information(self, "Copied", f"URL copied to clipboard:\n{self.current_url}")

    def _open_downloads(self):
        subprocess.Popen(["xdg-open", os.path.expanduser("~/Downloads")])

    def _launch_shared_terminal(self):
        ok = launch_desktop_terminal("main")
        if ok:
            QMessageBox.information(
                self,
                "Shared Terminal Active",
                "Launched a terminal window on your PC connected to tmux session 'main'.\n\n"
                "Anything you run in this terminal is mirrored live to your Android device!"
            )
        else:
            QMessageBox.warning(
                self,
                "Terminal Error",
                "Could not detect a desktop terminal emulator (e.g. konsole, xterm)."
            )

    def closeEvent(self, event):
        if self.tunnel:
            self.tunnel.stop()
        event.accept()
