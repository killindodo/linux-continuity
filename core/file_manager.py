"""
File drop and transfer manager for Linux Continuity.
Handles receiving files from Android and listing files for mobile download.
"""

import os
import subprocess
import time
from typing import List, Dict, Any


class FileManager:
    def __init__(self, download_dir: str = None):
        if not download_dir:
            self.download_dir = os.path.expanduser("~/Downloads")
        else:
            self.download_dir = os.path.expanduser(download_dir)

        os.makedirs(self.download_dir, exist_ok=True)

    def save_file(self, filename: str, content: bytes) -> str:
        """Saves an incoming uploaded file to the downloads folder."""
        # Sanitize filename
        safe_name = os.path.basename(filename)
        dest_path = os.path.join(self.download_dir, safe_name)

        # Handle collisions
        base, ext = os.path.splitext(safe_name)
        counter = 1
        while os.path.exists(dest_path):
            dest_path = os.path.join(self.download_dir, f"{base}_{counter}{ext}")
            counter += 1

        with open(dest_path, "wb") as f:
            f.write(content)

        # Notify on desktop
        self._send_notification("File Received", f"Saved {os.path.basename(dest_path)} to Downloads")
        return dest_path

    def list_files(self, limit: int = 30) -> List[Dict[str, Any]]:
        """Lists recent files available for mobile download."""
        files = []
        try:
            entries = os.scandir(self.download_dir)
            sorted_entries = sorted(
                (e for e in entries if e.is_file() and not e.name.startswith(".")),
                key=lambda e: e.stat().st_mtime,
                reverse=True
            )

            for entry in sorted_entries[:limit]:
                stat = entry.stat()
                files.append({
                    "name": entry.name,
                    "size": self._format_size(stat.st_size),
                    "bytes": stat.st_size,
                    "time": time.strftime("%b %d, %H:%M", time.localtime(stat.st_mtime)),
                })
        except Exception:
            pass

        return files

    def get_file_path(self, filename: str) -> str:
        safe_name = os.path.basename(filename)
        path = os.path.join(self.download_dir, safe_name)
        if os.path.exists(path) and os.path.isfile(path):
            return path
        return None

    def _format_size(self, size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

    def _send_notification(self, title: str, body: str):
        try:
            subprocess.Popen(
                ["notify-send", "-a", "Continuity Hub", "-i", "document-send", title, body],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception:
            pass
