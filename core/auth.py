"""
Authentication, Zero-Trust Device Pairing, and Admin Security Manager for Linux Continuity.
Protects remote connections with device authorization, live device monitoring,
kick/block capabilities, and session tokens.
Developed by killindodo
"""

import os
import sys
import re
import json
import time
import secrets
import uuid
import subprocess
from typing import Optional, Dict, Any, List, Set
from core.activity_logger import audit_logger


class AuthManager:
    def __init__(self):
        self.config_dir = os.path.expanduser("~/.config/linux-continuity")
        self.config_file = os.path.join(self.config_dir, "config.json")
        self.blocked_file = os.path.join(self.config_dir, "blocked_devices.json")
        
        self.pin: str = "2550"
        self.require_pin: bool = True
        self.require_admin_approval: bool = True  # Zero-trust: PC host must approve new devices
        
        self.valid_tokens: Set[str] = set()
        self.active_sessions: Dict[str, Dict[str, Any]] = {}  # token -> session info
        self.pending_requests: Dict[str, Dict[str, Any]] = {}  # req_id -> request info
        self.blocked_ips: Set[str] = set()
        self.trusted_devices: Set[str] = set()  # known paired device identifiers
        
        # Listeners for real-time UI notifications on Linux desktop
        self._pairing_listeners = []

        os.makedirs(self.config_dir, exist_ok=True)
        self._load_config()
        self._load_blocked()

        # Master token for local host
        self.master_token = uuid.uuid4().hex
        self.valid_tokens.add(self.master_token)
        self.active_sessions[self.master_token] = {
            "token": self.master_token,
            "ip": "127.0.0.1",
            "device_name": "Linux PC Localhost",
            "user_agent": "Internal",
            "created_at": time.time(),
            "last_seen": time.time(),
            "status": "active"
        }

    def _load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f:
                    data = json.load(f)
                    self.pin = str(data.get("pin", self.pin))
                    self.require_pin = bool(data.get("require_pin", True))
                    self.require_admin_approval = bool(data.get("require_admin_approval", True))
                    self.trusted_devices = set(data.get("trusted_devices", []))
            except Exception:
                pass

    def _save_config(self):
        try:
            with open(self.config_file, "w") as f:
                json.dump({
                    "pin": self.pin,
                    "require_pin": self.require_pin,
                    "require_admin_approval": self.require_admin_approval,
                    "trusted_devices": list(self.trusted_devices)
                }, f, indent=2)
        except Exception:
            pass

    def _load_blocked(self):
        if os.path.exists(self.blocked_file):
            try:
                with open(self.blocked_file, "r") as f:
                    self.blocked_ips = set(json.load(f))
            except Exception:
                self.blocked_ips = set()

    def _save_blocked(self):
        try:
            with open(self.blocked_file, "w") as f:
                json.dump(list(self.blocked_ips), f, indent=2)
        except Exception:
            pass

    def add_pairing_listener(self, callback):
        if callback not in self._pairing_listeners:
            self._pairing_listeners.append(callback)

    def _notify_listeners(self, event_type: str, data: Dict[str, Any]):
        for cb in list(self._pairing_listeners):
            try:
                cb(event_type, data)
            except Exception:
                pass

    def is_ip_blocked(self, ip: Optional[str]) -> bool:
        if not ip:
            return False
        clean_ip = ip.split(":")[0].strip()
        return clean_ip in self.blocked_ips or ip in self.blocked_ips

    def block_ip(self, ip: str, reason: str = "") -> bool:
        clean_ip = ip.split(":")[0].strip()
        self.blocked_ips.add(clean_ip)
        self._save_blocked()
        
        # Immediately kick all sessions from this IP
        self.kick_ip(clean_ip)
        
        # Cancel any pending requests from this IP
        for req_id, req in list(self.pending_requests.items()):
            if req.get("ip") == clean_ip:
                req["status"] = "blocked"
                
        audit_logger.log("SECURITY", f"IP address {clean_ip} blocked (Reason: {reason or 'Admin action'})", ip=clean_ip)
        self._notify_listeners("device_blocked", {"ip": clean_ip, "reason": reason})
        return True

    def unblock_ip(self, ip: str) -> bool:
        clean_ip = ip.split(":")[0].strip()
        if clean_ip in self.blocked_ips:
            self.blocked_ips.remove(clean_ip)
            self._save_blocked()
            audit_logger.log("SECURITY", f"IP address {clean_ip} unblocked", ip=clean_ip)
            self._notify_listeners("device_unblocked", {"ip": clean_ip})
            return True
        return False

    def kick_session(self, token: str) -> bool:
        if token in self.valid_tokens:
            self.valid_tokens.discard(token)
            session = self.active_sessions.pop(token, None)
            dev = session.get("device_name", "") if session else ""
            ip = session.get("ip", "") if session else ""
            audit_logger.log("SECURITY", f"Device '{dev}' ({ip}) kicked/disconnected by host", device=dev, ip=ip)
            self._notify_listeners("device_kicked", {"token": token, "session": session})
            return True
        return False

    def kick_ip(self, ip: str) -> int:
        clean_ip = ip.split(":")[0].strip()
        kicked = 0
        for token, session in list(self.active_sessions.items()):
            if session.get("ip") == clean_ip and token != self.master_token:
                self.valid_tokens.discard(token)
                self.active_sessions.pop(token, None)
                kicked += 1
                dev = session.get("device_name", "")
                audit_logger.log("SECURITY", f"Device '{dev}' ({clean_ip}) kicked/disconnected by host", device=dev, ip=clean_ip)
                self._notify_listeners("device_kicked", {"token": token, "session": session})
        return kicked

    def set_pin(self, new_pin: str):
        if len(new_pin) >= 4:
            self.pin = str(new_pin)
            self._save_config()

    def set_require_admin_approval(self, required: bool):
        self.require_admin_approval = required
        self._save_config()

    def verify_pin(self, pin_attempt: str, ip: str = "unknown", device_name: str = "Client", user_agent: str = "") -> Optional[str]:
        """Direct PIN verification (legacy/fallback if admin approval disabled)."""
        if self.is_ip_blocked(ip):
            return None

        if not self.require_pin or str(pin_attempt).strip() == self.pin:
            token = uuid.uuid4().hex
            self.valid_tokens.add(token)
            self.active_sessions[token] = {
                "token": token,
                "ip": ip,
                "device_name": device_name,
                "user_agent": user_agent,
                "created_at": time.time(),
                "last_seen": time.time(),
                "status": "active"
            }
            self._notify_listeners("device_connected", self.active_sessions[token])
            return token
        return None

    def request_pairing(self, pin: str, device_name: str, ip: str, user_agent: str = "") -> Dict[str, Any]:
        """
        Device pairing handshake.
        If blocked: rejects immediately.
        If wrong PIN: rejects immediately.
        If require_admin_approval: holds in pending queue and alerts Linux host.
        If approved: issues token.
        """
        clean_ip = ip.split(":")[0].strip()
        if self.is_ip_blocked(clean_ip):
            return {
                "status": "blocked",
                "message": "Access Denied: This device or IP address has been blocked by the PC administrator."
            }

        if self.require_pin and str(pin).strip() != self.pin:
            return {
                "status": "error",
                "message": "Invalid Security PIN. Please verify the PIN displayed on the PC screen."
            }

        # Check if device was previously trusted on this IP
        device_key = f"{device_name}@{clean_ip}"
        if not self.require_admin_approval or device_key in self.trusted_devices:
            # Auto-approve trusted device
            token = uuid.uuid4().hex
            self.valid_tokens.add(token)
            self.active_sessions[token] = {
                "token": token,
                "ip": clean_ip,
                "device_name": device_name,
                "user_agent": user_agent,
                "created_at": time.time(),
                "last_seen": time.time(),
                "status": "active"
            }
            self._notify_listeners("device_connected", self.active_sessions[token])
            return {
                "status": "approved",
                "token": token,
                "device_name": device_name
            }

        # Zero-trust: Add to pending pairing queue and prompt PC host
        req_id = uuid.uuid4().hex[:12]
        pending_item = {
            "req_id": req_id,
            "device_name": device_name,
            "ip": clean_ip,
            "user_agent": user_agent,
            "created_at": time.time(),
            "status": "pending",
            "token": None
        }
        self.pending_requests[req_id] = pending_item

        # Send desktop notification and interactive prompt on Linux PC
        audit_logger.log("SECURITY", f"Pairing request from '{device_name}'", device=device_name, ip=clean_ip)
        self._notify_listeners("pairing_requested", pending_item)
        self._send_desktop_pairing_alert(req_id, device_name, clean_ip)

        return {
            "status": "pending",
            "req_id": req_id,
            "message": "Authorization request sent. Please approve this connection on your Linux PC desktop."
        }

    def check_pairing_status(self, req_id: str) -> Dict[str, Any]:
        req = self.pending_requests.get(req_id)
        if not req:
            return {"status": "error", "message": "Request expired or not found"}

        if req["status"] == "approved":
            return {
                "status": "approved",
                "token": req["token"],
                "device_name": req["device_name"]
            }
        elif req["status"] == "rejected":
            return {"status": "rejected", "message": "Connection request was rejected by host administrator."}
        elif req["status"] == "blocked":
            return {"status": "blocked", "message": "This device has been permanently blocked by the host."}
        else:
            return {"status": "pending", "message": "Waiting for administrator approval..."}

    def approve_pairing(self, req_id: str, remember_device: bool = True) -> Optional[str]:
        req = self.pending_requests.get(req_id)
        if not req:
            return None

        token = uuid.uuid4().hex
        req["status"] = "approved"
        req["token"] = token

        self.valid_tokens.add(token)
        self.active_sessions[token] = {
            "token": token,
            "ip": req["ip"],
            "device_name": req["device_name"],
            "user_agent": req.get("user_agent", ""),
            "created_at": time.time(),
            "last_seen": time.time(),
            "status": "active"
        }

        if remember_device:
            device_key = f"{req['device_name']}@{req['ip']}"
            self.trusted_devices.add(device_key)
            self._save_config()

        audit_logger.log("AUTH", f"Device '{req['device_name']}' authorized & connected", device=req['device_name'], ip=req['ip'])
        self._notify_listeners("device_connected", self.active_sessions[token])
        return token

    def reject_pairing(self, req_id: str, block_ip: bool = False) -> bool:
        req = self.pending_requests.get(req_id)
        if req:
            req["status"] = "blocked" if block_ip else "rejected"
            if block_ip:
                self.block_ip(req["ip"], "Rejected and blocked by host")
            audit_logger.log("SECURITY", f"Pairing request for '{req['device_name']}' {'rejected & blocked' if block_ip else 'denied'}", device=req['device_name'], ip=req['ip'])
            self._notify_listeners("pairing_rejected", req)
            return True
        return False

    def record_activity(self, token: Optional[str], client_ip: Optional[str], user_agent: str = "", device_name: str = "") -> Optional[str]:
        """
        Records or updates an active remote device session whenever it communicates
        with the Linux Continuity server.
        """
        if not client_ip:
            return None
        clean_ip = client_ip.split(":")[0].strip()
        if clean_ip in ("127.0.0.1", "::1", "localhost"):
            return None

        now = time.time()
        # Find if we already have an existing session matching this IP or token
        sess_token = None
        for tok, sess in list(self.active_sessions.items()):
            if tok != self.master_token and (tok == token or sess.get("ip") == clean_ip):
                sess_token = tok
                break

        # Automatically extract human-friendly device name from User-Agent or device_name
        if not device_name:
            if "Android" in user_agent:
                m = re.search(r"Android [^;]+;\s*([^;)]+)", user_agent)
                if m:
                    model_raw = m.group(1).split("Build/")[0].strip()
                    if "I2221" in model_raw:
                        device_name = f"iQOO Neo 9 Pro ({model_raw})"
                    else:
                        device_name = f"Android ({model_raw})"
                else:
                    device_name = f"Android Phone ({clean_ip})"
            elif "iPhone" in user_agent or "iPad" in user_agent:
                device_name = f"Apple iOS ({clean_ip})"
            else:
                device_name = f"Client ({clean_ip})"
        elif "I2221" in device_name and "iQOO" not in device_name:
            device_name = f"iQOO Neo 9 Pro ({device_name})"

        if sess_token and sess_token in self.active_sessions:
            sess = self.active_sessions[sess_token]
            sess["last_seen"] = now
            if user_agent and not sess.get("user_agent"):
                sess["user_agent"] = user_agent
            if device_name and (not sess.get("device_name") or sess.get("device_name", "").startswith("Client")):
                sess["device_name"] = device_name
            return sess_token
        else:
            # Create a new session entry for this remote device
            new_token = token if (token and token != self.master_token) else uuid.uuid4().hex
            self.valid_tokens.add(new_token)
            self.active_sessions[new_token] = {
                "token": new_token,
                "ip": clean_ip,
                "device_name": device_name,
                "user_agent": user_agent,
                "created_at": now,
                "last_seen": now,
                "status": "active"
            }
            audit_logger.log("AUTH", f"Connected device registered: '{device_name}' ({clean_ip})", device=device_name, ip=clean_ip)
            self._notify_listeners("device_connected", self.active_sessions[new_token])
            return new_token

    def is_authorized(self, token: Optional[str], client_ip: Optional[str] = None, user_agent: str = "") -> bool:
        if client_ip and self.is_ip_blocked(client_ip):
            return False

        if not self.require_pin:
            if client_ip:
                try:
                    self.record_activity(token, client_ip, user_agent)
                except Exception as e:
                    print(f"[!] record_activity error: {e}")
            return True

        if token and token in self.valid_tokens:
            if client_ip:
                try:
                    self.record_activity(token, client_ip, user_agent)
                except Exception as e:
                    print(f"[!] record_activity error: {e}")
            elif token in self.active_sessions:
                self.active_sessions[token]["last_seen"] = time.time()
            return True
        return False

    def get_active_devices(self) -> List[Dict[str, Any]]:
        now = time.time()
        devices = []
        for token, s in list(self.active_sessions.items()):
            idle = int(now - s.get("last_seen", now))
            devices.append({
                "token": token,
                "ip": s.get("ip", "unknown"),
                "device_name": s.get("device_name", "Device"),
                "user_agent": s.get("user_agent", ""),
                "connected_time": time.strftime("%H:%M:%S", time.localtime(s.get("created_at", now))),
                "idle_seconds": idle,
                "is_localhost": s.get("ip") in ("127.0.0.1", "::1", "localhost")
            })
        return devices

    def get_pending_requests(self) -> List[Dict[str, Any]]:
        return [
            r for r in self.pending_requests.values()
            if r["status"] == "pending" and (time.time() - r["created_at"]) < 120
        ]

    def get_blocked_devices(self) -> List[str]:
        return sorted(list(self.blocked_ips))

    def _send_desktop_pairing_alert(self, req_id: str, device_name: str, ip: str):
        """
        Sends an interactive desktop notification with action buttons AND
        launches an on-screen authorization prompt dialog.
        """
        import threading
        
        # 1. Launch on-screen PyQt6 prompt dialog
        def _launch_dialog():
            try:
                env = os.environ.copy()
                if "DISPLAY" not in env and "WAYLAND_DISPLAY" not in env:
                    env["DISPLAY"] = ":0"
                dlg_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pairing_dialog.py")
                subprocess.Popen([
                    sys.executable, dlg_script,
                    "--req-id", req_id,
                    "--device", device_name,
                    "--ip", ip
                ], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:
                print(f"[!] Could not launch pairing dialog: {e}")

        threading.Thread(target=_launch_dialog, daemon=True).start()

        # 2. Interactive notify-send with clickable buttons
        def _notify_thread():
            try:
                env = os.environ.copy()
                if "DISPLAY" not in env and "WAYLAND_DISPLAY" not in env:
                    env["DISPLAY"] = ":0"
                cmd = [
                    "notify-send",
                    "-u", "critical",
                    "-a", "Linux Continuity Security",
                    "-i", "security-high",
                    "-A", "approve=✅ Authorize Device",
                    "-A", "reject=❌ Reject",
                    "-A", "block=⛔ Block IP",
                    f"⚠️ Pairing Request: {device_name}",
                    f"IP: {ip}\nClick an action below to respond immediately."
                ]
                proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                action, _ = proc.communicate()
                action = (action or "").strip()
                if action == "approve":
                    self.approve_pairing(req_id)
                elif action == "reject":
                    self.reject_pairing(req_id, block_ip=False)
                elif action == "block":
                    self.reject_pairing(req_id, block_ip=True)
            except Exception as e:
                print(f"[!] Notification listener error: {e}")

        threading.Thread(target=_notify_thread, daemon=True).start()
