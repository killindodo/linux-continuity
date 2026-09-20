"""
Desktop Window Controller for Linux Continuity.
Detects running desktop terminal windows, captures their visual frame,
and dispatches keystrokes and commands directly to the active PC terminal.
Developed by killindodo
"""

import os
import shutil
import subprocess
from typing import List, Dict, Any, Optional


def get_display_env() -> Dict[str, str]:
    env = os.environ.copy()
    if "DISPLAY" not in env:
        env["DISPLAY"] = ":0"
    if "XAUTHORITY" not in env and os.path.exists(os.path.expanduser("~/.Xauthority")):
        env["XAUTHORITY"] = os.path.expanduser("~/.Xauthority")
    return env


def list_desktop_terminal_windows() -> List[Dict[str, Any]]:
    """Detects all visible terminal emulator windows on the PC desktop."""
    env = get_display_env()
    if not shutil.which("xdotool"):
        return []

    patterns = [
        "konsole", "terminal", "alacritty", "kitty", "xterm",
        "terminator", "tilix", "urxvt", "gnome-terminal", "xfce4-terminal"
    ]
    seen_ids = set()
    windows = []

    for pat in patterns:
        try:
            res = subprocess.run(
                ["xdotool", "search", "--onlyvisible", "--class", pat],
                capture_output=True,
                text=True,
                env=env,
                timeout=1.5
            )
            if res.returncode == 0 and res.stdout.strip():
                for wid in res.stdout.strip().splitlines():
                    wid = wid.strip()
                    if wid and wid not in seen_ids:
                        seen_ids.add(wid)
                        name_res = subprocess.run(
                            ["xdotool", "getwindowname", wid],
                            capture_output=True,
                            text=True,
                            env=env,
                            timeout=1.0
                        )
                        title = name_res.stdout.strip() or f"{pat.capitalize()} ({wid})"
                        windows.append({
                            "id": wid,
                            "title": title,
                            "app": pat
                        })
        except Exception:
            pass

    return windows


def capture_window_frame(window_id: str, width: int = 960, quality: int = 65) -> Optional[bytes]:
    """Captures a high-speed JPEG screenshot of a specific desktop window."""
    env = get_display_env()
    if not shutil.which("import") or not window_id:
        return None

    cmd = ["import", "-window", str(window_id)]
    if width and width > 0:
        cmd.extend(["-resize", f"{width}x"])
    cmd.extend(["-quality", str(quality), "jpg:-"])

    try:
        res = subprocess.run(cmd, capture_output=True, env=env, timeout=2.0)
        if res.returncode == 0 and len(res.stdout) > 200:
            return res.stdout
    except Exception:
        pass
    return None


def send_to_window(window_id: str, text: Optional[str] = None, key: Optional[str] = None) -> bool:
    """Dispatches text or a key event directly to the targeted desktop window."""
    env = get_display_env()
    if not shutil.which("xdotool") or not window_id:
        return False

    try:
        # Activate window first so it receives focus
        subprocess.run(
            ["xdotool", "windowactivate", "--sync", str(window_id)],
            capture_output=True,
            env=env,
            timeout=1.0
        )

        if text is not None:
            # Type text into window
            subprocess.run(
                ["xdotool", "type", "--delay", "5", "--", text],
                capture_output=True,
                env=env,
                timeout=2.0
            )

        if key is not None:
            # Map common names
            key_map = {
                "enter": "Return",
                "return": "Return",
                "bksp": "BackSpace",
                "backspace": "BackSpace",
                "tab": "Tab",
                "esc": "Escape",
                "escape": "Escape",
                "ctrl+c": "ctrl+c",
                "ctrl+d": "ctrl+d",
                "ctrl+z": "ctrl+z",
                "up": "Up",
                "down": "Down",
                "left": "Left",
                "right": "Right",
                "clear": "ctrl+l"
            }
            actual_key = key_map.get(key.lower(), key)
            subprocess.run(
                ["xdotool", "key", actual_key],
                capture_output=True,
                env=env,
                timeout=1.5
            )

        return True
    except Exception:
        return False
