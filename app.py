#!/usr/bin/env python3
"""
Linux Continuity Hub - Desktop Companion & Web Server
Developed by killindodo
"""

import os
import sys
import threading
import argparse
import signal
import asyncio
import tornado.ioloop

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import QTimer
from ui.main_window import ContinuityWindow
from server import make_app, get_local_ip

__author__ = "killindodo"
__version__ = "1.0.0"


def start_tornado_server(port: int = 8080):
    asyncio.set_event_loop(asyncio.new_event_loop())
    app = make_app()
    app.listen(port, address="0.0.0.0")
    tornado.ioloop.IOLoop.current().start()


def main():
    parser = argparse.ArgumentParser(description="Linux Continuity Hub")
    parser.add_argument("--port", type=int, default=8080, help="Port to run server on (default: 8080)")
    parser.add_argument("--tray", action="store_true", help="Start minimized to system tray")
    args = parser.parse_args()

    # 1. Start Tornado server in daemon thread
    server_thread = threading.Thread(target=start_tornado_server, args=(args.port,), daemon=True)
    server_thread.start()

    # 2. Start Qt GUI
    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName("Linux Continuity")
    qt_app.setApplicationDisplayName("Linux Continuity Hub")
    qt_app.setDesktopFileName("linux-continuity")
    qt_app.setOrganizationName("killindodo")

    icon_path = os.path.join(PROJECT_ROOT, "static", "icons", "icon.png")
    if os.path.exists(icon_path):
        qt_app.setWindowIcon(QIcon(icon_path))

    host_ip = get_local_ip()
    window = ContinuityWindow(PROJECT_ROOT, host_ip, args.port)

    if not args.tray:
        window.show()
    else:
        window.hide()

    # Handle Ctrl+C
    signal.signal(signal.SIGINT, lambda *_: qt_app.quit())
    sig_timer = QTimer()
    sig_timer.start(500)
    sig_timer.timeout.connect(lambda: None)

    sys.exit(qt_app.exec())


if __name__ == "__main__":
    main()
