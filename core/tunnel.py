"""
Remote Tunnel & Network Detection Engine for Linux Continuity.
Supports Tailscale Mesh VPN, Cloudflare Secure Public Tunnels, and OpenSSH remote info.
Developed by killindodo
"""

import os
import re
import shutil
import getpass
import subprocess
import threading
from typing import Optional, Callable, List, Dict, Any


def is_tailscale_running() -> bool:
    """Returns True if the Tailscale interface/backend is running."""
    ts_bin = shutil.which("tailscale") or "/usr/sbin/tailscale"
    if not os.path.exists(ts_bin):
        return False
    try:
        res = subprocess.run(
            [ts_bin, "status"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=2.0
        )
        return res.returncode == 0
    except Exception:
        return False


def get_tailscale_ip() -> Optional[str]:
    """Returns the local node's IPv4 address on Tailscale mesh, if active."""
    ts_bin = shutil.which("tailscale") or "/usr/sbin/tailscale"
    if not os.path.exists(ts_bin):
        return None

    try:
        res = subprocess.run(
            [ts_bin, "ip", "-4"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2.0
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip().split("\n")[0].strip()
    except Exception:
        pass
    return None


def toggle_tailscale(enable: bool) -> Dict[str, Any]:
    """Brings Tailscale UP or DOWN. Detects operator permission errors gracefully."""
    currently_running = is_tailscale_running()
    if enable and currently_running:
        return {"status": "ok", "running": True, "tailscale_ip": get_tailscale_ip(), "message": "Tailscale is already active"}
    if not enable and not currently_running:
        return {"status": "ok", "running": False, "tailscale_ip": None, "message": "Tailscale is already stopped"}

    ts_bin = shutil.which("tailscale") or "/usr/sbin/tailscale"
    if not os.path.exists(ts_bin):
        return {"status": "error", "message": "Tailscale binary not found"}

    cmd = [ts_bin, "up"] if enable else [ts_bin, "down"]
    try:
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5.0
        )
        if res.returncode == 0:
            ip = get_tailscale_ip() if enable else None
            return {"status": "ok", "running": enable, "tailscale_ip": ip}
        else:
            err = (res.stderr or res.stdout).strip()
            if "operator" in err or "Access denied" in err or "sudo" in err:
                return {
                    "status": "error",
                    "code": "OPERATOR_REQUIRED",
                    "message": "Permission needed. Run 'sudo tailscale set --operator=$USER' on PC once to allow 1-tap toggle without root.",
                    "details": err
                }
            return {"status": "error", "message": err or "Failed to change Tailscale state"}
    except Exception as e:
        return {"status": "error", "message": str(e)}



def get_ssh_info() -> Dict[str, Any]:
    """Returns status and connection commands for local and remote SSH access."""
    is_active = False
    try:
        res = subprocess.run(
            ["systemctl", "is-active", "ssh"],
            capture_output=True,
            text=True,
            timeout=1.5
        )
        is_active = res.stdout.strip() == "active"
    except Exception:
        pass

    user = getpass.getuser()
    ts_ip = get_tailscale_ip()

    return {
        "active": is_active,
        "user": user,
        "tailscale_ip": ts_ip,
        "cmd_tailscale": f"ssh {user}@{ts_ip}" if ts_ip else None,
        "cmd_tmux_remote": f"ssh {user}@{ts_ip} -t tmux new-session -A -s main" if ts_ip else None
    }


# Tailscale Mesh VPN is the primary and recommended secure remote access pipeline.
# Cloudflare tunnels have been removed in favor of direct, zero-trust Tailscale networking.

