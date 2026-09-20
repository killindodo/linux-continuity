"""
Interactive Desktop Authorization Modal for Linux Continuity.
Pops up on PC screen when a new device requests connection.
Developed by killindodo
"""

import sys
import os
import json
import argparse
import urllib.request
import urllib.error

# Ensure project root is in path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QFont


class PairingDialog(QDialog):
    def __init__(self, req_id: str, device_name: str, ip: str, port: int = 8080):
        super().__init__()
        self.req_id = req_id
        self.device_name = device_name
        self.ip = ip
        self.port = port
        self.resolved = False

        self.setWindowTitle("Linux Continuity • Device Pairing Request")
        self.resize(460, 240)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        icon_path = os.path.join(PROJECT_ROOT, "static", "icons", "icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #0d0f15;
                color: #e4e7ee;
                font-family: 'Segoe UI', 'Ubuntu', sans-serif;
            }
            QFrame#Card {
                background-color: #151822;
                border: 1px solid #252a3a;
                border-radius: 12px;
            }
            QPushButton.primary-btn {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #007aff, stop:1 #0056b3);
                color: #ffffff;
                border: none;
                border-radius: 8px;
                padding: 10px 18px;
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
                padding: 10px 16px;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton.secondary-btn:hover {
                background-color: #2a3042;
                color: #ffffff;
            }
            QPushButton.danger-btn {
                background-color: #3b171c;
                color: #ff5252;
                border: 1px solid #63232b;
                border-radius: 8px;
                padding: 10px 16px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton.danger-btn:hover {
                background-color: #521d24;
                border-color: #ff5252;
                color: #ffffff;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(8)

        lbl_header = QLabel("🛡️ INCOMING DEVICE PAIRING REQUEST")
        lbl_header.setStyleSheet("color: #00d2ff; font-size: 13px; font-weight: 900; letter-spacing: 0.5px;")
        card_layout.addWidget(lbl_header)

        lbl_info = QLabel(
            f"A remote Android device is attempting to pair with your PC:<br><br>"
            f"📱 <b>Device:</b> <span style='color: #ffffff;'>{self.device_name}</span><br>"
            f"🌐 <b>IP Address:</b> <code style='color: #34c759;'>{self.ip}</code>"
        )
        lbl_info.setStyleSheet("color: #b0b8cb; font-size: 13px; line-height: 1.4;")
        card_layout.addWidget(lbl_info)

        lbl_desc = QLabel("Do you want to authorize this device to access your clipboard, terminal, and files?")
        lbl_desc.setStyleSheet("color: #7a8296; font-size: 11px; margin-top: 4px;")
        card_layout.addWidget(lbl_desc)

        layout.addWidget(card)

        # Buttons
        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)

        btn_approve = QPushButton("✅ Authorize Device")
        btn_approve.setProperty("class", "primary-btn")
        btn_approve.clicked.connect(self._approve)
        btn_box.addWidget(btn_approve, stretch=2)

        btn_reject = QPushButton("❌ Deny")
        btn_reject.setProperty("class", "secondary-btn")
        btn_reject.clicked.connect(self._reject)
        btn_box.addWidget(btn_reject, stretch=1)

        btn_block = QPushButton("⛔ Block IP")
        btn_block.setProperty("class", "danger-btn")
        btn_block.clicked.connect(self._block)
        btn_box.addWidget(btn_block, stretch=1)

        layout.addLayout(btn_box)

    def _send_action(self, action: str, target: str):
        url = f"http://127.0.0.1:{self.port}/api/admin/device_action"
        payload = json.dumps({"action": action, "target": target}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=3)
        except Exception as e:
            print(f"[!] Error sending action {action}: {e}")

    def _approve(self):
        self._send_action("approve", self.req_id)
        self.resolved = True
        self.accept()

    def _reject(self):
        self._send_action("reject", self.req_id)
        self.resolved = True
        self.reject()

    def _block(self):
        self._send_action("block", self.ip)
        self.resolved = True
        self.reject()


def main():
    parser = argparse.ArgumentParser(description="Linux Continuity Pairing Dialog")
    parser.add_argument("--req-id", required=True, help="Pairing request ID")
    parser.add_argument("--device", default="Android Device", help="Device model name")
    parser.add_argument("--ip", default="127.0.0.1", help="Client IP address")
    parser.add_argument("--port", type=int, default=8080, help="Local server port")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    dlg = PairingDialog(args.req_id, args.device, args.ip, args.port)
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
