"""
Desktop Screen Mirror and Remote Input Manager for Linux Continuity.
Captures live desktop frames and simulates mouse clicks and keystrokes via xdotool.
Developed by killindodo
"""

import os
import shutil
import subprocess
from typing import Tuple, Dict, Any


def get_display_env() -> Dict[str, str]:
    """Returns an environment dictionary ensuring DISPLAY and XAUTHORITY are set."""
    env = os.environ.copy()
    if "DISPLAY" not in env:
        env["DISPLAY"] = ":0"
    if "XAUTHORITY" not in env and os.path.exists(os.path.expanduser("~/.Xauthority")):
        env["XAUTHORITY"] = os.path.expanduser("~/.Xauthority")
    return env


def get_screen_geometry() -> Tuple[int, int]:
    """Returns (width, height) in pixels of the active X11 display."""
    if not shutil.which("xdotool"):
        return 1920, 1080
    try:
        res = subprocess.run(
            ["xdotool", "getdisplaygeometry"],
            capture_output=True,
            text=True,
            timeout=2,
            env=get_display_env()
        )
        if res.returncode == 0:
            parts = res.stdout.strip().split()
            if len(parts) >= 2:
                return int(parts[0]), int(parts[1])
    except Exception:
        pass
    return 1920, 1080


def capture_screen_jpeg(scale_width: int = 1024, quality: int = 60) -> bytes:
    """
    Captures the desktop screen as a JPEG byte buffer using ImageMagick.
    Fast and low-latency for streaming to mobile web clients.
    """
    env = get_display_env()
    if shutil.which("import"):
        try:
            cmd = [
                "import",
                "-window", "root",
                "-resize", f"{scale_width}x",
                "-quality", str(quality),
                "jpeg:-"
            ]
            res = subprocess.run(cmd, capture_output=True, timeout=3, env=env)
            if res.returncode == 0 and res.stdout:
                return res.stdout
        except Exception:
            pass

    # Fallback using ffmpeg x11grab if import fails
    if shutil.which("ffmpeg"):
        try:
            w, h = get_screen_geometry()
            display = env.get("DISPLAY", ":0")
            cmd = [
                "ffmpeg",
                "-f", "x11grab",
                "-video_size", f"{w}x{h}",
                "-i", display,
                "-vframes", "1",
                "-s", f"{scale_width}x{int(scale_width * (h / w))}",
                "-q:v", "5",
                "-f", "image2",
                "-"
            ]
            res = subprocess.run(cmd, capture_output=True, timeout=3, env=env)
            if res.returncode == 0 and res.stdout:
                return res.stdout
        except Exception:
            pass

    return b""


def click_screen(norm_x: float, norm_y: float, button: str = "1") -> Dict[str, Any]:
    """
    Simulates a mouse click at normalized coordinates (0.0 to 1.0) on the PC screen.
    Supported button values: '1' (left), '2' (middle), '3' (right), 'double' (double click).
    """
    if not shutil.which("xdotool"):
        return {"status": "error", "message": "xdotool is not installed"}

    w, h = get_screen_geometry()
    px = max(0, min(w - 1, int(norm_x * w)))
    py = max(0, min(h - 1, int(norm_y * h)))
    env = get_display_env()

    try:
        if button == "double":
            subprocess.run(
                ["xdotool", "mousemove", str(px), str(py), "click", "--repeat", "2", "1"],
                check=True,
                timeout=2,
                env=env
            )
        else:
            btn_str = str(button) if str(button) in ["1", "2", "3"] else "1"
            subprocess.run(
                ["xdotool", "mousemove", str(px), str(py), "click", btn_str],
                check=True,
                timeout=2,
                env=env
            )
        return {"status": "ok", "x": px, "y": py, "button": button}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def send_keystroke(key: str) -> Dict[str, Any]:
    """Injects a special key or shortcut via xdotool."""
    if not shutil.which("xdotool"):
        return {"status": "error", "message": "xdotool is not installed"}

    allowed_keys = {
        "Return", "BackSpace", "Tab", "Escape", "space", "Up", "Down", "Left", "Right",
        "ctrl+c", "ctrl+z", "ctrl+v", "ctrl+a", "super", "alt+Tab", "Delete", "Prior", "Next"
    }

    if key not in allowed_keys and not key.isalnum():
        return {"status": "error", "message": "Invalid key specified"}

    try:
        subprocess.run(
            ["xdotool", "key", key],
            check=True,
            timeout=2,
            env=get_display_env()
        )
        return {"status": "ok", "key": key}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def type_text(text: str) -> Dict[str, Any]:
    """Types raw text string into the currently focused window via xdotool."""
    if not shutil.which("xdotool"):
        return {"status": "error", "message": "xdotool is not installed"}

    if not text:
        return {"status": "ok"}

    try:
        subprocess.run(
            ["xdotool", "type", "--", text],
            check=True,
            timeout=5,
            env=get_display_env()
        )
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
