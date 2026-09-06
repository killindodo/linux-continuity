"""
Interactive PTY Terminal Manager for Linux Continuity.
Spawns interactive shell sessions and bridges them asynchronously to WebSockets.
"""

import os
import pty
import fcntl
import termios
import struct
import signal
import tornado.ioloop
from typing import Callable, Optional


class TerminalSession:
    def __init__(self, on_output: Callable[[bytes], None], cols: int = 80, rows: int = 24):
        self.on_output = on_output
        self.cols = cols
        self.rows = rows
        self.master_fd: Optional[int] = None
        self.pid: Optional[int] = None
        self.ioloop = tornado.ioloop.IOLoop.current()
        self._alive = False

        self._spawn()

    def _spawn(self):
        shell = os.environ.get("SHELL", "/bin/bash")
        self.pid, self.master_fd = pty.fork()

        if self.pid == 0:
            # Child process
            os.environ["TERM"] = "xterm-256color"
            os.environ["COLORTERM"] = "truecolor"
            os.chdir(os.path.expanduser("~"))

            # Execute user's shell
            os.execv(shell, [shell])
        else:
            # Parent process
            self._alive = True
            # Set non-blocking I/O on master pty
            flags = fcntl.fcntl(self.master_fd, fcntl.F_GETFL)
            fcntl.fcntl(self.master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

            # Set initial window size
            self.resize(self.cols, self.rows)

            # Register with Tornado event loop
            self.ioloop.add_handler(self.master_fd, self._on_pty_read, tornado.ioloop.IOLoop.READ)

    def _on_pty_read(self, fd: int, events: int):
        if not self._alive or self.master_fd is None:
            return

        if events & tornado.ioloop.IOLoop.READ:
            try:
                data = os.read(self.master_fd, 4096)
                if data:
                    self.on_output(data)
                else:
                    self.close()
            except (BlockingIOError, InterruptedError):
                pass
            except Exception:
                self.close()

        if events & (tornado.ioloop.IOLoop.ERROR | tornado.ioloop.IOLoop.WRITE):
            self.close()

    def write(self, data: str):
        if self._alive and self.master_fd is not None:
            try:
                os.write(self.master_fd, data.encode("utf-8", errors="replace"))
            except Exception:
                self.close()

    def resize(self, cols: int, rows: int):
        if self._alive and self.master_fd is not None:
            self.cols = max(10, min(300, cols))
            self.rows = max(4, min(100, rows))
            try:
                winsize = struct.pack("HHHH", self.rows, self.cols, 0, 0)
                fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)
            except Exception:
                pass

    def close(self):
        if not self._alive:
            return
        self._alive = False

        if self.master_fd is not None:
            try:
                self.ioloop.remove_handler(self.master_fd)
                os.close(self.master_fd)
            except Exception:
                pass
            self.master_fd = None

        if self.pid is not None:
            try:
                os.kill(self.pid, signal.SIGHUP)
                os.kill(self.pid, signal.SIGTERM)
                os.waitpid(self.pid, os.WNOHANG)
            except Exception:
                pass
            self.pid = None
