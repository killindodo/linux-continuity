"""
File drop, browsing, and transfer manager for Linux Continuity.
Handles receiving files, interactive folder browsing, saving custom target locations,
and listing files for mobile download.
Developed by killindodo
"""

import os
import json
import time
import subprocess
from typing import List, Dict, Any, Optional


class FileManager:
    def __init__(self, download_dir: Optional[str] = None):
        self.config_file = os.path.expanduser("~/.config/linux-continuity/config.json")
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        
        self.config = self._load_config()
        if download_dir:
            self.download_dir = os.path.expanduser(download_dir)
        else:
            self.download_dir = self.config.get("default_save_dir") or os.path.expanduser("~/Downloads")

        os.makedirs(self.download_dir, exist_ok=True)

    def _load_config(self) -> Dict[str, Any]:
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "default_save_dir": os.path.expanduser("~/Downloads"),
            "saved_places": [
                os.path.expanduser("~/Downloads"),
                os.path.expanduser("~/Desktop"),
                os.path.expanduser("~/Documents")
            ]
        }

    def _save_config(self):
        try:
            with open(self.config_file, "w") as f:
                json.dump(self.config, f, indent=2)
        except Exception:
            pass

    def get_default_save_dir(self) -> str:
        return self.config.get("default_save_dir") or self.download_dir

    def set_default_save_dir(self, dir_path: str) -> bool:
        """Sets and persists the user's preferred default save folder."""
        expanded = os.path.abspath(os.path.expanduser(dir_path))
        if os.path.exists(expanded) and os.path.isdir(expanded):
            self.download_dir = expanded
            self.config["default_save_dir"] = expanded
            self.add_saved_place(expanded)
            self._save_config()
            return True
        return False

    def get_saved_places(self) -> List[str]:
        places = self.config.get("saved_places", [])
        return [p for p in places if os.path.exists(p) and os.path.isdir(p)]

    def add_saved_place(self, dir_path: str) -> bool:
        expanded = os.path.abspath(os.path.expanduser(dir_path))
        if os.path.exists(expanded) and os.path.isdir(expanded):
            places = self.config.setdefault("saved_places", [])
            if expanded not in places:
                places.append(expanded)
                self._save_config()
            return True
        return False

    def remove_saved_place(self, dir_path: str) -> bool:
        expanded = os.path.abspath(os.path.expanduser(dir_path))
        places = self.config.setdefault("saved_places", [])
        if expanded in places:
            places.remove(expanded)
            self._save_config()
            return True
        return False

    def browse_directory(self, path: Optional[str] = None) -> Dict[str, Any]:
        """Lists subdirectories, files, shortcuts, and metadata for interactive browsing."""
        if not path or not path.strip():
            target_path = self.get_default_save_dir()
        else:
            target_path = os.path.abspath(os.path.expanduser(path.strip()))

        if not os.path.exists(target_path) or not os.path.isdir(target_path):
            target_path = os.path.expanduser("~")

        parent_path = os.path.dirname(target_path) if target_path != "/" else None

        home = os.path.expanduser("~")
        quick_shortcuts = [
            {"name": "Home", "path": home, "icon": "🏠"},
            {"name": "Downloads", "path": os.path.join(home, "Downloads"), "icon": "📥"},
            {"name": "Desktop", "path": os.path.join(home, "Desktop"), "icon": "🖥️"},
            {"name": "Documents", "path": os.path.join(home, "Documents"), "icon": "📄"},
            {"name": "Pictures", "path": os.path.join(home, "Pictures"), "icon": "🖼️"},
        ]
        # Filter existing shortcuts
        quick_shortcuts = [s for s in quick_shortcuts if os.path.exists(s["path"])]

        folders = []
        files = []

        try:
            entries = os.scandir(target_path)
            for entry in entries:
                try:
                    if entry.name.startswith("."):
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        folders.append({
                            "name": entry.name,
                            "path": entry.path
                        })
                    elif entry.is_file(follow_symlinks=False):
                        stat = entry.stat()
                        files.append({
                            "name": entry.name,
                            "path": entry.path,
                            "size": self._format_size(stat.st_size),
                            "bytes": stat.st_size,
                            "time": time.strftime("%b %d, %H:%M", time.localtime(stat.st_mtime)),
                            "mtime": stat.st_mtime
                        })
                except (PermissionError, FileNotFoundError):
                    continue
        except (PermissionError, FileNotFoundError):
            pass

        folders.sort(key=lambda x: x["name"].lower())
        files.sort(key=lambda x: x["mtime"], reverse=True)

        return {
            "current_path": target_path,
            "parent_path": parent_path,
            "default_save_dir": self.get_default_save_dir(),
            "is_default": target_path == self.get_default_save_dir(),
            "quick_shortcuts": quick_shortcuts,
            "saved_places": self.get_saved_places(),
            "folders": folders,
            "files": files
        }

    def create_directory(self, parent_dir: str, name: str) -> Dict[str, Any]:
        """Creates a new folder inside parent_dir."""
        safe_name = os.path.basename(name.strip())
        if not safe_name:
            return {"status": "error", "message": "Invalid folder name"}

        parent = os.path.abspath(os.path.expanduser(parent_dir))
        new_path = os.path.join(parent, safe_name)
        try:
            os.makedirs(new_path, exist_ok=True)
            return {"status": "ok", "path": new_path, "name": safe_name}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def save_file(self, filename: str, content: bytes, target_dir: Optional[str] = None) -> str:
        """Saves an incoming uploaded file to the target or default folder."""
        if target_dir:
            save_folder = os.path.abspath(os.path.expanduser(target_dir))
        else:
            save_folder = self.get_default_save_dir()

        os.makedirs(save_folder, exist_ok=True)

        safe_name = os.path.basename(filename)
        dest_path = os.path.join(save_folder, safe_name)

        # Handle collisions
        base, ext = os.path.splitext(safe_name)
        counter = 1
        while os.path.exists(dest_path):
            dest_path = os.path.join(save_folder, f"{base}_{counter}{ext}")
            counter += 1

        with open(dest_path, "wb") as f:
            f.write(content)

        # Notify on desktop
        folder_display = os.path.basename(save_folder) or save_folder
        self._send_notification("File Received", f"Saved {os.path.basename(dest_path)} to {folder_display}")
        return dest_path

    def list_files(self, dir_path: Optional[str] = None, limit: int = 30) -> List[Dict[str, Any]]:
        """Lists recent files in the given directory or default save directory."""
        folder = os.path.abspath(os.path.expanduser(dir_path)) if dir_path else self.get_default_save_dir()
        files = []
        try:
            entries = os.scandir(folder)
            sorted_entries = sorted(
                (e for e in entries if e.is_file() and not e.name.startswith(".")),
                key=lambda e: e.stat().st_mtime,
                reverse=True
            )

            for entry in sorted_entries[:limit]:
                stat = entry.stat()
                files.append({
                    "name": entry.name,
                    "path": entry.path,
                    "size": self._format_size(stat.st_size),
                    "bytes": stat.st_size,
                    "time": time.strftime("%b %d, %H:%M", time.localtime(stat.st_mtime)),
                })
        except Exception:
            pass

        return files

    def get_file_path(self, filename: str, dir_path: Optional[str] = None) -> Optional[str]:
        folder = os.path.abspath(os.path.expanduser(dir_path)) if dir_path else self.get_default_save_dir()
        safe_name = os.path.basename(filename)
        path = os.path.join(folder, safe_name)
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
