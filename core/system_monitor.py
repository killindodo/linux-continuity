"""
System Hardware and Resource Monitor for Linux Continuity.
Gathers real-time CPU, RAM, Disk, Temperature, and Battery statistics.
Developed by killindodo
"""

import os
import time
import socket
from typing import Dict, Any, List

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


def get_uptime_str() -> str:
    """Returns human-readable system uptime."""
    if not PSUTIL_AVAILABLE:
        try:
            with open("/proc/uptime", "r") as f:
                uptime_seconds = float(f.readline().split()[0])
        except Exception:
            return "Unknown"
    else:
        uptime_seconds = time.time() - psutil.boot_time()

    days = int(uptime_seconds // (24 * 3600))
    hours = int((uptime_seconds % (24 * 3600)) // 3600)
    minutes = int((uptime_seconds % 3600) // 60)

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0 or days > 0:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


def get_temperatures() -> Dict[str, Any]:
    """Retrieves CPU and GPU temperatures in Celsius."""
    temps = {"cpu": None, "gpu": None, "all": {}}
    if not PSUTIL_AVAILABLE:
        return temps

    try:
        raw_temps = psutil.sensors_temperatures()
        if not raw_temps:
            return temps

        # Search for CPU temp
        for chip, entries in raw_temps.items():
            temps["all"][chip] = []
            for entry in entries:
                temps["all"][chip].append({
                    "label": entry.label or chip,
                    "current": entry.current,
                    "high": entry.high,
                    "critical": entry.critical
                })
                # Check for common CPU thermal drivers
                if chip in ("k10temp", "coretemp", "cpu_thermal") and temps["cpu"] is None:
                    temps["cpu"] = round(entry.current, 1)
                elif "edge" in entry.label.lower() or "amdgpu" in chip or "nvme" not in chip:
                    if temps["cpu"] is None:
                        temps["cpu"] = round(entry.current, 1)

                if "amdgpu" in chip or "nouveau" in chip or "nvidia" in chip:
                    temps["gpu"] = round(entry.current, 1)

    except Exception:
        pass

    return temps


def get_battery_info() -> Dict[str, Any]:
    """Retrieves battery percentage and power plug state."""
    if not PSUTIL_AVAILABLE:
        return {"has_battery": False}

    try:
        batt = psutil.sensors_battery()
        if batt is None:
            return {"has_battery": False}
        return {
            "has_battery": True,
            "percent": round(batt.percent, 1),
            "plugged": batt.power_plugged,
            "secs_left": batt.secsleft if batt.secsleft > 0 else None
        }
    except Exception:
        return {"has_battery": False}


def get_system_stats() -> Dict[str, Any]:
    """Returns comprehensive real-time system metrics."""
    if not PSUTIL_AVAILABLE:
        return {"error": "psutil not available"}

    # CPU metrics
    cpu_percent = psutil.cpu_percent(interval=None)
    cpu_per_core = psutil.cpu_percent(interval=None, percpu=True)
    cpu_count = psutil.cpu_count(logical=True)
    freq = psutil.cpu_freq()
    cpu_freq_mhz = round(freq.current, 0) if freq else None

    # Memory metrics
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()

    # Storage metrics
    disk = psutil.disk_usage("/")

    # Temps & Battery
    temps = get_temperatures()
    battery = get_battery_info()

    # Load average
    load_1, load_5, load_15 = os.getloadavg() if hasattr(os, "getloadavg") else (0, 0, 0)

    return {
        "hostname": socket.gethostname(),
        "uptime": get_uptime_str(),
        "cpu": {
            "percent": round(cpu_percent, 1),
            "cores": cpu_count,
            "per_core": [round(c, 1) for c in cpu_per_core],
            "freq_mhz": cpu_freq_mhz,
            "temp_c": temps.get("cpu"),
            "load_avg": [round(load_1, 2), round(load_5, 2), round(load_15, 2)]
        },
        "memory": {
            "percent": round(mem.percent, 1),
            "used_mb": round(mem.used / (1024 * 1024), 0),
            "total_mb": round(mem.total / (1024 * 1024), 0),
            "available_mb": round(mem.available / (1024 * 1024), 0),
            "swap_percent": round(swap.percent, 1),
            "swap_used_mb": round(swap.used / (1024 * 1024), 0),
            "swap_total_mb": round(swap.total / (1024 * 1024), 0)
        },
        "disk": {
            "percent": round(disk.percent, 1),
            "used_gb": round(disk.used / (1024 ** 3), 1),
            "total_gb": round(disk.total / (1024 ** 3), 1),
            "free_gb": round(disk.free / (1024 ** 3), 1)
        },
        "temps": temps,
        "battery": battery
    }
