"""
Clipboard Synchronization Engine for Linux Continuity.
Reads and writes X11/Wayland clipboard and broadcasts updates to connected clients.
"""

import subprocess
import threading
import time
from typing import Callable, Optional, Set


class ClipboardSync:
    def __init__(self, on_change: Optional[Callable[[str], None]] = None):
        self.on_change = on_change
        self.last_text = ""
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def get_clipboard(self) -> str:
        """Reads current X11/Wayland clipboard content."""
        try:
            res = subprocess.run(
                ["xclip", "-selection", "clipboard", "-o"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=1.0,
                text=True,
            )
            return res.stdout
        except Exception:
            pass

        try:
            res = subprocess.run(
                ["xsel", "--clipboard", "--output"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=1.0,
                text=True,
            )
            return res.stdout
        except Exception:
            pass

        return ""

    def set_clipboard(self, text: str):
        """Sets X11/Wayland clipboard content."""
        self.last_text = text
        try:
            p = subprocess.Popen(
                ["xclip", "-selection", "clipboard", "-i"],
                stdin=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            p.communicate(input=text.encode("utf-8"))
            return
        except Exception:
            pass

        try:
            p = subprocess.Popen(
                ["xsel", "--clipboard", "--input"],
                stdin=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            p.communicate(input=text.encode("utf-8"))
        except Exception:
            pass

    def start_polling(self):
        if self._running:
            return
        self._running = True
        self.last_text = self.get_clipboard()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def _poll_loop(self):
        while self._running:
            time.sleep(0.75)
            try:
                current = self.get_clipboard()
                if current != self.last_text and current.strip():
                    self.last_text = current
                    if self.on_change:
                        self.on_change(current)
            except Exception:
                pass

    def stop(self):
        self._running = False
