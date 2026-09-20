"""
Desktop Companion Dashboard Window for Linux Continuity.
Supports Local Wi-Fi, Tailscale Mesh VPN, Zero-Trust Device Pairing,
Live Connected Devices Management, Clipboard Sync, Camera & Mic Hub,
File Transfers, and Security Activity Logs.
Developed by killindodo
"""

import os
import sys
import json
import time
import subprocess
import urllib.request
import urllib.error

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QScrollArea, QMessageBox, QFileDialog,
    QApplication, QButtonGroup, QRadioButton, QTabWidget,
    QCheckBox, QInputDialog, QTextEdit, QLineEdit, QTableWidget,
    QTableWidgetItem, QHeaderView, QSplitter
)
from PyQt6.QtCore import Qt, pyqtSlot, pyqtSignal, QUrl, QTimer, QByteArray
from PyQt6.QtGui import QIcon, QFont, QDesktopServices, QPixmap, QImage, QColor

from ui.qr_widget import QRWidget
from ui.tray import ContinuityTrayIcon
from core.tunnel import get_tailscale_ip, get_ssh_info
from core.terminal_pty import launch_desktop_terminal
from core.av_capture import av_mgr
from core.clipboard_sync import ClipboardSync
from core.activity_logger import audit_logger
from server import auth_mgr, file_mgr


class ContinuityWindow(QMainWindow):
    security_event = pyqtSignal(str, dict)

    def __init__(self, project_root: str, host_ip: str, port: int = 8080):
        super().__init__()
        self.project_root = project_root
        self.host_ip = host_ip
        self.port = port
        self.local_url = f"http://{host_ip}:{port}"
        self.current_url = self.local_url
        self.icon_path = os.path.join(project_root, "static", "icons", "icon.png")

        # Local clipboard helper
        self.clip_helper = ClipboardSync()
        self.last_known_clip = ""
        self.clip_history = []
        self.cam_live_active = False

        # Wire security event listener
        self.security_event.connect(self._handle_security_event)
        auth_mgr.add_pairing_listener(lambda event_type, data: self.security_event.emit(event_type, data))

        self._init_window()
        self._setup_ui()
        self._setup_tray()
        self._update_display_url()

        # Timers
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._on_poll_tick)
        self.poll_timer.start(3000)

        self.cam_timer = QTimer(self)
        self.cam_timer.timeout.connect(self._refresh_cam_frame)

    def _init_window(self):
        self.setWindowTitle("Linux Continuity • PC <-> Android Bridge")
        self.resize(960, 680)
        self.setMinimumSize(820, 560)
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
            QTabWidget::pane {
                border: 1px solid #252a3a;
                background-color: #151822;
                border-radius: 10px;
                padding: 10px;
            }
            QTabBar::tab {
                background-color: #1c202d;
                color: #8b92a5;
                padding: 9px 18px;
                margin-right: 3px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                font-weight: bold;
                font-size: 12px;
                border: 1px solid #282f42;
                border-bottom: none;
            }
            QTabBar::tab:selected {
                background-color: #007aff;
                color: #ffffff;
                border-color: #007aff;
            }
            QTabBar::tab:hover:!selected {
                background-color: #262d3f;
                color: #e4e7ee;
            }
            QPushButton.primary-btn {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #007aff, stop:1 #0056b3);
                color: #ffffff;
                border: none;
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 12px;
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
            QPushButton.danger-btn {
                background-color: #3b171c;
                color: #ff5252;
                border: 1px solid #63232b;
                border-radius: 6px;
                padding: 6px 12px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton.danger-btn:hover {
                background-color: #521d24;
                border-color: #ff5252;
                color: #ffffff;
            }
            QPushButton.success-btn {
                background-color: #12301c;
                color: #34c759;
                border: 1px solid #1f5731;
                border-radius: 6px;
                padding: 6px 12px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton.success-btn:hover {
                background-color: #1a4427;
                border-color: #34c759;
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
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QTextEdit, QLineEdit {
                background-color: #0c0e14;
                color: #e4e7ee;
                border: 1px solid #252a3a;
                border-radius: 6px;
                padding: 6px 10px;
                font-family: monospace;
            }
        """)

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(14, 12, 14, 12)
        main_layout.setSpacing(10)

        # 1. Header Card
        header = QFrame()
        header.setObjectName("HeaderCard")
        hdr_layout = QHBoxLayout(header)
        hdr_layout.setContentsMargins(16, 10, 16, 10)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        lbl_title = QLabel("LINUX CONTINUITY")
        lbl_title.setStyleSheet("color: #00d2ff; font-size: 18px; font-weight: 900; letter-spacing: 1px;")

        lbl_sub = QLabel("PC <-> Android Bridge • Zero-Trust Security • Clipboard, Camera, Files & Logs")
        lbl_sub.setStyleSheet("color: #8b92a5; font-size: 12px;")
        title_box.addWidget(lbl_title)
        title_box.addWidget(lbl_sub)
        hdr_layout.addLayout(title_box)

        hdr_layout.addStretch()

        # Connected count badge
        self.lbl_dev_count = QLabel("📱 0 Devices")
        self.lbl_dev_count.setStyleSheet("""
            background-color: #1c2538; color: #00d2ff;
            padding: 6px 12px; border-radius: 12px; font-size: 12px; font-weight: bold;
            border: 1px solid #293854;
        """)
        hdr_layout.addWidget(self.lbl_dev_count)

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

        # 2. Main Tabs
        self.tabs = QTabWidget()
        self.tabs.addTab(self._create_connect_tab(), "📡 Connect Hub")
        self.tabs.addTab(self._create_phone_control_tab(), "📲 Android Remote Control")
        self.tabs.addTab(self._create_devices_tab(), "📱 Devices & Security")
        self.tabs.addTab(self._create_clipboard_tab(), "📋 Clipboard Sync")
        self.tabs.addTab(self._create_camera_mic_tab(), "📷 Camera & Mic")
        self.tabs.addTab(self._create_files_tab(), "📁 File Transfers")
        self.tabs.addTab(self._create_logs_tab(), "📜 Activity Logs")
        main_layout.addWidget(self.tabs, stretch=1)

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

        lbl_repo = QLabel("<a href='https://github.com/killindodo/linux-continuity' style='color: #007aff; text-decoration: none;'>🔗 github.com/killindodo/linux-continuity</a>")
        lbl_repo.setOpenExternalLinks(True)
        lbl_repo.setStyleSheet("font-size: 11px;")

        lbl_ver = QLabel("Linux Continuity Hub v1.2.0")
        lbl_ver.setStyleSheet("color: #63697a; font-size: 11px;")

        ftr_layout.addWidget(lbl_author)
        ftr_layout.addSpacing(16)
        ftr_layout.addWidget(lbl_repo)
        ftr_layout.addStretch()
        ftr_layout.addWidget(lbl_ver)
        main_layout.addWidget(footer)

    # -------------------------------------------------------------
    # TAB 1: CONNECT & DASHBOARD
    # -------------------------------------------------------------
    def _create_connect_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        mode_card = QFrame()
        mode_card.setObjectName("Card")
        mode_box = QHBoxLayout(mode_card)
        mode_box.setContentsMargins(12, 8, 12, 8)
        mode_box.setSpacing(10)

        lbl_conn_type = QLabel("NETWORK MODE:")
        lbl_conn_type.setStyleSheet("font-size: 11px; font-weight: bold; color: #8b92a5;")
        mode_box.addWidget(lbl_conn_type)

        self.btn_grp_conn = QButtonGroup(self)
        self.btn_local = QPushButton("🏠 Local Wi-Fi")
        self.btn_tailscale = QPushButton("🌐 Tailscale Mesh VPN")

        for b in [self.btn_local, self.btn_tailscale]:
            b.setCheckable(True)
            b.setProperty("class", "mode-tab")
            self.btn_grp_conn.addButton(b)
            mode_box.addWidget(b)

        self.btn_local.setChecked(True)
        self.btn_local.clicked.connect(self._select_local_mode)
        self.btn_tailscale.clicked.connect(self._select_tailscale_mode)

        mode_box.addStretch()

        btn_mirror_term = QPushButton("🖥️ Launch Mirrored Konsole")
        btn_mirror_term.setProperty("class", "secondary-btn")
        btn_mirror_term.setToolTip("Opens a desktop Konsole window mirrored with phone via tmux")
        btn_mirror_term.clicked.connect(self._launch_shared_terminal)
        mode_box.addWidget(btn_mirror_term)

        btn_apk = QPushButton("📱 Download Android App (.apk)")
        btn_apk.setProperty("class", "primary-btn")
        btn_apk.clicked.connect(self._download_or_open_apk)
        mode_box.addWidget(btn_apk)

        layout.addWidget(mode_card)

        # Body: QR Code + Quick Info
        body_layout = QHBoxLayout()
        body_layout.setSpacing(14)

        qr_card = QFrame()
        qr_card.setObjectName("Card")
        qr_box = QVBoxLayout(qr_card)
        qr_box.setContentsMargins(16, 14, 16, 14)
        qr_box.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_qr_inst = QLabel("Pairing QR Code")
        self.lbl_qr_inst.setStyleSheet("font-size: 13px; font-weight: bold; color: #d0d6e5; margin-bottom: 4px;")
        qr_box.addWidget(self.lbl_qr_inst, alignment=Qt.AlignmentFlag.AlignCenter)

        self.qr_widget = QRWidget(self.current_url)
        self.qr_widget.setFixedSize(185, 185)
        qr_box.addWidget(self.qr_widget, alignment=Qt.AlignmentFlag.AlignCenter)

        self.lbl_qr_sub = QLabel("Scan in Android App to pair instantly")
        self.lbl_qr_sub.setStyleSheet("font-size: 11px; color: #7a8296; margin-top: 4px;")
        qr_box.addWidget(self.lbl_qr_sub, alignment=Qt.AlignmentFlag.AlignCenter)
        body_layout.addWidget(qr_card, stretch=1)

        right_card = QFrame()
        right_card.setObjectName("Card")
        r_box = QVBoxLayout(right_card)
        r_box.setContentsMargins(16, 14, 16, 14)
        r_box.setSpacing(10)

        lbl_url_title = QLabel("CONNECT URL (Enter in Android App):")
        lbl_url_title.setStyleSheet("font-size: 11px; font-weight: bold; color: #8b92a5;")
        r_box.addWidget(lbl_url_title)

        url_box = QHBoxLayout()
        self.lbl_url = QLabel(self.current_url)
        self.lbl_url.setStyleSheet("""
            background-color: #0c0e14; color: #00d2ff;
            padding: 8px 12px; border-radius: 6px; font-family: monospace;
            font-size: 13px; font-weight: bold; border: 1px solid #232734;
        """)
        url_box.addWidget(self.lbl_url, stretch=1)

        btn_copy = QPushButton("Copy")
        btn_copy.setProperty("class", "primary-btn")
        btn_copy.clicked.connect(self._copy_url)
        url_box.addWidget(btn_copy)
        r_box.addLayout(url_box)

        # Capabilities checklist
        features = [
            ("📟 Shared Interactive Terminal", "Mirror & control PC terminals in real-time via tmux"),
            ("🛡️ Zero-Trust Device Gatekeeper", "Incoming connections must be approved on this PC"),
            ("📋 Universal Shared Clipboard", "Bi-directional instant sync with X11 clipboard"),
            ("📷 Camera & 🎙️ Mic Hub", "View PC webcam frames and monitor microphone audio"),
            ("📁 AirDrop-Style File Transfers", "Send photos & docs straight to ~/Downloads")
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

        btn_browser = QPushButton("🌐 Web View")
        btn_browser.setProperty("class", "secondary-btn")
        btn_browser.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self.current_url)))
        btn_row.addWidget(btn_browser)

        r_box.addLayout(btn_row)
        body_layout.addWidget(right_card, stretch=2)

        layout.addLayout(body_layout)
        return w

    # -------------------------------------------------------------
    # TAB: ANDROID REMOTE CONTROL DECK
    # -------------------------------------------------------------
    def _create_phone_control_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        # 1. Telemetry Bar
        tel_card = QFrame()
        tel_card.setObjectName("Card")
        tel_box = QHBoxLayout(tel_card)
        tel_box.setContentsMargins(14, 10, 14, 10)

        self.lbl_phone_tel = QLabel("📱 Target: <b>Scanning for connected phone...</b>")
        self.lbl_phone_tel.setStyleSheet("font-size: 13px; color: #e4e7ee;")
        tel_box.addWidget(self.lbl_phone_tel, stretch=1)

        self.lbl_phone_battery = QLabel("🔋 Battery: --")
        self.lbl_phone_battery.setStyleSheet("font-size: 12px; color: #34c759; font-weight: bold;")
        tel_box.addWidget(self.lbl_phone_battery)

        btn_refresh_tel = QPushButton("🔄 Refresh Status")
        btn_refresh_tel.setProperty("class", "secondary-btn")
        btn_refresh_tel.clicked.connect(self._refresh_phone_telemetry)
        tel_box.addWidget(btn_refresh_tel)
        layout.addWidget(tel_card)

        # Scroll area for control sections
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        c_layout = QVBoxLayout(content)
        c_layout.setContentsMargins(2, 2, 2, 2)
        c_layout.setSpacing(12)

        # 2. Alert & Find My Phone Card
        alert_card = QFrame()
        alert_card.setObjectName("Card")
        a_box = QVBoxLayout(alert_card)
        a_box.setContentsMargins(14, 12, 14, 12)
        a_box.setSpacing(10)

        lbl_a_title = QLabel("🚨 FIND MY PHONE & REMOTE ALERTS:")
        lbl_a_title.setStyleSheet("font-size: 11px; font-weight: bold; color: #ff9f0a;")
        a_box.addWidget(lbl_a_title)

        btn_row_a = QHBoxLayout()
        btn_ring = QPushButton("🚨 Ring Loud Alarm")
        btn_ring.setProperty("class", "danger-btn")
        btn_ring.clicked.connect(lambda: self._send_phone_command("ring"))
        btn_row_a.addWidget(btn_ring)

        btn_stop_ring = QPushButton("⏹️ Stop Alarm")
        btn_stop_ring.setProperty("class", "secondary-btn")
        btn_stop_ring.clicked.connect(lambda: self._send_phone_command("stop_ring"))
        btn_row_a.addWidget(btn_stop_ring)

        btn_vibrate = QPushButton("📳 Vibrate Phone")
        btn_vibrate.setProperty("class", "secondary-btn")
        btn_vibrate.clicked.connect(lambda: self._send_phone_command("vibrate"))
        btn_row_a.addWidget(btn_vibrate)
        a_box.addLayout(btn_row_a)

        # Toast input row
        toast_row = QHBoxLayout()
        self.txt_toast_msg = QLineEdit()
        self.txt_toast_msg.setPlaceholderText("Send popup notification message to phone screen...")
        toast_row.addWidget(self.txt_toast_msg, stretch=1)

        btn_toast = QPushButton("💬 Send Alert")
        btn_toast.setProperty("class", "primary-btn")
        btn_toast.clicked.connect(self._send_phone_toast)
        toast_row.addWidget(btn_toast)
        a_box.addLayout(toast_row)
        c_layout.addWidget(alert_card)

        # 3. Media & Volume Controls Card
        media_card = QFrame()
        media_card.setObjectName("Card")
        m_box = QVBoxLayout(media_card)
        m_box.setContentsMargins(14, 12, 14, 12)
        m_box.setSpacing(10)

        lbl_m_title = QLabel("🎵 REMOTE PHONE MEDIA & AUDIO CONTROLS:")
        lbl_m_title.setStyleSheet("font-size: 11px; font-weight: bold; color: #00d2ff;")
        m_box.addWidget(lbl_m_title)

        media_row = QHBoxLayout()
        btn_prev = QPushButton("⏮️ Prev Track")
        btn_prev.setProperty("class", "secondary-btn")
        btn_prev.clicked.connect(lambda: self._send_phone_command("media_prev"))
        media_row.addWidget(btn_prev)

        btn_pp = QPushButton("⏯️ Play / Pause")
        btn_pp.setProperty("class", "primary-btn")
        btn_pp.clicked.connect(lambda: self._send_phone_command("media_play_pause"))
        media_row.addWidget(btn_pp)

        btn_next = QPushButton("⏭️ Next Track")
        btn_next.setProperty("class", "secondary-btn")
        btn_next.clicked.connect(lambda: self._send_phone_command("media_next"))
        media_row.addWidget(btn_next)

        btn_v_dn = QPushButton("🔉 Volume -")
        btn_v_dn.setProperty("class", "secondary-btn")
        btn_v_dn.clicked.connect(lambda: self._send_phone_command("volume_down"))
        media_row.addWidget(btn_v_dn)

        btn_v_up = QPushButton("🔊 Volume +")
        btn_v_up.setProperty("class", "secondary-btn")
        btn_v_up.clicked.connect(lambda: self._send_phone_command("volume_up"))
        media_row.addWidget(btn_v_up)
        m_box.addLayout(media_row)
        c_layout.addWidget(media_card)

        # 4. Remote Navigation Card
        nav_card = QFrame()
        nav_card.setObjectName("Card")
        n_box = QVBoxLayout(nav_card)
        n_box.setContentsMargins(14, 12, 14, 12)
        n_box.setSpacing(10)

        lbl_n_title = QLabel("🌐 REMOTE NAVIGATION & BROWSER LAUNCH:")
        lbl_n_title.setStyleSheet("font-size: 11px; font-weight: bold; color: #8b92a5;")
        n_box.addWidget(lbl_n_title)

        url_row = QHBoxLayout()
        self.txt_phone_url = QLineEdit()
        self.txt_phone_url.setPlaceholderText("https://youtube.com or any URL to open on Android phone...")
        url_row.addWidget(self.txt_phone_url, stretch=1)

        btn_open_url = QPushButton("🚀 Open on Phone")
        btn_open_url.setProperty("class", "primary-btn")
        btn_open_url.clicked.connect(self._open_url_on_phone)
        url_row.addWidget(btn_open_url)
        n_box.addLayout(url_row)
        c_layout.addWidget(nav_card)

        # 5. Remote Phone Camera Viewfinder (Phone -> PC)
        cam_card = QFrame()
        cam_card.setObjectName("Card")
        cam_box = QVBoxLayout(cam_card)
        cam_box.setContentsMargins(14, 12, 14, 12)
        cam_box.setSpacing(10)

        lbl_c_title = QLabel("📷 PHONE CAMERA REMOTE STREAM (Phone -> PC Viewfinder):")
        lbl_c_title.setStyleSheet("font-size: 11px; font-weight: bold; color: #34c759;")
        cam_box.addWidget(lbl_c_title)

        self.lbl_phone_cam_view = QLabel("Phone camera stream inactive. Click 'Start Phone Feed' below.")
        self.lbl_phone_cam_view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_phone_cam_view.setStyleSheet("""
            background-color: #0c0e14; border: 1px solid #232734;
            border-radius: 8px; color: #63697a; font-size: 12px;
        """)
        self.lbl_phone_cam_view.setMinimumHeight(220)
        cam_box.addWidget(self.lbl_phone_cam_view)

        cam_btn_row = QHBoxLayout()
        self.btn_phone_cam_toggle = QPushButton("🔴 Start Phone Camera Feed")
        self.btn_phone_cam_toggle.setProperty("class", "primary-btn")
        self.btn_phone_cam_toggle.clicked.connect(self._toggle_phone_camera_feed)
        cam_btn_row.addWidget(self.btn_phone_cam_toggle)

        btn_cam_front = QPushButton("🤳 Front Camera")
        btn_cam_front.setProperty("class", "secondary-btn")
        btn_cam_front.clicked.connect(lambda: self._send_phone_command("camera_start", "front"))
        cam_btn_row.addWidget(btn_cam_front)

        btn_cam_back = QPushButton("📸 Back Camera")
        btn_cam_back.setProperty("class", "secondary-btn")
        btn_cam_back.clicked.connect(lambda: self._send_phone_command("camera_start", "back"))
        cam_btn_row.addWidget(btn_cam_back)
        cam_box.addLayout(cam_btn_row)
        c_layout.addWidget(cam_card)

        # 6. Wireless ADB & Remote Phone Shell Card
        adb_card = QFrame()
        adb_card.setObjectName("Card")
        adb_box = QVBoxLayout(adb_card)
        adb_box.setContentsMargins(14, 12, 14, 12)
        adb_box.setSpacing(10)

        lbl_adb_title = QLabel("⚡ WIRELESS ADB & ANDROID TERMINAL SHELL:")
        lbl_adb_title.setStyleSheet("font-size: 11px; font-weight: bold; color: #00d2ff;")
        adb_box.addWidget(lbl_adb_title)

        lbl_adb_desc = QLabel("Connect directly to your Android device via Wireless Debugging (port 5555) for full remote terminal shell, app management, and screen control.")
        lbl_adb_desc.setStyleSheet("color: #8b92a5; font-size: 11px;")
        adb_box.addWidget(lbl_adb_desc)

        adb_row = QHBoxLayout()
        self.txt_adb_addr = QLineEdit()
        self.txt_adb_addr.setPlaceholderText("Phone IP:Port (e.g. 192.168.1.50:5555)")
        adb_row.addWidget(self.txt_adb_addr, stretch=1)

        btn_adb_connect = QPushButton("⚡ Connect ADB")
        btn_adb_connect.setProperty("class", "primary-btn")
        btn_adb_connect.clicked.connect(self._connect_wireless_adb)
        adb_row.addWidget(btn_adb_connect)

        btn_adb_shell = QPushButton("📟 Open Phone Shell")
        btn_adb_shell.setProperty("class", "secondary-btn")
        btn_adb_shell.clicked.connect(self._open_phone_shell)
        adb_row.addWidget(btn_adb_shell)
        adb_box.addLayout(adb_row)
        c_layout.addWidget(adb_card)

        c_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, stretch=1)

        # Phone camera poll timer
        self.phone_cam_timer = QTimer(self)
        self.phone_cam_timer.timeout.connect(self._poll_phone_camera_frame)
        self.phone_cam_active = False

        self._refresh_phone_telemetry()
        return w

    # -------------------------------------------------------------
    # TAB 3: CONNECTED DEVICES & ACCESS CONTROL
    # -------------------------------------------------------------
    def _create_devices_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        # Policy & Config Card
        pol_card = QFrame()
        pol_card.setObjectName("Card")
        pol_layout = QHBoxLayout(pol_card)
        pol_layout.setContentsMargins(14, 10, 14, 10)

        self.chk_admin_approval = QCheckBox("🛡️ Require Host Approval for New Devices (Zero-Trust Gatekeeper)")
        self.chk_admin_approval.setChecked(auth_mgr.require_admin_approval)
        self.chk_admin_approval.setStyleSheet("font-weight: bold; font-size: 12px; color: #00d2ff;")
        self.chk_admin_approval.toggled.connect(self._on_toggle_admin_approval)
        pol_layout.addWidget(self.chk_admin_approval)

        pol_layout.addStretch()

        btn_change_pin = QPushButton("🔑 Change PIN")
        btn_change_pin.setProperty("class", "secondary-btn")
        btn_change_pin.clicked.connect(self._prompt_change_pin)
        pol_layout.addWidget(btn_change_pin)

        btn_refresh = QPushButton("🔄 Refresh Devices")
        btn_refresh.setProperty("class", "secondary-btn")
        btn_refresh.clicked.connect(self._refresh_device_lists)
        pol_layout.addWidget(btn_refresh)

        layout.addWidget(pol_card)

        # Scrollable device containers
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        self.devices_layout = QVBoxLayout(scroll_content)
        self.devices_layout.setContentsMargins(4, 4, 4, 4)
        self.devices_layout.setSpacing(12)

        self.box_active = QVBoxLayout()
        self.devices_layout.addLayout(self.box_active)

        self.box_pending = QVBoxLayout()
        self.devices_layout.addLayout(self.box_pending)

        self.box_blocked = QVBoxLayout()
        self.devices_layout.addLayout(self.box_blocked)

        self.devices_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, stretch=1)

        self._refresh_device_lists()
        return w

    # -------------------------------------------------------------
    # TAB 3: UNIVERSAL CLIPBOARD SYNC
    # -------------------------------------------------------------
    def _create_clipboard_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        # Top status card
        top_card = QFrame()
        top_card.setObjectName("Card")
        t_box = QHBoxLayout(top_card)
        t_box.setContentsMargins(14, 10, 14, 10)

        lbl_clip_status = QLabel("📋 Bi-Directional Clipboard Sync: <b style='color: #34c759;'>Active (X11 <-> Android)</b>")
        lbl_clip_status.setStyleSheet("font-size: 12px;")
        t_box.addWidget(lbl_clip_status)

        t_box.addStretch()

        btn_pull = QPushButton("🔄 Read PC Clipboard")
        btn_pull.setProperty("class", "secondary-btn")
        btn_pull.clicked.connect(self._manual_read_clipboard)
        t_box.addWidget(btn_pull)

        layout.addWidget(top_card)

        # Main Clipboard Editor & Push Area
        split = QHBoxLayout()
        split.setSpacing(12)

        # Current PC Clipboard card
        left_card = QFrame()
        left_card.setObjectName("Card")
        l_box = QVBoxLayout(left_card)
        l_box.setContentsMargins(14, 12, 14, 12)

        lbl_pc_clip = QLabel("CURRENT PC CLIPBOARD CONTENT:")
        lbl_pc_clip.setStyleSheet("font-size: 11px; font-weight: bold; color: #8b92a5;")
        l_box.addWidget(lbl_pc_clip)

        self.txt_pc_clipboard = QTextEdit()
        self.txt_pc_clipboard.setReadOnly(True)
        self.txt_pc_clipboard.setPlaceholderText("Current PC clipboard is empty...")
        l_box.addWidget(self.txt_pc_clipboard)

        btn_copy_pc = QPushButton("📋 Copy Current to Linux Clipboard")
        btn_copy_pc.setProperty("class", "secondary-btn")
        btn_copy_pc.clicked.connect(lambda: QApplication.clipboard().setText(self.txt_pc_clipboard.toPlainText()))
        l_box.addWidget(btn_copy_pc)
        split.addWidget(left_card, stretch=1)

        # Push to Phone card
        right_card = QFrame()
        right_card.setObjectName("Card")
        r_box = QVBoxLayout(right_card)
        r_box.setContentsMargins(14, 12, 14, 12)

        lbl_push = QLabel("PUSH TEXT / LINK TO CONNECTED PHONE:")
        lbl_push.setStyleSheet("font-size: 11px; font-weight: bold; color: #8b92a5;")
        r_box.addWidget(lbl_push)

        self.txt_push_input = QTextEdit()
        self.txt_push_input.setPlaceholderText("Type text, link, code snippet, or notes to send directly to your Android clipboard...")
        r_box.addWidget(self.txt_push_input)

        btn_push_phone = QPushButton("🚀 Send to Phone Clipboard")
        btn_push_phone.setProperty("class", "primary-btn")
        btn_push_phone.clicked.connect(self._push_to_phone_clipboard)
        r_box.addWidget(btn_push_phone)
        split.addWidget(right_card, stretch=1)

        layout.addLayout(split)
        return w

    # -------------------------------------------------------------
    # TAB 4: CAMERA & MIC HUB
    # -------------------------------------------------------------
    def _create_camera_mic_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        # Status Bar
        av_card = QFrame()
        av_card.setObjectName("Card")
        av_box = QHBoxLayout(av_card)
        av_box.setContentsMargins(14, 10, 14, 10)

        status = av_mgr.get_status()
        cam_str = "<b style='color: #34c759;'>Available (/dev/video0)</b>" if status.get("has_webcam") else "<b style='color: #ff5252;'>Not Detected</b>"
        mic_str = "<b style='color: #34c759;'>Available</b>" if status.get("has_mic") else "<b style='color: #ff5252;'>Not Detected</b>"

        lbl_av = QLabel(f"📷 Webcam: {cam_str} &nbsp;&nbsp;|&nbsp;&nbsp; 🎙️ Microphone: {mic_str}")
        lbl_av.setStyleSheet("font-size: 12px;")
        av_box.addWidget(lbl_av)

        av_box.addStretch()

        btn_open_cam_app = QPushButton("🖥️ Open Desktop Camera App")
        btn_open_cam_app.setProperty("class", "secondary-btn")
        btn_open_cam_app.clicked.connect(lambda: av_mgr.open_camera_on_desktop())
        av_box.addWidget(btn_open_cam_app)

        layout.addWidget(av_card)

        # Viewfinder Card
        body = QHBoxLayout()
        body.setSpacing(12)

        cam_card = QFrame()
        cam_card.setObjectName("Card")
        cam_box = QVBoxLayout(cam_card)
        cam_box.setContentsMargins(14, 12, 14, 12)

        lbl_cam_title = QLabel("WEBCAM VIEWFINDER / LIVE FRAME:")
        lbl_cam_title.setStyleSheet("font-size: 11px; font-weight: bold; color: #8b92a5;")
        cam_box.addWidget(lbl_cam_title)

        self.lbl_cam_frame = QLabel("Camera preview inactive. Click 'Capture Snapshot' below.")
        self.lbl_cam_frame.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_cam_frame.setStyleSheet("""
            background-color: #0c0e14; border: 1px solid #232734;
            border-radius: 8px; color: #63697a; font-size: 12px;
        """)
        self.lbl_cam_frame.setMinimumHeight(240)
        cam_box.addWidget(self.lbl_cam_frame, stretch=1)

        cam_btn_row = QHBoxLayout()
        btn_snap = QPushButton("📸 Capture Snapshot")
        btn_snap.setProperty("class", "primary-btn")
        btn_snap.clicked.connect(self._refresh_cam_frame)
        cam_btn_row.addWidget(btn_snap)

        self.btn_toggle_cam_live = QPushButton("🔴 Start Live Preview")
        self.btn_toggle_cam_live.setProperty("class", "secondary-btn")
        self.btn_toggle_cam_live.clicked.connect(self._toggle_cam_live)
        cam_btn_row.addWidget(self.btn_toggle_cam_live)

        cam_box.addLayout(cam_btn_row)
        body.addWidget(cam_card, stretch=2)

        # Mic & AV Controls Card
        mic_card = QFrame()
        mic_card.setObjectName("Card")
        mic_box = QVBoxLayout(mic_card)
        mic_box.setContentsMargins(14, 12, 14, 12)
        mic_box.setSpacing(10)

        lbl_mic_title = QLabel("AUDIO & STREAM CONTROLS:")
        lbl_mic_title.setStyleSheet("font-size: 11px; font-weight: bold; color: #8b92a5;")
        mic_box.addWidget(lbl_mic_title)

        lbl_mic_info = QLabel(
            "Your Android device can listen to your PC microphone in real-time or view your PC webcam from the mobile app."
        )
        lbl_mic_info.setWordWrap(True)
        lbl_mic_info.setStyleSheet("color: #9aa1b5; font-size: 12px;")
        mic_box.addWidget(lbl_mic_info)

        mic_url = f"{self.current_url}/api/mic/stream"
        btn_listen_mic = QPushButton("🎙️ Test PC Mic Stream")
        btn_listen_mic.setProperty("class", "secondary-btn")
        btn_listen_mic.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(mic_url)))
        mic_box.addWidget(btn_listen_mic)

        btn_cam_url = QPushButton("📷 Open Web Camera Stream")
        btn_cam_url.setProperty("class", "secondary-btn")
        btn_cam_url.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(f"{self.current_url}/api/camera/frame")))
        mic_box.addWidget(btn_cam_url)

        mic_box.addStretch()
        body.addWidget(mic_card, stretch=1)

        layout.addLayout(body)
        return w

    def _toggle_cam_live(self):
        if self.cam_live_active:
            self.cam_live_active = False
            self.cam_timer.stop()
            self.btn_toggle_cam_live.setText("🔴 Start Live Preview")
        else:
            self.cam_live_active = True
            self.cam_timer.start(1000)
            self.btn_toggle_cam_live.setText("⏹ Stop Live Preview")
            self._refresh_cam_frame()

    def _refresh_cam_frame(self):
        frame_bytes = av_mgr.capture_frame(640, 360, quality=3)
        if frame_bytes:
            pix = QPixmap()
            if pix.loadFromData(frame_bytes):
                scaled = pix.scaled(
                    self.lbl_cam_frame.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self.lbl_cam_frame.setPixmap(scaled)
                return
        self.lbl_cam_frame.setText("Webcam feed unavailable or device currently in use.")

    # -------------------------------------------------------------
    # TAB 5: FILE TRANSFERS & AIRDROP
    # -------------------------------------------------------------
    def _create_files_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        top_card = QFrame()
        top_card.setObjectName("Card")
        t_box = QHBoxLayout(top_card)
        t_box.setContentsMargins(14, 10, 14, 10)

        save_dir_display = file_mgr.get_default_save_dir().replace(os.path.expanduser("~"), "~")
        self.lbl_save_dir = QLabel(f"📁 Save Directory: <code style='color: #00d2ff;'>{save_dir_display}</code>")
        self.lbl_save_dir.setStyleSheet("font-size: 12px;")
        t_box.addWidget(self.lbl_save_dir)

        t_box.addStretch()

        btn_open = QPushButton("📂 Open Downloads")
        btn_open.setProperty("class", "primary-btn")
        btn_open.clicked.connect(self._open_downloads)
        t_box.addWidget(btn_open)

        btn_choose = QPushButton("Change Directory")
        btn_choose.setProperty("class", "secondary-btn")
        btn_choose.clicked.connect(self._choose_save_dir)
        t_box.addWidget(btn_choose)

        layout.addWidget(top_card)

        # Recent files list
        files_card = QFrame()
        files_card.setObjectName("Card")
        f_box = QVBoxLayout(files_card)
        f_box.setContentsMargins(14, 12, 14, 12)

        lbl_rec = QLabel("RECENTLY RECEIVED CONTINUITY FILES:")
        lbl_rec.setStyleSheet("font-size: 11px; font-weight: bold; color: #8b92a5;")
        f_box.addWidget(lbl_rec)

        self.txt_files_list = QTextEdit()
        self.txt_files_list.setReadOnly(True)
        f_box.addWidget(self.txt_files_list)

        btn_refresh_files = QPushButton("🔄 Refresh Files")
        btn_refresh_files.setProperty("class", "secondary-btn")
        btn_refresh_files.clicked.connect(self._refresh_files_list)
        f_box.addWidget(btn_refresh_files)

        layout.addWidget(files_card)
        self._refresh_files_list()
        return w

    def _choose_save_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Select Save Directory", file_mgr.get_default_save_dir())
        if d:
            file_mgr.set_default_save_dir(d)
            QMessageBox.information(self, "Directory Updated", f"Continuity files will now save to:\n{d}")

    def _refresh_files_list(self):
        try:
            files = file_mgr.list_files()
            if not files:
                self.txt_files_list.setPlainText("No files received yet. Use the Android app to upload files directly to your PC.")
            else:
                lines = []
                for f in files[:25]:
                    lines.append(f"• {f.get('name')}  ({f.get('size')} bytes)  -  Modified: {f.get('modified')}")
                self.txt_files_list.setPlainText("\n".join(lines))
        except Exception:
            pass

    # -------------------------------------------------------------
    # TAB 6: SECURITY & ACTIVITY LOGS
    # -------------------------------------------------------------
    def _create_logs_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        top_card = QFrame()
        top_card.setObjectName("Card")
        t_box = QHBoxLayout(top_card)
        t_box.setContentsMargins(14, 10, 14, 10)

        lbl_log_title = QLabel("📜 Real-Time Security & Device Activity Audit Log")
        lbl_log_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #00d2ff;")
        t_box.addWidget(lbl_log_title)

        t_box.addStretch()

        btn_clear_log = QPushButton("🗑️ Clear Logs")
        btn_clear_log.setProperty("class", "secondary-btn")
        btn_clear_log.clicked.connect(self._clear_logs)
        t_box.addWidget(btn_clear_log)

        btn_refresh_log = QPushButton("🔄 Refresh")
        btn_refresh_log.setProperty("class", "secondary-btn")
        btn_refresh_log.clicked.connect(self._refresh_logs)
        t_box.addWidget(btn_refresh_log)

        layout.addWidget(top_card)

        # Log Text Box
        self.txt_logs = QTextEdit()
        self.txt_logs.setReadOnly(True)
        self.txt_logs.setStyleSheet("""
            background-color: #0c0e14; color: #34c759;
            font-family: 'Consolas', 'Courier New', monospace;
            font-size: 12px; line-height: 1.4; border: 1px solid #232734;
        """)
        layout.addWidget(self.txt_logs, stretch=1)

        self._refresh_logs()
        return w

    def _refresh_logs(self):
        logs = None
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/admin/logs?limit=100")
            with urllib.request.urlopen(req, timeout=1) as resp:
                data = json.loads(resp.read().decode())
                if data.get("status") == "ok":
                    logs = data.get("logs")
        except Exception:
            pass

        if logs is None:
            logs = audit_logger.get_logs(limit=100)

        if not logs:
            self.txt_logs.setPlainText("[SYSTEM] No events recorded yet.")
            return

        lines = []
        for l in logs:
            cat = l.get("category", "INFO")
            t = l.get("time", "")
            msg = l.get("message", "")
            dev = l.get("device")
            ip = l.get("ip")
            meta = f" [{dev}]" if dev else ""
            if ip and not dev:
                meta = f" [{ip}]"
            lines.append(f"[{t}] [{cat:8s}]{meta} {msg}")

        self.txt_logs.setPlainText("\n".join(lines))
        # Scroll to bottom
        cursor = self.txt_logs.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.txt_logs.setTextCursor(cursor)

    def _clear_logs(self):
        audit_logger.clear()
        self._send_admin_action("clear_logs", "")
        self._refresh_logs()

    # -------------------------------------------------------------
    # TICK & SYNC HELPERS
    # -------------------------------------------------------------
    def _on_poll_tick(self):
        # 1. Update clipboard display
        try:
            cur = self.clip_helper.get_clipboard()
            if cur != self.last_known_clip:
                self.last_known_clip = cur
                if hasattr(self, "txt_pc_clipboard"):
                    self.txt_pc_clipboard.setPlainText(cur)
        except Exception:
            pass

        # 2. Update device lists & log counts
        self._refresh_device_lists()
        self._refresh_phone_telemetry()
        if hasattr(self, "txt_logs") and self.tabs.currentIndex() == 6:
            self._refresh_logs()

    def _manual_read_clipboard(self):
        cur = self.clip_helper.get_clipboard()
        self.last_known_clip = cur
        self.txt_pc_clipboard.setPlainText(cur)
        QMessageBox.information(self, "Clipboard Read", f"Read {len(cur)} characters from Linux clipboard.")

    def _push_to_phone_clipboard(self):
        text = self.txt_push_input.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Empty Content", "Please enter some text or link to send.")
            return

        self.clip_helper.set_clipboard(text)
        self.last_known_clip = text
        self.txt_pc_clipboard.setPlainText(text)
        audit_logger.log("CLIPBOARD", f"Manual push from PC Dashboard: '{text[:30]}...'")
        QMessageBox.information(
            self,
            "Pushed to Clipboard",
            "Copied to Linux PC clipboard and synced to connected mobile devices via WebSocket!"
        )
        self.txt_push_input.clear()

    def _send_admin_action(self, action: str, target: str):
        try:
            url = f"http://127.0.0.1:{self.port}/api/admin/device_action"
            payload = json.dumps({"action": action, "target": target}).encode("utf-8")
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=2)
        except Exception:
            pass

    def _refresh_device_lists(self):
        pending = None
        sessions = None
        blocked = None
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/admin/devices")
            with urllib.request.urlopen(req, timeout=1) as resp:
                data = json.loads(resp.read().decode())
                if data.get("status") == "ok":
                    pending = data.get("pending_requests")
                    sessions = data.get("active_devices")
                    blocked = data.get("blocked_devices")
        except Exception:
            pass

        if pending is None:
            pending = auth_mgr.get_pending_requests()
        if sessions is None:
            sessions = auth_mgr.get_active_devices()
        if blocked is None:
            blocked = auth_mgr.get_blocked_devices()

        remote_sessions = [s for s in sessions if not s.get("is_localhost") and s.get("ip") != "127.0.0.1"]
        count = len(remote_sessions)
        if count > 0:
            dev_text = f"📱 {count} Connected" if count == 1 else f"📱 {count} Devices"
            self.lbl_dev_count.setText(dev_text)
            self.lbl_dev_count.setStyleSheet("""
                background-color: #172e21; color: #34c759;
                padding: 6px 12px; border-radius: 12px; font-size: 12px; font-weight: bold;
                border: 1px solid #234832;
            """)
        else:
            self.lbl_dev_count.setText("📱 0 Devices")
            self.lbl_dev_count.setStyleSheet("""
                background-color: #1c2538; color: #8b92a5;
                padding: 6px 12px; border-radius: 12px; font-size: 12px; font-weight: bold;
                border: 1px solid #293854;
            """)

        if hasattr(self, "tray"):
            status_txt = f"{count} Device(s) Connected" if count > 0 else "Ready for Connection"
            self.tray.setToolTip(f"Linux Continuity Hub\n{status_txt}\n{self.current_url}")

        # 1. Active sessions
        self._clear_layout(self.box_active)
        lbl_a = QLabel("🟢 AUTHORIZED & CONNECTED DEVICES:")
        lbl_a.setStyleSheet("font-size: 12px; font-weight: bold; color: #34c759;")
        self.box_active.addWidget(lbl_a)

        if not remote_sessions:
            none_lbl = QLabel("  No active mobile connections. Waiting for Android phone to connect...")
            none_lbl.setStyleSheet("color: #63697a; font-style: italic; font-size: 11px;")
            self.box_active.addWidget(none_lbl)
        else:
            for s in remote_sessions:
                token = s.get("token")
                ip = s.get("ip")
                dev_name = s.get("device_name", "Android Device")
                conn_time = s.get("connected_time", "")
                idle_sec = s.get("idle_seconds", 0)
                status_color = "#34c759" if idle_sec < 60 else "#ff9f0a"
                status_txt = "Active Now" if idle_sec < 60 else f"Idle ({idle_sec}s ago)"

                card = QFrame()
                card.setStyleSheet("background-color: #17212b; border: 1px solid #233446; border-radius: 8px; padding: 6px;")
                row = QHBoxLayout(card)
                row.setContentsMargins(10, 8, 10, 8)

                info = QLabel(
                    f"📱 <b>{dev_name}</b> &nbsp;|&nbsp; IP: <code>{ip}</code> &nbsp;|&nbsp; "
                    f"<span style='color: {status_color};'>● {status_txt}</span> &nbsp;|&nbsp; "
                    f"<span style='color: #7a8296; font-size: 11px;'>Paired at {conn_time}</span>"
                )
                info.setStyleSheet("color: #e4e7ee; font-size: 12px;")
                row.addWidget(info, stretch=1)

                btn_push_c = QPushButton("📋 Push Clip")
                btn_push_c.setProperty("class", "secondary-btn")
                btn_push_c.clicked.connect(lambda checked, i=ip: self._push_to_phone_clipboard())
                row.addWidget(btn_push_c)

                btn_kick = QPushButton("⚠️ Kick")
                btn_kick.setProperty("class", "secondary-btn")
                btn_kick.clicked.connect(lambda checked, t=token: self._kick_token(t))
                row.addWidget(btn_kick)

                btn_ban = QPushButton("⛔ Block IP")
                btn_ban.setProperty("class", "danger-btn")
                btn_ban.clicked.connect(lambda checked, i=ip: self._block_ip(i))
                row.addWidget(btn_ban)

                self.box_active.addWidget(card)

        # 2. Pending requests
        self._clear_layout(self.box_pending)
        lbl_p = QLabel("⏳ PENDING CONNECTION REQUESTS (Zero-Trust Gatekeeper):")
        lbl_p.setStyleSheet("font-size: 12px; font-weight: bold; color: #ff9f0a; margin-top: 10px;")
        self.box_pending.addWidget(lbl_p)

        if not pending:
            none_lbl = QLabel("  No pending requests. Incoming devices will prompt here for authorization.")
            none_lbl.setStyleSheet("color: #63697a; font-style: italic; font-size: 11px;")
            self.box_pending.addWidget(none_lbl)
        else:
            for req in pending:
                req_id = req.get("req_id") or req.get("id")
                card = QFrame()
                card.setStyleSheet("background-color: #1e2433; border: 1px solid #36415d; border-radius: 8px; padding: 6px;")
                row = QHBoxLayout(card)
                row.setContentsMargins(10, 8, 10, 8)

                info = QLabel(f"📱 <b>{req.get('device_name', 'Android')}</b> &nbsp;|&nbsp; IP: <code>{req.get('ip', 'unknown')}</code>")
                info.setStyleSheet("color: #e4e7ee; font-size: 12px;")
                row.addWidget(info, stretch=1)

                btn_app = QPushButton("✅ Approve")
                btn_app.setProperty("class", "success-btn")
                btn_app.clicked.connect(lambda checked, rid=req_id: self._approve_req(rid))
                row.addWidget(btn_app)

                btn_rej = QPushButton("❌ Reject")
                btn_rej.setProperty("class", "secondary-btn")
                btn_rej.clicked.connect(lambda checked, rid=req_id: self._reject_req(rid, False))
                row.addWidget(btn_rej)

                btn_blk = QPushButton("⛔ Block IP")
                btn_blk.setProperty("class", "danger-btn")
                btn_blk.clicked.connect(lambda checked, rid=req_id: self._reject_req(rid, True))
                row.addWidget(btn_blk)

                self.box_pending.addWidget(card)

        # 3. Blocked IPs
        self._clear_layout(self.box_blocked)
        lbl_b = QLabel("⛔ BLOCKED IPS & BLACKLIST:")
        lbl_b.setStyleSheet("font-size: 12px; font-weight: bold; color: #ff5252; margin-top: 10px;")
        self.box_blocked.addWidget(lbl_b)

        if not blocked:
            none_lbl = QLabel("  No devices or IPs blocked.")
            none_lbl.setStyleSheet("color: #63697a; font-style: italic; font-size: 11px;")
            self.box_blocked.addWidget(none_lbl)
        else:
            for b_ip in blocked:
                card = QFrame()
                card.setStyleSheet("background-color: #26161b; border: 1px solid #442129; border-radius: 8px; padding: 6px;")
                row = QHBoxLayout(card)
                row.setContentsMargins(10, 8, 10, 8)

                info = QLabel(f"🚫 Blocked Address: <code>{b_ip}</code>")
                info.setStyleSheet("color: #ff8585; font-size: 12px;")
                row.addWidget(info, stretch=1)

                btn_unblock = QPushButton("🔓 Unblock")
                btn_unblock.setProperty("class", "secondary-btn")
                btn_unblock.clicked.connect(lambda checked, i=b_ip: self._unblock_ip(i))
                row.addWidget(btn_unblock)

                self.box_blocked.addWidget(card)

    def _approve_req(self, req_id: str):
        self._send_admin_action("approve", req_id)
        auth_mgr.approve_pairing(req_id)
        self._refresh_device_lists()

    def _reject_req(self, req_id: str, block_ip: bool):
        if block_ip:
            self._send_admin_action("block", req_id)
        else:
            self._send_admin_action("reject", req_id)
        auth_mgr.reject_pairing(req_id, block_ip=block_ip)
        self._refresh_device_lists()

    def _kick_token(self, token: str):
        self._send_admin_action("kick", token)
        auth_mgr.kick_session(token)
        self._refresh_device_lists()

    def _block_ip(self, ip: str):
        self._send_admin_action("block", ip)
        auth_mgr.block_ip(ip, "Blocked via Admin UI")
        self._refresh_device_lists()

    def _unblock_ip(self, ip: str):
        self._send_admin_action("unblock", ip)
        auth_mgr.unblock_ip(ip)
        self._refresh_device_lists()

    def _on_toggle_admin_approval(self, checked: bool):
        self._send_admin_action("set_policy", "true" if checked else "false")
        auth_mgr.set_require_admin_approval(checked)

    def _prompt_change_pin(self):
        new_pin, ok = QInputDialog.getText(
            self, "Change Security PIN", "Enter new 4-digit numeric PIN:", text=auth_mgr.pin
        )
        if ok and new_pin.strip():
            auth_mgr.set_pin(new_pin.strip())
            self.lbl_pin_badge.setText(f"🔒 PIN: <b>{auth_mgr.pin}</b>")
            QMessageBox.information(self, "PIN Updated", f"New PIN is now: {auth_mgr.pin}")

    def _download_or_open_apk(self):
        apk_path = os.path.join(self.project_root, "static", "apk", "LinuxContinuity.apk")
        download_url = f"{self.current_url}/download/app"
        msg = (
            f"<b>Linux Continuity Android App (.apk)</b> is ready!<br><br>"
            f"• <b>Download Directly on Phone:</b><br>"
            f"<a href='{download_url}'>{download_url}</a><br><br>"
            f"• <b>Local file location:</b><br><code>{apk_path}</code><br><br>"
            f"Would you like to open the folder containing the APK?"
        )
        reply = QMessageBox.question(
            self,
            "Android APK Companion",
            msg,
            QMessageBox.StandardButton.Open | QMessageBox.StandardButton.Close
        )
        if reply == QMessageBox.StandardButton.Open:
            folder = os.path.dirname(apk_path)
            subprocess.Popen(["xdg-open", folder])

    @pyqtSlot(str, dict)
    def _handle_security_event(self, event_type: str, data: dict):
        self._refresh_device_lists()
        if event_type == "pairing_requested":
            device_name = data.get("device_name", "Unknown Android Device")
            ip = data.get("ip", "unknown")
            req_id = data.get("req_id")

            self.showNormal()
            self.activateWindow()
            reply = QMessageBox.question(
                self,
                "🛡️ Pairing Request Received",
                f"<b>{device_name}</b> ({ip}) is requesting to connect to your PC.<br><br>"
                f"Do you want to authorize this device?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                auth_mgr.approve_pairing(req_id)
                QMessageBox.information(self, "Device Approved", f"Authorized {device_name} successfully.")
            else:
                auth_mgr.reject_pairing(req_id, block_ip=False)
            self._refresh_device_lists()

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

    def _setup_tray(self):
        self.tray = ContinuityTrayIcon(self.icon_path, self.current_url, self)
        self.tray.toggle_window.connect(self.toggle_visibility)
        self.tray.open_downloads.connect(self._open_downloads)
        self.tray.quit_app.connect(self.close)
        self.tray.show()

    def _select_local_mode(self):
        self.current_url = self.local_url
        self._update_display_url()

    def _select_tailscale_mode(self):
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

    def _update_display_url(self):
        self.lbl_url.setText(self.current_url)
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
        subprocess.Popen(["xdg-open", file_mgr.get_default_save_dir()])

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

    def _send_phone_command(self, action: str, param: str = ""):
        try:
            url = f"http://127.0.0.1:{self.port}/api/phone/control"
            payload = json.dumps({"action": action, "param": param}).encode("utf-8")
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read().decode())
                delivered = data.get("delivered", 0)
                has_active = data.get("has_active_devices", False)
                if delivered > 0:
                    audit_logger.log("PHONE_CTRL", f"Command '{action}' delivered to phone ({delivered} channel(s))")
                elif has_active:
                    audit_logger.log("PHONE_CTRL", f"Command '{action}' queued for active phone")
                else:
                    QMessageBox.warning(self, "Phone Offline", "No active phone connected. Connect phone first.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to send command: {e}")

    def _send_phone_toast(self):
        msg = self.txt_toast_msg.text().strip()
        if not msg:
            return
        self._send_phone_command("toast", msg)
        self.txt_toast_msg.clear()

    def _open_url_on_phone(self):
        url = self.txt_phone_url.text().strip()
        if not url:
            return
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url
        self._send_phone_command("url", url)
        self.txt_phone_url.clear()

    def _refresh_phone_telemetry(self):
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/phone/telemetry")
            with urllib.request.urlopen(req, timeout=1) as resp:
                data = json.loads(resp.read().decode())
                tel = data.get("telemetry")
                if not tel:
                    if hasattr(self, "lbl_phone_tel"):
                        self.lbl_phone_tel.setText("📱 Target: <span style='color: #8E8E93;'>No active phone connected</span>")
                    if hasattr(self, "lbl_phone_battery"):
                        self.lbl_phone_battery.setText("🔋 Battery: --")
                        self.lbl_phone_battery.setStyleSheet("font-size: 12px; color: #8E8E93;")
                    return

                dev = tel.get("device", "Android Phone")
                ip = tel.get("ip", "")
                bat = tel.get("battery")
                charging = tel.get("charging", False)

                if hasattr(self, "lbl_phone_tel"):
                    self.lbl_phone_tel.setText(f"📱 Target: <b>{dev}</b> {f'({ip})' if ip else ''}")
                if hasattr(self, "lbl_phone_battery"):
                    if bat is not None and isinstance(bat, (int, float)) and bat >= 0:
                        chg = " (⚡ Charging)" if charging else " (Discharging)"
                        self.lbl_phone_battery.setText(f"🔋 Battery: {int(bat)}%{chg}")
                        self.lbl_phone_battery.setStyleSheet("font-size: 12px; color: #34c759; font-weight: bold;")
                    else:
                        self.lbl_phone_battery.setText("🔋 Battery: --")
                        self.lbl_phone_battery.setStyleSheet("font-size: 12px; color: #8E8E93;")
                if hasattr(self, "txt_adb_addr") and ip and not self.txt_adb_addr.text():
                    self.txt_adb_addr.setText(f"{ip}:5555")
        except Exception:
            pass

    def _toggle_phone_camera_feed(self):
        if self.phone_cam_active:
            self.phone_cam_active = False
            self.phone_cam_timer.stop()
            self.btn_phone_cam_toggle.setText("🔴 Start Phone Camera Feed")
            self._send_phone_command("camera_stop")
            self.lbl_phone_cam_view.setText("Phone camera feed stopped.")
        else:
            self.phone_cam_active = True
            self.phone_cam_timer.start(700)
            self.btn_phone_cam_toggle.setText("⏹ Stop Phone Feed")
            self._send_phone_command("camera_start", "back")

    def _poll_phone_camera_frame(self):
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/phone/camera/frame")
            with urllib.request.urlopen(req, timeout=1) as resp:
                img_data = resp.read()
                pix = QPixmap()
                if pix.loadFromData(img_data):
                    scaled = pix.scaled(
                        self.lbl_phone_cam_view.size(),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    )
                    self.lbl_phone_cam_view.setPixmap(scaled)
        except Exception:
            pass

    def _connect_wireless_adb(self):
        addr = self.txt_adb_addr.text().strip()
        if not addr:
            QMessageBox.warning(self, "Missing Address", "Enter phone IP:Port (e.g. 192.168.1.50:5555).")
            return
        try:
            res = subprocess.run(["adb", "connect", addr], capture_output=True, text=True, timeout=5)
            out = res.stdout.strip()
            QMessageBox.information(self, "ADB Output", f"Result:\n{out}")
            audit_logger.log("ADB", f"adb connect {addr}: {out}")
        except Exception as e:
            QMessageBox.critical(self, "ADB Error", f"ADB command failed: {e}")

    def _open_phone_shell(self):
        addr = self.txt_adb_addr.text().strip()
        target = f"-s {addr}" if addr else ""
        term_cmd = f"adb {target} shell"
        try:
            subprocess.Popen(["x-terminal-emulator", "-e", f"bash -c '{term_cmd}; exec bash'"])
        except Exception:
            try:
                subprocess.Popen(["konsole", "-e", f"bash -c '{term_cmd}; exec bash'"])
            except Exception as e:
                QMessageBox.critical(self, "Terminal Error", f"Could not launch terminal emulator: {e}")

    def closeEvent(self, event):
        if hasattr(self, "phone_cam_timer") and self.phone_cam_timer.isActive():
            self.phone_cam_timer.stop()
        if self.cam_timer.isActive():
            self.cam_timer.stop()
        if self.poll_timer.isActive():
            self.poll_timer.stop()
        event.accept()
