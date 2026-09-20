"""
Linux Continuity Server - Tornado Async Web & WebSocket Gateway
Supports real-time terminal streaming over WebSockets, shared tmux sessions,
clipboard sync, file transfers, and remote connectivity (Cloudflare Tunnels & Tailscale).
Developed by killindodo
"""

import os
import sys
import time
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
    type_text,
    trackpad_move,
    trackpad_scroll,
    mouse_press,
    mouse_release
)
from core.media_controller import (
    get_volume_info,
    set_volume,
    toggle_mute,
    get_mpris_status,
    mpris_command
)
from core.system_monitor import get_system_stats
from core.power_manager import (
    execute_power_action,
    launch_application,
    send_desktop_notification
)
from core.tunnel import (
    get_tailscale_ip,
    get_ssh_info,
    is_tailscale_running,
    toggle_tailscale
)
from core.clipboard_sync import ClipboardSync
from core.file_manager import FileManager
from core.auth import AuthManager
from core.av_capture import av_mgr
from core.window_controller import (
    list_desktop_terminal_windows,
    capture_window_frame,
    send_to_window
)
from core.activity_logger import audit_logger

# Globals
file_mgr = FileManager()
clip_sync = ClipboardSync()
auth_mgr = AuthManager()
connected_clip_clients = set()
connected_term_clients = set()


def on_auth_security_event(event_type, data):
    """Disconnects live WebSockets immediately when an administrator kicks or blocks a device."""
    if event_type in ("device_kicked", "device_blocked"):
        token = data.get("token")
        ip = data.get("ip")
        # Disconnect terminal sockets
        for ws in list(connected_term_clients):
            ws_token = getattr(ws, "client_token", None)
            ws_ip = getattr(ws, "client_ip", None)
            if (token and ws_token == token) or (ip and ws_ip == ip):
                try:
                    ws.write_message(b"\r\n\x1b[31m[!] Disconnected: Session terminated by PC administrator.\x1b[0m\r\n", binary=True)
                    ws.close()
                except Exception:
                    pass
        # Disconnect clipboard sockets
        for ws in list(connected_clip_clients):
            ws_token = getattr(ws, "client_token", None)
            ws_ip = getattr(ws, "client_ip", None)
            if (token and ws_token == token) or (ip and ws_ip == ip):
                try:
                    ws.close()
                except Exception:
                    pass

auth_mgr.add_pairing_listener(on_auth_security_event)


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
    """Handles pairing requests with device metadata, PIN verification, and Zero-Trust host authorization."""
    def post(self):
        client_ip = self.request.remote_ip
        if auth_mgr.is_ip_blocked(client_ip):
            self.set_status(403)
            self.set_header("Content-Type", "application/json")
            self.write(json.dumps({"status": "blocked", "message": "Access Denied: This device or IP address has been blocked by the PC administrator."}))
            return

        try:
            data = json.loads(self.request.body)
            pin = str(data.get("pin", "")).strip()
            device_name = str(data.get("device_name", "")).strip() or f"Client ({client_ip})"
            user_agent = self.request.headers.get("User-Agent", "")

            # Execute device pairing handshake
            res = auth_mgr.request_pairing(pin, device_name, client_ip, user_agent)
            if res.get("status") == "approved":
                self.set_header("Content-Type", "application/json")
                self.write(json.dumps({"status": "success", "token": res["token"], "device_name": device_name}))
            elif res.get("status") == "pending":
                self.set_header("Content-Type", "application/json")
                self.write(json.dumps(res))
            elif res.get("status") == "blocked":
                self.set_status(403)
                self.set_header("Content-Type", "application/json")
                self.write(json.dumps(res))
            else:
                self.set_status(401)
                self.set_header("Content-Type", "application/json")
                self.write(json.dumps(res))
        except Exception as e:
            self.set_status(400)
            self.set_header("Content-Type", "application/json")
            self.write(json.dumps({"status": "error", "message": str(e)}))


class PairStatusHandler(tornado.web.RequestHandler):
    """Polled by mobile clients waiting for PC administrator approval."""
    def get(self):
        req_id = self.get_argument("req_id", "")
        res = auth_mgr.check_pairing_status(req_id)
        self.set_header("Content-Type", "application/json")
        self.write(json.dumps(res))


class AdminDevicesHandler(tornado.web.RequestHandler):
    """Admin API for PC dashboard to inspect active, pending, and blocked devices."""
    def get(self):
        token = self.get_argument("token", None)
        client_ip = self.request.remote_ip
        is_local = client_ip in ("127.0.0.1", "::1")
        if not is_local and not auth_mgr.is_authorized(token, client_ip):
            self.set_status(401)
            self.write(json.dumps({"status": "error", "message": "Unauthorized"}))
            return

        # Ensure any active WebSocket clients are kept marked as live
        all_ws_clients = connected_term_clients.union(connected_clip_clients)
        for ws in all_ws_clients:
            ws_ip = getattr(ws, "client_ip", None)
            ws_token = getattr(ws, "client_token", None)
            if ws_ip and ws_ip not in ("127.0.0.1", "::1", "localhost"):
                auth_mgr.record_activity(ws_token, ws_ip)

        self.set_header("Content-Type", "application/json")
        self.write(json.dumps({
            "status": "ok",
            "active_devices": auth_mgr.get_active_devices(),
            "pending_requests": auth_mgr.get_pending_requests(),
            "blocked_devices": auth_mgr.get_blocked_devices(),
            "require_admin_approval": auth_mgr.require_admin_approval,
            "security_pin": auth_mgr.pin
        }))


class AdminDeviceActionHandler(tornado.web.RequestHandler):
    """Admin API to approve, reject, kick, block, or unblock devices directly from PC."""
    def post(self):
        token = self.get_argument("token", None)
        client_ip = self.request.remote_ip
        is_local = client_ip in ("127.0.0.1", "::1")
        if not is_local and not auth_mgr.is_authorized(token, client_ip):
            self.set_status(401)
            self.write(json.dumps({"status": "error", "message": "Unauthorized"}))
            return

        try:
            data = json.loads(self.request.body)
            action = data.get("action")
            target = data.get("target")

            if action == "approve":
                token_out = auth_mgr.approve_pairing(target)
                self.write(json.dumps({"status": "ok" if token_out else "error", "token": token_out}))
            elif action == "reject":
                ok = auth_mgr.reject_pairing(target)
                self.write(json.dumps({"status": "ok" if ok else "error"}))
            elif action == "kick":
                ok = auth_mgr.kick_session(target) or bool(auth_mgr.kick_ip(target))
                self.write(json.dumps({"status": "ok" if ok else "error"}))
            elif action == "block":
                if target in auth_mgr.pending_requests:
                    req_ip = auth_mgr.pending_requests[target]["ip"]
                    auth_mgr.reject_pairing(target, block_ip=True)
                    ok = auth_mgr.block_ip(req_ip)
                else:
                    ok = auth_mgr.block_ip(target)
                self.write(json.dumps({"status": "ok" if ok else "error"}))
            elif action == "unblock":
                ok = auth_mgr.unblock_ip(target)
                self.write(json.dumps({"status": "ok" if ok else "error"}))
            elif action == "set_policy":
                require_approval = bool(data.get("require_approval", True))
                auth_mgr.set_require_admin_approval(require_approval)
                self.write(json.dumps({"status": "ok", "require_admin_approval": require_approval}))
            else:
                self.set_status(400)
                self.write(json.dumps({"status": "error", "message": "Unknown action"}))
        except Exception as e:
            self.set_status(500)
            self.write(json.dumps({"status": "error", "message": str(e)}))


class AdminLogsHandler(tornado.web.RequestHandler):
    """Returns real-time activity and security audit logs."""
    def get(self):
        token = self.get_argument("token", None)
        client_ip = self.request.remote_ip
        is_local = client_ip in ("127.0.0.1", "::1")
        if not is_local and not auth_mgr.is_authorized(token, client_ip):
            self.set_status(401)
            self.write(json.dumps({"status": "error", "message": "Unauthorized"}))
            return
        limit = int(self.get_argument("limit", 150))
        self.set_header("Content-Type", "application/json")
        self.write(json.dumps({
            "status": "ok",
            "logs": audit_logger.get_logs(limit=limit)
        }))

    def delete(self):
        token = self.get_argument("token", None)
        client_ip = self.request.remote_ip
        is_local = client_ip in ("127.0.0.1", "::1")
        if not is_local and not auth_mgr.is_authorized(token, client_ip):
            self.set_status(401)
            self.write(json.dumps({"status": "error", "message": "Unauthorized"}))
            return
        audit_logger.clear()
        self.set_header("Content-Type", "application/json")
        self.write(json.dumps({"status": "ok", "message": "Logs cleared"}))


class PhoneControlHandler(tornado.web.RequestHandler):
    """Sends remote control commands from PC host to connected Android phone(s)."""
    pending_commands = []

    def post(self):
        token = self.get_argument("token", None)
        client_ip = self.request.remote_ip
        is_local = client_ip in ("127.0.0.1", "::1")
        if not is_local and not auth_mgr.is_authorized(token, client_ip):
            self.set_status(401)
            self.write(json.dumps({"status": "error", "message": "Unauthorized"}))
            return

        try:
            data = json.loads(self.request.body)
            action = data.get("action")
            param = data.get("param", "")
            target_ip = data.get("target_ip", None)

            msg = json.dumps({
                "type": "phone_control",
                "action": action,
                "param": param
            })

            delivered = 0
            delivered_ips = set()

            # 1. Deliver to connected clipboard WebSockets
            for ws in list(connected_clip_clients):
                ws_ip = getattr(ws, "client_ip", None)
                if not target_ip or ws_ip == target_ip:
                    try:
                        ws.write_message(msg)
                        delivered += 1
                        if ws_ip:
                            delivered_ips.add(ws_ip)
                    except Exception:
                        pass

            # 2. Also deliver to connected terminal WebSockets if not already delivered
            for ws in list(connected_term_clients):
                ws_ip = getattr(ws, "client_ip", None)
                if ws_ip and ws_ip in delivered_ips:
                    continue
                if not target_ip or ws_ip == target_ip:
                    try:
                        ws.write_message(msg)
                        delivered += 1
                        if ws_ip:
                            delivered_ips.add(ws_ip)
                    except Exception:
                        pass

            # 3. Buffer in pending_commands for polling fallback
            cmd_entry = {
                "id": uuid.uuid4().hex[:8],
                "action": action,
                "param": param,
                "target_ip": target_ip,
                "timestamp": time.time(),
                "delivered_ips": set(delivered_ips)
            }
            PhoneControlHandler.pending_commands.append(cmd_entry)
            now = time.time()
            PhoneControlHandler.pending_commands = [
                c for c in PhoneControlHandler.pending_commands if now - c["timestamp"] < 30.0
            ]

            has_active = len([d for d in auth_mgr.get_active_devices() if not d.get("is_localhost")]) > 0
            audit_logger.log("PHONE_CTRL", f"Executed '{action}' on phone (delivered to {delivered} client(s), queued: {has_active})")
            self.write(json.dumps({
                "status": "ok",
                "delivered": delivered,
                "has_active_devices": has_active
            }))
        except Exception as e:
            self.set_status(500)
            self.write(json.dumps({"status": "error", "message": str(e)}))

    def get(self):
        """Allows phone to poll for pending commands as fallback."""
        token = self.get_argument("token", None)
        client_ip = self.request.remote_ip
        if not auth_mgr.is_authorized(token, client_ip):
            self.set_status(401)
            self.write(json.dumps({"status": "error", "message": "Unauthorized"}))
            return

        now = time.time()
        cmds_to_send = []
        for cmd in PhoneControlHandler.pending_commands:
            if not cmd.get("target_ip") or cmd.get("target_ip") == client_ip:
                delivered_set = cmd.setdefault("delivered_ips", set())
                if client_ip not in delivered_set:
                    cmds_to_send.append({"action": cmd["action"], "param": cmd["param"]})
                    delivered_set.add(client_ip)

        self.set_header("Content-Type", "application/json")
        self.write(json.dumps({"status": "ok", "commands": cmds_to_send}))


class PhoneTelemetryHandler(tornado.web.RequestHandler):
    """Stores and serves real telemetry from Android phone (battery, charging, screen, etc.)."""
    telemetry_store = {}

    def post(self):
        try:
            data = json.loads(self.request.body)
            client_ip = self.request.remote_ip
            # Ignore localhost telemetry (tests)
            if client_ip in ("127.0.0.1", "::1", "localhost"):
                self.write(json.dumps({"status": "ok", "ignored": "localhost"}))
                return

            now = time.time()
            data["ip"] = client_ip
            data["updated_at"] = now
            ua = self.request.headers.get("User-Agent", "")
            dev = data.get("device", "")
            auth_mgr.record_activity(None, client_ip, ua, dev)

            # Match clean device name from session if available
            clean_name = None
            for sess in auth_mgr.active_sessions.values():
                if sess.get("ip") == client_ip and sess.get("device_name"):
                    clean_name = sess.get("device_name")
                    break
            if clean_name:
                data["device"] = clean_name
            elif dev and "I2221" in dev:
                data["device"] = "iQOO Neo 9 Pro (I2221)"

            PhoneTelemetryHandler.telemetry_store[client_ip] = data
            self.write(json.dumps({"status": "ok"}))
        except Exception as e:
            self.set_status(400)
            self.write(json.dumps({"status": "error", "message": str(e)}))

    def get(self):
        now = time.time()
        # Clean out stale (> 60s) or localhost entries
        valid_store = {}
        for ip, t in PhoneTelemetryHandler.telemetry_store.items():
            if ip not in ("127.0.0.1", "::1", "localhost") and (now - t.get("updated_at", 0)) < 60.0:
                valid_store[ip] = t
        PhoneTelemetryHandler.telemetry_store = valid_store

        target_ip = self.get_argument("ip", None)
        selected_tel = None

        if target_ip and target_ip in valid_store:
            selected_tel = valid_store[target_ip]
        elif valid_store:
            selected_tel = list(valid_store.values())[-1]
        else:
            # Check if there is an active remote device in auth_mgr that has not yet sent telemetry
            active_devs = [d for d in auth_mgr.get_active_devices() if not d.get("is_localhost")]
            if active_devs:
                latest_dev = active_devs[-1]
                selected_tel = {
                    "device": latest_dev.get("device_name", "Android Phone"),
                    "ip": latest_dev.get("ip", ""),
                    "battery": None,
                    "charging": False,
                    "status": "connected",
                    "updated_at": now
                }
            else:
                selected_tel = None

        self.set_header("Content-Type", "application/json")
        if selected_tel:
            self.write(json.dumps({"status": "ok", "telemetry": selected_tel}))
        else:
            self.write(json.dumps({"status": "idle", "telemetry": None}))


class PhoneCameraFrameHandler(tornado.web.RequestHandler):
    """Receives camera snapshots from Android phone and serves to PC viewfinder."""
    latest_frame = None
    latest_frame_time = 0
    stream_active = False

    def post(self):
        PhoneCameraFrameHandler.latest_frame = self.request.body
        PhoneCameraFrameHandler.latest_frame_time = time.time()
        PhoneCameraFrameHandler.stream_active = True
        self.write(json.dumps({"status": "ok"}))

    def get(self):
        now = time.time()
        if PhoneCameraFrameHandler.latest_frame and (now - PhoneCameraFrameHandler.latest_frame_time) < 6.0:
            self.set_header("Content-Type", "image/jpeg")
            self.set_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.write(PhoneCameraFrameHandler.latest_frame)
        else:
            self.set_status(404)
            self.write("No active phone camera frame")


class IndexHandler(tornado.web.RequestHandler):
    def get(self):
        client_ip = self.request.remote_ip
        if auth_mgr.is_ip_blocked(client_ip):
            self.set_status(403)
            self.write("<h1>403 Forbidden</h1><p>Access Denied: Your IP address has been blocked by the Linux PC administrator.</p>")
            return
        self.render(os.path.join(PROJECT_ROOT, "templates", "index.html"))


class TerminalStandaloneHandler(tornado.web.RequestHandler):
    """Direct, distraction-free full-screen terminal page for mobile browsers."""
    def get(self):
        client_ip = self.request.remote_ip
        if auth_mgr.is_ip_blocked(client_ip):
            self.set_status(403)
            self.write("<h1>403 Forbidden</h1><p>Access Denied: Blocked by administrator.</p>")
            return
        self.render(os.path.join(PROJECT_ROOT, "templates", "terminal.html"))


class TerminalWebSocket(tornado.websocket.WebSocketHandler):
    # Keepalive heartbeats to prevent mobile cellular carrier NAT & Cloudflare idle timeouts
    @property
    def ping_interval(self):
        return 15  # seconds

    @property
    def ping_timeout(self):
        return 35  # seconds

    def check_origin(self, origin):
        return True  # Allow local network and remote tunnel connections

    def open(self):
        client_ip = self.request.remote_ip
        token = self.get_argument("token", None)
        ua = self.request.headers.get("User-Agent", "")
        if auth_mgr.is_ip_blocked(client_ip) or not auth_mgr.is_authorized(token, client_ip, ua):
            self.write_message(b"\r\n\x1b[31m[!] Unauthorized: Access blocked or invalid PIN.\x1b[0m\r\n", binary=True)
            self.close()
            return

        self.client_token = token
        self.client_ip = client_ip
        connected_term_clients.add(self)

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
        if hasattr(self, "session"):
            if isinstance(message, str) and message.startswith("{") and message.endswith("}"):
                try:
                    data = json.loads(message)
                    if data.get("type") == "resize":
                        cols = int(data.get("cols", 80))
                        rows = int(data.get("rows", 24))
                        self.session.resize(cols, rows)
                        return
                except Exception:
                    pass
            if isinstance(message, str):
                self.session.write(message)

    def on_close(self):
        connected_term_clients.discard(self)
        if hasattr(self, "session"):
            self.session.close()


class ClipboardWebSocket(tornado.websocket.WebSocketHandler):
    @property
    def ping_interval(self):
        return 12

    @property
    def ping_timeout(self):
        return 35

    def check_origin(self, origin):
        return True

    def open(self):
        client_ip = self.request.remote_ip
        token = self.get_argument("token", None)
        ua = self.request.headers.get("User-Agent", "")
        if auth_mgr.is_ip_blocked(client_ip) or not auth_mgr.is_authorized(token, client_ip, ua):
            self.close()
            return
        self.client_token = token
        self.client_ip = client_ip
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
        token = self.get_argument("token", None)
        if not auth_mgr.is_authorized(token):
            self.set_status(401)
            self.write(json.dumps({"status": "error", "message": "Unauthorized"}))
            return

        target_dir = self.get_argument("target_dir", None)
        files = self.request.files.get("files", [])
        saved = []
        for f in files:
            filename = f.get("filename")
            body = f.get("body")
            if filename and body:
                path = file_mgr.save_file(filename, body, target_dir=target_dir)
                saved.append(os.path.basename(path))

        self.set_header("Content-Type", "application/json")
        self.write(json.dumps({
            "status": "success",
            "saved": saved,
            "target_dir": target_dir or file_mgr.get_default_save_dir()
        }))


class FilesListHandler(tornado.web.RequestHandler):
    def get(self):
        token = self.get_argument("token", None)
        if not auth_mgr.is_authorized(token):
            self.set_status(401)
            self.write(json.dumps({"status": "error", "message": "Unauthorized"}))
            return

        dir_path = self.get_argument("dir", None)
        files = file_mgr.list_files(dir_path=dir_path)
        self.set_header("Content-Type", "application/json")
        self.write(json.dumps({
            "files": files,
            "current_dir": dir_path or file_mgr.get_default_save_dir()
        }))


class FileBrowseHandler(tornado.web.RequestHandler):
    def get(self):
        token = self.get_argument("token", None)
        if not auth_mgr.is_authorized(token):
            self.set_status(401)
            self.write(json.dumps({"status": "error", "message": "Unauthorized"}))
            return

        path = self.get_argument("path", None)
        data = file_mgr.browse_directory(path)
        self.set_header("Content-Type", "application/json")
        self.write(json.dumps({"status": "ok", **data}))

    def post(self):
        token = self.get_argument("token", None)
        if not auth_mgr.is_authorized(token):
            self.set_status(401)
            self.write(json.dumps({"status": "error", "message": "Unauthorized"}))
            return

        try:
            body = json.loads(self.request.body)
            action = body.get("action")
            if action == "set_default":
                path = body.get("path")
                ok = file_mgr.set_default_save_dir(path)
                self.write(json.dumps({"status": "ok" if ok else "error", "default_save_dir": file_mgr.get_default_save_dir()}))
            elif action == "save_place":
                path = body.get("path")
                ok = file_mgr.add_saved_place(path)
                self.write(json.dumps({"status": "ok" if ok else "error", "saved_places": file_mgr.get_saved_places()}))
            elif action == "remove_place":
                path = body.get("path")
                ok = file_mgr.remove_saved_place(path)
                self.write(json.dumps({"status": "ok" if ok else "error", "saved_places": file_mgr.get_saved_places()}))
            elif action == "mkdir":
                parent = body.get("parent")
                name = body.get("name")
                res = file_mgr.create_directory(parent, name)
                self.write(json.dumps(res))
            else:
                self.write(json.dumps({"status": "error", "message": "Unknown action"}))
        except Exception as e:
            self.write(json.dumps({"status": "error", "message": str(e)}))


class DownloadHandler(tornado.web.RequestHandler):
    def get(self, filename):
        token = self.get_argument("token", None)
        if not auth_mgr.is_authorized(token):
            self.set_status(401)
            self.write("Unauthorized")
            return

        dir_path = self.get_argument("dir", None)
        file_path = file_mgr.get_file_path(filename, dir_path=dir_path)
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


class TunnelApiHandler(tornado.web.RequestHandler):
    """Remote connectivity status and control endpoint (Tailscale Mesh VPN & SSH)."""
    def get(self):
        token = self.get_argument("token", None)
        if not auth_mgr.is_authorized(token, self.request.remote_ip, self.request.headers.get("User-Agent", "")):
            self.set_status(401)
            self.write(json.dumps({"status": "error", "message": "Unauthorized"}))
            return

        self.set_header("Content-Type", "application/json")
        self.write(json.dumps({
            "status": "ok",
            "tailscale_ip": get_tailscale_ip(),
            "tailscale_running": is_tailscale_running(),
            "local_ip": get_local_ip(),
            "ssh": get_ssh_info()
        }))

    def post(self):
        token = self.get_argument("token", None)
        if not auth_mgr.is_authorized(token, self.request.remote_ip, self.request.headers.get("User-Agent", "")):
            self.set_status(401)
            self.write(json.dumps({"status": "error", "message": "Unauthorized"}))
            return

        try:
            data = json.loads(self.request.body)
            action = data.get("action")
            if action == "tailscale_toggle":
                enable = bool(data.get("enable", True))
                res = toggle_tailscale(enable)
                self.write(json.dumps(res))
            else:
                self.set_status(400)
                self.write(json.dumps({"status": "error", "message": "Unknown action"}))
        except Exception as e:
            self.set_status(500)
            self.write(json.dumps({"status": "error", "message": str(e)}))


class TailscaleToggleHandler(tornado.web.RequestHandler):
    """Brings Tailscale mesh VPN UP or DOWN directly from the deck."""
    def post(self):
        token = self.get_argument("token", None)
        if not auth_mgr.is_authorized(token):
            self.set_status(401)
            self.write(json.dumps({"status": "error", "message": "Unauthorized"}))
            return

        try:
            data = json.loads(self.request.body)
            enable = bool(data.get("enable", True))
            res = toggle_tailscale(enable)
            self.set_header("Content-Type", "application/json")
            self.write(json.dumps(res))
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


class CameraFrameHandler(tornado.web.RequestHandler):
    """Serves live camera frame or snapshot from the PC webcam."""
    def get(self):
        token = self.get_argument("token", None)
        if not auth_mgr.is_authorized(token):
            self.set_status(401)
            self.write("Unauthorized")
            return

        w = int(self.get_argument("w", 640))
        h = int(self.get_argument("h", 360))
        q = int(self.get_argument("q", 3))

        frame = av_mgr.capture_frame(width=w, height=h, quality=q)
        if frame:
            self.set_header("Content-Type", "image/jpeg")
            self.set_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.write(frame)
        else:
            self.set_status(503)
            self.write("Webcam unavailable or in use")


class CameraStatusHandler(tornado.web.RequestHandler):
    """Returns webcam and microphone availability status."""
    def get(self):
        token = self.get_argument("token", None)
        if not auth_mgr.is_authorized(token):
            self.set_status(401)
            self.write(json.dumps({"status": "error", "message": "Unauthorized"}))
            return

        self.set_header("Content-Type", "application/json")
        self.write(json.dumps({"status": "ok", **av_mgr.get_status()}))


class MicStreamHandler(tornado.web.RequestHandler):
    """Streams live audio from PC microphone to mobile browser via MP3."""
    async def get(self):
        token = self.get_argument("token", None)
        if not auth_mgr.is_authorized(token):
            self.set_status(401)
            self.write("Unauthorized")
            return

        self.set_header("Content-Type", "audio/mpeg")
        self.set_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.set_header("Connection", "keep-alive")

        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-f", "pulse",
            "-i", "default",
            "-c:a", "libmp3lame",
            "-b:a", "96k",
            "-f", "mp3",
            "-"
        ]

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=2048
        )

        try:
            loop = tornado.ioloop.IOLoop.current()
            while True:
                chunk = await loop.run_in_executor(None, proc.stdout.read, 2048)
                if not chunk:
                    break
                self.write(chunk)
                await self.flush()
        except (tornado.iostream.StreamClosedError, Exception):
            pass
        finally:
            try:
                proc.terminate()
                proc.wait(timeout=1.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass


class DesktopTerminalsHandler(tornado.web.RequestHandler):
    """Lists all open desktop terminal windows."""
    def get(self):
        token = self.get_argument("token", None)
        if not auth_mgr.is_authorized(token):
            self.set_status(401)
            self.write(json.dumps({"status": "error", "message": "Unauthorized"}))
            return

        wins = list_desktop_terminal_windows()
        self.set_header("Content-Type", "application/json")
        self.write(json.dumps({"status": "ok", "windows": wins}))


class DesktopTerminalFrameHandler(tornado.web.RequestHandler):
    """Serves high-resolution live screenshot frame of the chosen desktop terminal window."""
    def get(self):
        token = self.get_argument("token", None)
        if not auth_mgr.is_authorized(token):
            self.set_status(401)
            self.write("Unauthorized")
            return

        wid = self.get_argument("id", None)
        w = int(self.get_argument("w", 960))
        q = int(self.get_argument("q", 65))

        if not wid:
            wins = list_desktop_terminal_windows()
            if wins:
                wid = wins[0]["id"]

        if wid:
            frame = capture_window_frame(wid, width=w, quality=q)
            if frame:
                self.set_header("Content-Type", "image/jpeg")
                self.set_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.write(frame)
                return

        self.set_status(404)
        self.write("Terminal window frame not available")


class DesktopTerminalInputHandler(tornado.web.RequestHandler):
    """Sends keystrokes or text commands directly to the targeted desktop terminal window."""
    def post(self):
        token = self.get_argument("token", None)
        if not auth_mgr.is_authorized(token):
            self.set_status(401)
            self.write(json.dumps({"status": "error", "message": "Unauthorized"}))
            return

        try:
            data = json.loads(self.request.body)
            wid = data.get("id")
            text = data.get("text")
            key = data.get("key")
            press_enter = data.get("press_enter", False)
            focus_only = data.get("focus_only", False)

            if not wid:
                wins = list_desktop_terminal_windows()
                if wins:
                    wid = wins[0]["id"]

            if not wid:
                self.set_status(404)
                self.write(json.dumps({"status": "error", "message": "No active terminal window found"}))
                return

            if focus_only:
                send_to_window(wid)
                self.set_header("Content-Type", "application/json")
                self.write(json.dumps({"status": "ok", "message": "Window focused"}))
                return

            if text:
                send_to_window(wid, text=text)
                if press_enter:
                    send_to_window(wid, key="Return")

            if key:
                send_to_window(wid, key=key)

            self.set_header("Content-Type", "application/json")
            self.write(json.dumps({"status": "ok"}))
        except Exception as e:
            self.set_status(500)
            self.write(json.dumps({"status": "error", "message": str(e)}))


class InfoHandler(tornado.web.RequestHandler):
    def get(self):
        self.set_header("Content-Type", "application/json")
        self.write(json.dumps({
            "hostname": socket.gethostname(),
            "ip": get_local_ip(),
            "tailscale_ip": get_tailscale_ip(),
            "author": "killindodo",
            "version": "1.3.0",
            "require_pin": auth_mgr.require_pin
        }))


class SystemStatsHandler(tornado.web.RequestHandler):
    def get(self):
        token = self.get_argument("token", None)
        if not auth_mgr.is_authorized(token):
            self.set_status(401)
            self.set_header("Content-Type", "application/json")
            self.write(json.dumps({"status": "error", "message": "Unauthorized"}))
            return
        self.set_header("Content-Type", "application/json")
        self.write(json.dumps(get_system_stats()))


class MediaStatusHandler(tornado.web.RequestHandler):
    def get(self):
        vol = get_volume_info()
        mpris = get_mpris_status()
        self.set_header("Content-Type", "application/json")
        self.write(json.dumps({"volume": vol, "media": mpris}))


class MediaControlHandler(tornado.web.RequestHandler):
    def post(self):
        try:
            data = json.loads(self.request.body)
            action = data.get("action")
            if action == "set_volume":
                vol = data.get("volume", 50)
                res = set_volume(vol)
            elif action == "toggle_mute":
                res = toggle_mute()
            elif action in ("PlayPause", "Next", "Previous", "Stop", "Play", "Pause"):
                player_id = data.get("player")
                res = mpris_command(action, player_id)
            else:
                res = {"status": "error", "message": "Unknown media action"}
            self.set_header("Content-Type", "application/json")
            self.write(json.dumps(res))
        except Exception as e:
            self.set_status(500)
            self.write(json.dumps({"status": "error", "message": str(e)}))


class PowerHandler(tornado.web.RequestHandler):
    def post(self):
        try:
            data = json.loads(self.request.body)
            action = data.get("action")
            res = execute_power_action(action)
            self.set_header("Content-Type", "application/json")
            self.write(json.dumps(res))
        except Exception as e:
            self.set_status(500)
            self.write(json.dumps({"status": "error", "message": str(e)}))


class AppLaunchHandler(tornado.web.RequestHandler):
    def post(self):
        try:
            data = json.loads(self.request.body)
            app_name = data.get("app")
            res = launch_application(app_name)
            self.set_header("Content-Type", "application/json")
            self.write(json.dumps(res))
        except Exception as e:
            self.set_status(500)
            self.write(json.dumps({"status": "error", "message": str(e)}))


class NotificationHandler(tornado.web.RequestHandler):
    def post(self):
        try:
            data = json.loads(self.request.body)
            title = data.get("title", "Android Notification")
            message = data.get("message", "")
            urgency = data.get("urgency", "normal")
            res = send_desktop_notification(title, message, urgency)
            self.set_header("Content-Type", "application/json")
            self.write(json.dumps(res))
        except Exception as e:
            self.set_status(500)
            self.write(json.dumps({"status": "error", "message": str(e)}))


class TrackpadHandler(tornado.web.RequestHandler):
    def post(self):
        try:
            data = json.loads(self.request.body)
            event_type = data.get("type", "move")
            if event_type == "move":
                dx = data.get("dx", 0)
                dy = data.get("dy", 0)
                res = trackpad_move(dx, dy)
            elif event_type == "scroll":
                direction = data.get("direction", "down")
                steps = data.get("steps", 1)
                res = trackpad_scroll(direction, steps)
            elif event_type == "mousedown":
                btn = str(data.get("button", "1"))
                res = mouse_press(btn)
            elif event_type == "mouseup":
                btn = str(data.get("button", "1"))
                res = mouse_release(btn)
            elif event_type == "click":
                btn = str(data.get("button", "1"))
                norm_x = data.get("norm_x", 0.5)
                norm_y = data.get("norm_y", 0.5)
                res = click_screen(norm_x, norm_y, btn)
            else:
                res = {"status": "error", "message": "Unknown trackpad event"}
            self.set_header("Content-Type", "application/json")
            self.write(json.dumps(res))
        except Exception as e:
            self.set_status(500)
            self.write(json.dumps({"status": "error", "message": str(e)}))


class ManifestHandler(tornado.web.RequestHandler):
    def get(self):
        self.set_header("Content-Type", "application/manifest+json")
        manifest_path = os.path.join(PROJECT_ROOT, "static", "manifest.json")
        with open(manifest_path, "r") as f:
            self.write(f.read())


class ServiceWorkerHandler(tornado.web.RequestHandler):
    def get(self):
        self.set_header("Content-Type", "application/javascript")
        sw_path = os.path.join(PROJECT_ROOT, "static", "sw.js")
        with open(sw_path, "r") as f:
            self.write(f.read())


class ApkDownloadHandler(tornado.web.RequestHandler):
    """Serves the compiled Android APK directly to phone over Wi-Fi or Tailscale."""
    def head(self):
        apk_path = os.path.join(PROJECT_ROOT, "static", "apk", "LinuxContinuity.apk")
        if not os.path.exists(apk_path):
            self.set_status(404)
            return
        self.set_header("Content-Type", "application/vnd.android.package-archive")
        self.set_header("Content-Disposition", 'attachment; filename="LinuxContinuity.apk"')
        self.set_header("Content-Length", str(os.path.getsize(apk_path)))

    def get(self):
        apk_path = os.path.join(PROJECT_ROOT, "static", "apk", "LinuxContinuity.apk")
        if not os.path.exists(apk_path):
            self.set_status(404)
            self.write("APK is being generated or not found.")
            return
        self.set_header("Content-Type", "application/vnd.android.package-archive")
        self.set_header("Content-Disposition", 'attachment; filename="LinuxContinuity.apk"')
        with open(apk_path, "rb") as f:
            while chunk := f.read(65536):
                self.write(chunk)


def make_app():
    return tornado.web.Application([
        (r"/", IndexHandler),
        (r"/terminal", TerminalStandaloneHandler),
        (r"/manifest.json", ManifestHandler),
        (r"/sw.js", ServiceWorkerHandler),
        (r"/download/app", ApkDownloadHandler),
        (r"/ws/terminal", TerminalWebSocket),
        (r"/ws/clipboard", ClipboardWebSocket),
        (r"/api/auth", AuthHandler),
        (r"/api/auth/pair_status", PairStatusHandler),
        (r"/api/admin/devices", AdminDevicesHandler),
        (r"/api/admin/device_action", AdminDeviceActionHandler),
        (r"/api/admin/logs", AdminLogsHandler),
        (r"/api/phone/control", PhoneControlHandler),
        (r"/api/phone/telemetry", PhoneTelemetryHandler),
        (r"/api/phone/camera/frame", PhoneCameraFrameHandler),
        (r"/api/upload", UploadHandler),
        (r"/api/files", FilesListHandler),
        (r"/api/files/browse", FileBrowseHandler),
        (r"/api/download/(.+)", DownloadHandler),
        (r"/api/terminals", TerminalsApiHandler),
        (r"/api/tunnel", TunnelApiHandler),
        (r"/api/tailscale/toggle", TailscaleToggleHandler),
        (r"/api/screen", ScreenCaptureHandler),
        (r"/api/screen/click", ScreenClickHandler),
        (r"/api/screen/key", ScreenKeyHandler),
        (r"/api/trackpad", TrackpadHandler),
        (r"/api/screen/trackpad", TrackpadHandler),
        (r"/api/system/stats", SystemStatsHandler),
        (r"/api/media/status", MediaStatusHandler),
        (r"/api/media/control", MediaControlHandler),
        (r"/api/power", PowerHandler),
        (r"/api/app/launch", AppLaunchHandler),
        (r"/api/notification", NotificationHandler),
        (r"/api/action", ActionHandler),
        (r"/api/info", InfoHandler),
        (r"/api/camera/frame", CameraFrameHandler),
        (r"/api/camera/status", CameraStatusHandler),
        (r"/api/mic/stream", MicStreamHandler),
        (r"/api/desktop/terminals", DesktopTerminalsHandler),
        (r"/api/desktop/terminal/frame", DesktopTerminalFrameHandler),
        (r"/api/desktop/terminal/input", DesktopTerminalInputHandler),
        (r"/static/(.*)", tornado.web.StaticFileHandler, {"path": os.path.join(PROJECT_ROOT, "static")}),
    ], template_path=os.path.join(PROJECT_ROOT, "templates"))


def run_server(port: int = 8080):
    app = make_app()
    app.listen(port, address="0.0.0.0")
    ip = get_local_ip()
    ts_ip = get_tailscale_ip()
    print("=" * 60)
    print("      Linux Continuity Server (by killindodo)")
    print("=" * 60)
    print(f"[*] Local Wi-Fi:   http://{ip}:{port}")
    if ts_ip:
        print(f"[*] Tailscale VPN: http://{ts_ip}:{port}")
    print(f"[*] Standalone:    http://{ip}:{port}/terminal")
    print("=" * 60)
    tornado.ioloop.IOLoop.current().start()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Linux Continuity Server")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on (default: 8080)")
    args = parser.parse_args()
    run_server(args.port)
