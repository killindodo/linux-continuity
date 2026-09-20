"""
Media and Audio Controller for Linux Continuity.
Interacts with MPRIS D-Bus players and PulseAudio / PipeWire via pactl.
Developed by killindodo
"""

import re
import subprocess
from typing import Dict, Any, Optional

try:
    import dbus
    DBUS_AVAILABLE = True
except ImportError:
    DBUS_AVAILABLE = False


def get_volume_info() -> Dict[str, Any]:
    """Gets current master sink volume percentage and mute status via pactl."""
    volume = 50
    is_muted = False
    try:
        res = subprocess.run(
            ["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
            capture_output=True,
            text=True,
            timeout=2
        )
        if res.returncode == 0:
            match = re.search(r"(\d+)%", res.stdout)
            if match:
                volume = int(match.group(1))
        
        mute_res = subprocess.run(
            ["pactl", "get-sink-mute", "@DEFAULT_SINK@"],
            capture_output=True,
            text=True,
            timeout=2
        )
        if mute_res.returncode == 0:
            is_muted = "yes" in mute_res.stdout.lower()
    except Exception:
        pass

    return {
        "volume": volume,
        "is_muted": is_muted
    }


def set_volume(volume_pct: int) -> Dict[str, Any]:
    """Sets master sink volume percentage (0 to 150)."""
    volume_pct = max(0, min(150, int(volume_pct)))
    try:
        subprocess.run(
            ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{volume_pct}%"],
            check=True,
            timeout=2
        )
        return {"status": "ok", "volume": volume_pct}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def toggle_mute() -> Dict[str, Any]:
    """Toggles master sink mute state."""
    try:
        subprocess.run(
            ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"],
            check=True,
            timeout=2
        )
        return get_volume_info()
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_mpris_status() -> Dict[str, Any]:
    """
    Finds active MPRIS players (Spotify, Firefox, Chrome, VLC, mpv, etc.)
    and returns playback status, title, artist, album, and player list.
    """
    if not DBUS_AVAILABLE:
        return {"available": False, "players": [], "active": None}

    try:
        bus = dbus.SessionBus()
        names = [str(n) for n in bus.list_names() if str(n).startswith("org.mpris.MediaPlayer2.")]
        
        players_data = []
        active_player = None

        for name in names:
            try:
                obj = bus.get_object(name, "/org/mpris/MediaPlayer2")
                props = dbus.Interface(obj, "org.freedesktop.DBus.Properties")
                status = str(props.Get("org.mpris.MediaPlayer2.Player", "PlaybackStatus"))
                meta = props.Get("org.mpris.MediaPlayer2.Player", "Metadata")
                
                title = str(meta.get("xesam:title", "Unknown Title"))
                artists = meta.get("xesam:artist", ["Unknown Artist"])
                artist = ", ".join([str(a) for a in artists]) if isinstance(artists, (list, tuple)) else str(artists)
                album = str(meta.get("xesam:album", ""))
                art_url = str(meta.get("mpris:artUrl", ""))
                player_display = name.replace("org.mpris.MediaPlayer2.", "")

                p_info = {
                    "id": name,
                    "name": player_display,
                    "status": status,
                    "title": title,
                    "artist": artist,
                    "album": album,
                    "art_url": art_url
                }
                players_data.append(p_info)

                # Prioritize currently playing player
                if status.lower() == "playing" and active_player is None:
                    active_player = p_info
            except Exception:
                continue

        if not active_player and players_data:
            active_player = players_data[0]

        return {
            "available": True,
            "players": players_data,
            "active": active_player
        }
    except Exception as e:
        return {"available": False, "error": str(e), "players": [], "active": None}


def mpris_command(action: str, player_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Sends an MPRIS action: 'PlayPause', 'Next', 'Previous', 'Play', 'Pause', 'Stop'.
    If player_id is None, targets the first available or playing player.
    """
    if not DBUS_AVAILABLE:
        return {"status": "error", "message": "D-Bus not available"}

    valid_actions = {"PlayPause", "Next", "Previous", "Play", "Pause", "Stop"}
    if action not in valid_actions:
        return {"status": "error", "message": f"Invalid action {action}"}

    try:
        bus = dbus.SessionBus()
        target = player_id
        if not target:
            names = [str(n) for n in bus.list_names() if str(n).startswith("org.mpris.MediaPlayer2.")]
            if not names:
                return {"status": "error", "message": "No active media players found"}
            target = names[0]

        obj = bus.get_object(target, "/org/mpris/MediaPlayer2")
        player_iface = dbus.Interface(obj, "org.mpris.MediaPlayer2.Player")
        method = getattr(player_iface, action)
        method()

        return {"status": "ok", "action": action, "player": target}
    except Exception as e:
        return {"status": "error", "message": str(e)}
