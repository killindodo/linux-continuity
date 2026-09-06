"""
Linux Continuity Server - Tornado Async Web & WebSocket Gateway
Developed by killindodo
"""

import os
import sys
import json
import socket
import subprocess
import argparse
import tornado.web
import tornado.websocket
import tornado.ioloop

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from core.terminal_pty import (
    TerminalSession,
    list_tmux_sessions,
    list_running_pts_processes,
    create_tmux_session,
    kill_tmux_session,
    launch_desktop_terminal
)
from core.screen_mirror import (
    capture_screen_jpeg,
    click_screen,
    send_keystroke,
    type_text
)
from core.clipboard_sync import ClipboardSync
from core.file_manager import FileManager
from core.auth import AuthManager

# Globals
file_mgr = FileManager()
clip_sync = ClipboardSync()
auth_mgr = AuthManager()
connected_clip_clients = set()


def get_local_ip() -> str:
    """Detects local network IP on Wi-Fi/Ethernet."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("1.1.1.1", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# Broadcast clipboard to all connected mobile clients
def on_clipboard_changed(text: str):
    if not connected_clip_clients:
        return
    msg = json.dumps({"type": "clipboard", "text": text})
    for client in list(connected_clip_clients):
        try:
            client.write_message(msg)
        except Exception:
            connected_clip_clients.discard(client)


clip_sync.on_change = on_clipboard_changed
clip_sync.start_polling()


class AuthHandler(tornado.web.RequestHandler):
    def post(self):
        try:
            data = json.loads(self.request.body)
            pin = data.get("pin", "")
            token = auth_mgr.verify_pin(pin)
            if token:
                self.set_header("Content-Type", "application/json")
                self.write(json.dumps({"status": "success", "token": token}))
            else:
                self.set_status(401)
                self.set_header("Content-Type", "application/json")
                self.write(json.dumps({"status": "error", "message": "Invalid PIN"}))
        except Exception as e:
            self.set_status(400)
            self.write(json.dumps({"status": "error", "message": str(e)}))


class IndexHandler(tornado.web.RequestHandler):
    def get(self):
        self.render(os.path.join(PROJECT_ROOT, "templates", "index.html"))


class TerminalWebSocket(tornado.websocket.WebSocketHandler):
    def check_origin(self, origin):
        return True  # Allow local and remote connections

    def open(self):
        token = self.get_argument("token", None)
        if not auth_mgr.is_authorized(token):
            self.write_message(b"\r\n\x1b[31m[!] Unauthorized: Security PIN required.\x1b[0m\r\n", binary=True)
            self.close()
            return

        session_name = self.get_argument("session", "main").strip() or "main"
        self.session = TerminalSession(
            on_output=self._on_pty_output,
            session_name=session_name,
            use_tmux=True
        )

    def _on_pty_output(self, data: bytes):
        try:
            self.write_message(data, binary=True)
        except Exception:
            pass

    def on_message(self, message):
        try:
            msg = json.loads(message)
            msg_type = msg.get("type")
            if msg_type == "input":
                self.session.write(msg.get("data", ""))
            elif msg_type == "resize":
                cols = int(msg.get("cols", 80))
                rows = int(msg.get("rows", 24))
                self.session.resize(cols, rows)
        except Exception:
            # Raw string fallback
            if isinstance(message, str):
                self.session.write(message)

    def on_close(self):
        if hasattr(self, "session"):
            self.session.close()


class ClipboardWebSocket(tornado.websocket.WebSocketHandler):
    def check_origin(self, origin):
        return True

    def open(self):
        token = self.get_argument("token", None)
        if not auth_mgr.is_authorized(token):
            self.close()
            return
        connected_clip_clients.add(self)
        # Send current clipboard immediately on connect
        current = clip_sync.get_clipboard()
        self.write_message(json.dumps({"type": "clipboard", "text": current}))

    def on_message(self, message):
        try:
            data = json.loads(message)
            if data.get("type") == "set_clipboard":
                text = data.get("text", "")
                clip_sync.set_clipboard(text)
        except Exception:
            pass

    def on_close(self):
        connected_clip_clients.discard(self)


class UploadHandler(tornado.web.RequestHandler):
    def post(self):
        files = self.request.files.get("files", [])
        saved = []
        for f in files:
            filename = f.get("filename")
            body = f.get("body")
            if filename and body:
                path = file_mgr.save_file(filename, body)
                saved.append(os.path.basename(path))

        self.set_header("Content-Type", "application/json")
        self.write(json.dumps({"status": "success", "saved": saved}))


class FilesListHandler(tornado.web.RequestHandler):
    def get(self):
        files = file_mgr.list_files()
        self.set_header("Content-Type", "application/json")
        self.write(json.dumps({"files": files}))


class DownloadHandler(tornado.web.RequestHandler):
    def get(self, filename):
        file_path = file_mgr.get_file_path(filename)
        if not file_path:
            self.set_status(404)
            self.write("File not found")
            return

        self.set_header("Content-Type", "application/octet-stream")
        self.set_header("Content-Disposition", f'attachment; filename="{os.path.basename(file_path)}"')
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                self.write(chunk)


class TerminalsApiHandler(tornado.web.RequestHandler):
    def get(self):
        token = self.get_argument("token", None)
        if not auth_mgr.is_authorized(token):
            self.set_status(401)
            self.write(json.dumps({"status": "error", "message": "Unauthorized"}))
            return

        self.set_header("Content-Type", "application/json")
        self.write(json.dumps({
            "status": "ok",
            "tmux_sessions": list_tmux_sessions(),
            "pts_processes": list_running_pts_processes()
        }))

    def post(self):
        token = self.get_argument("token", None)
        if not auth_mgr.is_authorized(token):
            self.set_status(401)
            self.write(json.dumps({"status": "error", "message": "Unauthorized"}))
            return

        try:
            data = json.loads(self.request.body)
            action = data.get("action")
            name = data.get("name", "main").strip()

            if action == "create":
                ok = create_tmux_session(name)
                self.write(json.dumps({"status": "ok" if ok else "error", "created": ok}))
            elif action == "kill":
                ok = kill_tmux_session(name)
                self.write(json.dumps({"status": "ok" if ok else "error", "killed": ok}))
            elif action == "launch_pc":
                ok = launch_desktop_terminal(name)
                self.write(json.dumps({"status": "ok" if ok else "error", "launched": ok}))
            else:
                self.set_status(400)
                self.write(json.dumps({"status": "error", "message": "Unknown action"}))
        except Exception as e:
            self.set_status(500)
            self.write(json.dumps({"status": "error", "message": str(e)}))


class ScreenCaptureHandler(tornado.web.RequestHandler):
    def get(self):
        token = self.get_argument("token", None)
        if not auth_mgr.is_authorized(token):
            self.set_status(401)
            self.write("Unauthorized")
            return

        scale = int(self.get_argument("w", "1024"))
        quality = int(self.get_argument("q", "55"))
        img_bytes = capture_screen_jpeg(scale_width=scale, quality=quality)

        if not img_bytes:
            self.set_status(500)
            self.write("Failed to capture screen")
            return

        self.set_header("Content-Type", "image/jpeg")
        self.set_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.write(img_bytes)


class ScreenClickHandler(tornado.web.RequestHandler):
    def post(self):
        token = self.get_argument("token", None)
        if not auth_mgr.is_authorized(token):
            self.set_status(401)
            self.write(json.dumps({"status": "error", "message": "Unauthorized"}))
            return

        try:
            data = json.loads(self.request.body)
            norm_x = float(data.get("norm_x", 0.5))
            norm_y = float(data.get("norm_y", 0.5))
            button = str(data.get("button", "1"))
            res = click_screen(norm_x, norm_y, button)
            self.set_header("Content-Type", "application/json")
            self.write(json.dumps(res))
        except Exception as e:
            self.set_status(500)
            self.write(json.dumps({"status": "error", "message": str(e)}))


class ScreenKeyHandler(tornado.web.RequestHandler):
    def post(self):
        token = self.get_argument("token", None)
        if not auth_mgr.is_authorized(token):
            self.set_status(401)
            self.write(json.dumps({"status": "error", "message": "Unauthorized"}))
            return

        try:
            data = json.loads(self.request.body)
            if "key" in data:
                res = send_keystroke(data["key"])
            elif "text" in data:
                res = type_text(data["text"])
            else:
                res = {"status": "error", "message": "No key or text provided"}

            self.set_header("Content-Type", "application/json")
            self.write(json.dumps(res))
        except Exception as e:
            self.set_status(500)
            self.write(json.dumps({"status": "error", "message": str(e)}))


class ActionHandler(tornado.web.RequestHandler):
    def post(self):
        try:
            data = json.loads(self.request.body)
            action = data.get("action")
            msg = "Executed"

            if action == "lock_screen":
                subprocess.Popen(["loginctl", "lock-session"])
                msg = "Screen locked"
            elif action == "notify":
                subprocess.Popen(["notify-send", "🔔 Android Ping", "Ping received from mobile phone!"])
                msg = "Desktop pinged"
            elif action == "vol_mute":
                subprocess.Popen(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"])
                msg = "Toggled mute"
            elif action == "open_downloads":
                subprocess.Popen(["xdg-open", file_mgr.download_dir])
                msg = "Opened Downloads folder"
            elif action == "launch_shared_terminal":
                launch_desktop_terminal("main")
                msg = "Launched shared terminal on PC"

            self.set_header("Content-Type", "application/json")
            self.write(json.dumps({"status": "ok", "message": msg}))
        except Exception as e:
            self.set_status(500)
            self.write(json.dumps({"status": "error", "message": str(e)}))


class InfoHandler(tornado.web.RequestHandler):
    def get(self):
        self.set_header("Content-Type", "application/json")
        self.write(json.dumps({
            "hostname": socket.gethostname(),
            "ip": get_local_ip(),
            "author": "killindodo",
            "version": "1.1.0",
            "require_pin": auth_mgr.require_pin
        }))


def make_app():
    return tornado.web.Application([
        (r"/", IndexHandler),
        (r"/ws/terminal", TerminalWebSocket),
        (r"/ws/clipboard", ClipboardWebSocket),
        (r"/api/auth", AuthHandler),
        (r"/api/upload", UploadHandler),
        (r"/api/files", FilesListHandler),
        (r"/api/download/(.+)", DownloadHandler),
        (r"/api/terminals", TerminalsApiHandler),
        (r"/api/screen", ScreenCaptureHandler),
        (r"/api/screen/click", ScreenClickHandler),
        (r"/api/screen/key", ScreenKeyHandler),
        (r"/api/action", ActionHandler),
        (r"/api/info", InfoHandler),
        (r"/static/(.*)", tornado.web.StaticFileHandler, {"path": os.path.join(PROJECT_ROOT, "static")}),
    ], template_path=os.path.join(PROJECT_ROOT, "templates"))


def run_server(port: int = 8080):
    app = make_app()
    app.listen(port, address="0.0.0.0")
    ip = get_local_ip()
    print("=" * 60)
    print("      Linux Continuity Server (by killindodo)")
    print("=" * 60)
    print(f"[*] Server running on: http://{ip}:{port}")
    print(f"[*] Local access:      http://127.0.0.1:{port}")
    print("[*] Open the URL on your Android phone (or scan QR code)")
    print("=" * 60)
    tornado.ioloop.IOLoop.current().start()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Linux Continuity Server")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on (default: 8080)")
    args = parser.parse_args()
    run_server(args.port)
