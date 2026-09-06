"""
Interactive PTY Terminal Manager for Linux Continuity.
Supports shared tmux sessions (attach/mirror), session listing,
process tracking across active PTS instances, and desktop terminal launching.
Developed by killindodo
"""

import os
import pty
import fcntl
import termios
import struct
import signal
import shutil
import subprocess
import tornado.ioloop
from typing import Callable, Optional, List, Dict, Any


class TerminalSession:
    def __init__(
        self,
        on_output: Callable[[bytes], None],
        cols: int = 80,
        rows: int = 24,
        session_name: str = "main",
        use_tmux: bool = True
    ):
        self.on_output = on_output
        self.cols = cols
        self.rows = rows
        self.session_name = session_name
        self.use_tmux = use_tmux and bool(shutil.which("tmux"))
        self.master_fd: Optional[int] = None
        self.pid: Optional[int] = None
        self.ioloop = tornado.ioloop.IOLoop.current()
        self._alive = False

        self._spawn()

    def _spawn(self):
        # Configure tmux to adapt window size dynamically to the active client
        if self.use_tmux:
            try:
                subprocess.run(
                    ["tmux", "set-option", "-g", "window-size", "latest"],
                    capture_output=True,
                    timeout=1
                )
            except Exception:
                pass

        shell = os.environ.get("SHELL", "/bin/bash")
        self.pid, self.master_fd = pty.fork()

        if self.pid == 0:
            # Child process
            os.environ["TERM"] = "xterm-256color"
            os.environ["COLORTERM"] = "truecolor"
            os.chdir(os.path.expanduser("~"))

            if self.use_tmux:
                # Attach to existing session or create a new one with session_name
                cmd = ["tmux", "new-session", "-A", "-s", self.session_name]
                os.execvp("tmux", cmd)
            else:
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


def list_tmux_sessions() -> List[Dict[str, Any]]:
    """Returns a list of all active tmux sessions."""
    if not shutil.which("tmux"):
        return []
    try:
        res = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}|#{session_windows}|#{session_attached}"],
            capture_output=True,
            text=True,
            timeout=2
        )
        if res.returncode != 0:
            return []
        sessions = []
        for line in res.stdout.strip().splitlines():
            if not line:
                continue
            parts = line.split("|")
            if len(parts) >= 3:
                sessions.append({
                    "name": parts[0],
                    "windows": int(parts[1]) if parts[1].isdigit() else 1,
                    "attached": int(parts[2]) if parts[2].isdigit() else 0,
                })
        return sessions
    except Exception:
        return []


def create_tmux_session(name: str) -> bool:
    """Creates a new detached tmux session with the given name."""
    if not shutil.which("tmux") or not name:
        return False
    # Sanitize name
    clean_name = "".join(c for c in name if c.isalnum() or c in ("-", "_")).strip()
    if not clean_name:
        return False
    try:
        res = subprocess.run(
            ["tmux", "new-session", "-d", "-s", clean_name],
            capture_output=True,
            text=True,
            timeout=2
        )
        return res.returncode == 0
    except Exception:
        return False


def kill_tmux_session(name: str) -> bool:
    """Kills an existing tmux session."""
    if not shutil.which("tmux") or not name:
        return False
    try:
        res = subprocess.run(
            ["tmux", "kill-session", "-t", name],
            capture_output=True,
            text=True,
            timeout=2
        )
        return res.returncode == 0
    except Exception:
        return False


def list_running_pts_processes() -> List[Dict[str, str]]:
    """
    Finds and returns active processes running across pseudo-terminals (/dev/pts/*)
    so users can see what commands are running on their PC desktop.
    """
    try:
        res = subprocess.run(
            ["ps", "-eo", "pid,tty,user,args", "--sort=tty"],
            capture_output=True,
            text=True,
            timeout=2
        )
        if res.returncode != 0:
            return []

        procs = []
        for line in res.stdout.strip().splitlines()[1:]:
            parts = line.split(None, 3)
            if len(parts) >= 4:
                pid, tty, user, cmd = parts[0], parts[1], parts[2], parts[3]
                if tty.startswith("pts/"):
                    # Exclude ps and grep themselves
                    if "ps -eo" in cmd or "grep" in cmd:
                        continue
                    procs.append({
                        "pid": pid,
                        "tty": tty,
                        "user": user,
                        "cmd": cmd[:100]
                    })
        return procs
    except Exception:
        return []


def launch_desktop_terminal(session_name: str = "main") -> bool:
    """
    Launches an interactive desktop terminal window on the PC desktop
    connected to the shared tmux session.
    """
    env = os.environ.copy()
    if "DISPLAY" not in env:
        env["DISPLAY"] = ":0"

    emulators = [
        ["konsole", "-e", "tmux", "new-session", "-A", "-s", session_name],
        ["x-terminal-emulator", "-e", f"tmux new-session -A -s {session_name}"],
        ["xfce4-terminal", "-e", f"tmux new-session -A -s {session_name}"],
        ["gnome-terminal", "--", "tmux", "new-session", "-A", "-s", session_name],
        ["xterm", "-e", "tmux", "new-session", "-A", "-s", session_name],
    ]

    for cmd in emulators:
        if shutil.which(cmd[0]):
            try:
                subprocess.Popen(cmd, env=env)
                return True
            except Exception:
                continue
    return False
