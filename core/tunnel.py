"""
Remote Tunnel & Network Detection Engine for Linux Continuity.
Supports Tailscale Mesh VPN and Cloudflare Secure Public Tunnels.
Developed by killindodo
"""

import os
import re
import shutil
import subprocess
import threading
from typing import Optional, Callable


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


class CloudflareTunnel:
    """Manages an ephemeral or permanent Cloudflare Tunnel via cloudflared."""

    def __init__(self, local_port: int = 8080, on_url_ready: Optional[Callable[[str], None]] = None):
        self.local_port = local_port
        self.on_url_ready = on_url_ready
        self.public_url: Optional[str] = None
        self.process: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    @staticmethod
    def is_installed() -> bool:
        return bool(shutil.which("cloudflared") or os.path.exists(os.path.expanduser("~/.local/bin/cloudflared")))

    def start(self) -> bool:
        if self._running:
            return True

        bin_path = shutil.which("cloudflared") or os.path.expanduser("~/.local/bin/cloudflared")
        if not os.path.exists(bin_path):
            return False

        self._running = True
        self.public_url = None

        cmd = [bin_path, "tunnel", "--url", f"http://127.0.0.1:{self.local_port}"]
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
        except Exception:
            self._running = False
            return False

        # Read stderr in background thread (cloudflared prints tunnel URL to stderr)
        self._thread = threading.Thread(target=self._monitor_output, daemon=True)
        self._thread.start()
        return True

    def _monitor_output(self):
        url_pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
        while self._running and self.process and self.process.poll() is None:
            line = self.process.stderr.readline()
            if not line:
                break

            match = url_pattern.search(line)
            if match and not self.public_url:
                self.public_url = match.group(0)
                if self.on_url_ready:
                    self.on_url_ready(self.public_url)

    def stop(self):
        self._running = False
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=2.0)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None
        self.public_url = None
