"""
Activity and Security Audit Logger for Linux Continuity.
Tracks device connections, security authorizations, clipboard syncs,
file transfers, and media events with in-memory ring buffer.
Developed by killindodo
"""

import time
import threading
from typing import List, Dict, Any, Callable


class ActivityLogger:
    def __init__(self, max_entries: int = 300):
        self.max_entries = max_entries
        self.logs: List[Dict[str, Any]] = []
        self._listeners: List[Callable[[Dict[str, Any]], None]] = []
        self._lock = threading.Lock()

        # Initial startup entry
        self.log("SYSTEM", "Linux Continuity Core Engine started", ip="127.0.0.1")

    def add_listener(self, cb: Callable[[Dict[str, Any]], None]):
        with self._lock:
            if cb not in self._listeners:
                self._listeners.append(cb)

    def remove_listener(self, cb: Callable[[Dict[str, Any]], None]):
        with self._lock:
            if cb in self._listeners:
                self._listeners.remove(cb)

    def log(self, category: str, message: str, device: str = "", ip: str = ""):
        now = time.time()
        entry = {
            "time": time.strftime("%H:%M:%S", time.localtime(now)),
            "timestamp": now,
            "category": category.upper(),
            "message": message,
            "device": device,
            "ip": ip
        }
        with self._lock:
            self.logs.append(entry)
            if len(self.logs) > self.max_entries:
                self.logs.pop(0)
            listeners = list(self._listeners)

        for cb in listeners:
            try:
                cb(entry)
            except Exception:
                pass

    def get_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self.logs[-limit:])

    def clear(self):
        with self._lock:
            self.logs.clear()
            self.log("SYSTEM", "Audit log cleared by PC Administrator")


# Global singleton instance
audit_logger = ActivityLogger()
