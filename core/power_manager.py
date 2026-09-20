"""
Power Management, Desktop Notifications, and App Launchers for Linux Continuity.
Developed by killindodo
"""

import os
import shutil
import subprocess
from typing import Dict, Any


def get_display_env() -> Dict[str, str]:
    """Returns an environment dictionary ensuring DISPLAY and XAUTHORITY are set."""
    env = os.environ.copy()
    if "DISPLAY" not in env:
        env["DISPLAY"] = ":0"
    if "XAUTHORITY" not in env and os.path.exists(os.path.expanduser("~/.Xauthority")):
        env["XAUTHORITY"] = os.path.expanduser("~/.Xauthority")
    return env


def execute_power_action(action: str) -> Dict[str, Any]:
    """
    Executes a system power or display action:
    'lock', 'display_off', 'suspend', 'reboot', 'poweroff'
    """
    env = get_display_env()

    if action == "lock":
        try:
            # Try loginctl first, then xdg-screensaver, then xflock4
            for cmd in [["loginctl", "lock-session"], ["xflock4"], ["xdg-screensaver", "lock"]]:
                if shutil.which(cmd[0]):
                    subprocess.Popen(cmd, env=env)
                    return {"status": "ok", "message": "Screen locked"}
            return {"status": "error", "message": "No lock command found"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    elif action == "display_off":
        try:
            if shutil.which("xset"):
                subprocess.Popen(["xset", "dpms", "force", "off"], env=env)
                return {"status": "ok", "message": "Display powered off"}
            return {"status": "error", "message": "xset command not found"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    elif action == "suspend":
        try:
            subprocess.Popen(["systemctl", "suspend"])
            return {"status": "ok", "message": "System suspended"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    elif action == "reboot":
        try:
            subprocess.Popen(["systemctl", "reboot"])
            return {"status": "ok", "message": "System rebooting"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    elif action == "poweroff":
        try:
            subprocess.Popen(["systemctl", "poweroff"])
            return {"status": "ok", "message": "System shutting down"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    return {"status": "error", "message": f"Unknown power action '{action}'"}


def launch_application(app_name: str) -> Dict[str, Any]:
    """
    Launches a desktop application on the PC:
    'terminal', 'files', 'browser', 'editor', 'calculator', 'settings'
    """
    env = get_display_env()

    app_commands = {
        "terminal": ["x-terminal-emulator", "xfce4-terminal", "gnome-terminal", "alacritty", "kitty", "konsole", "xterm"],
        "files": ["xdg-open", os.path.expanduser("~")],
        "camera": ["cheese", "guvcview", "kamoso", "camorama"],
        "browser": ["x-www-browser", "firefox", "google-chrome", "chromium", "brave-browser"],
        "editor": ["code", "subl", "gedit", "mousepad", "kate", "nano"],
        "calculator": ["galculator", "gnome-calculator", "kcalc", "xcalc"],
        "settings": ["xfce4-settings-manager", "gnome-control-center", "systemsettings"]
    }

    if app_name not in app_commands:
        return {"status": "error", "message": f"Unknown application '{app_name}'"}

    if app_name == "camera":
        from .av_capture import av_mgr
        if av_mgr.open_camera_on_desktop():
            return {"status": "ok", "message": "Opened Camera on PC"}
        return {"status": "error", "message": "Could not open camera on PC"}

    candidates = app_commands[app_name]
    if app_name == "files":
        try:
            subprocess.Popen(["xdg-open", os.path.expanduser("~")], env=env)
            return {"status": "ok", "message": "Opened File Manager"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # For apps with multiple fallbacks
    for cmd_binary in candidates:
        if shutil.which(cmd_binary):
            try:
                subprocess.Popen([cmd_binary], env=env)
                return {"status": "ok", "message": f"Launched {cmd_binary}"}
            except Exception as e:
                return {"status": "error", "message": str(e)}

    return {"status": "error", "message": f"Could not find installed binary for {app_name}"}


def send_desktop_notification(title: str, message: str, urgency: str = "normal") -> Dict[str, Any]:
    """Sends a native desktop notification using notify-send."""
    if not shutil.which("notify-send"):
        return {"status": "error", "message": "notify-send is not installed"}

    valid_urgencies = {"low", "normal", "critical"}
    u = urgency if urgency in valid_urgencies else "normal"

    try:
        subprocess.Popen([
            "notify-send",
            "-a", "Linux Continuity",
            "-u", u,
            "-i", "dialog-information",
            title or "Android Notification",
            message or ""
        ], env=get_display_env())
        return {"status": "ok", "message": "Notification dispatched"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
