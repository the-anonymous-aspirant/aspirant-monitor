"""Read host system metrics from mounted /proc and /sys."""

import logging
import os

from app.config import HOST_PROC, HOST_SYS

logger = logging.getLogger(__name__)


def get_uptime() -> str:
    """Read host uptime from /proc/uptime, return human-readable string."""
    try:
        with open(os.path.join(HOST_PROC, "uptime")) as f:
            seconds = float(f.read().split()[0])
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        parts = []
        if days:
            parts.append(f"{days} days")
        if hours:
            parts.append(f"{hours} hours")
        if minutes:
            parts.append(f"{minutes} min")
        return ", ".join(parts) or "0 min"
    except Exception as exc:
        logger.warning("Failed to read uptime: %s", exc)
        return "unavailable"


def get_load_average() -> dict:
    """Read CPU load averages from /proc/loadavg."""
    try:
        with open(os.path.join(HOST_PROC, "loadavg")) as f:
            parts = f.read().split()
        return {
            "load_1m": float(parts[0]),
            "load_5m": float(parts[1]),
            "load_15m": float(parts[2]),
        }
    except Exception as exc:
        logger.warning("Failed to read load average: %s", exc)
        return {"load_1m": None, "load_5m": None, "load_15m": None}


def get_memory() -> dict:
    """Read memory info from /proc/meminfo."""
    try:
        info = {}
        with open(os.path.join(HOST_PROC, "meminfo")) as f:
            for line in f:
                key, _, value = line.partition(":")
                # Values are in kB
                info[key.strip()] = int(value.strip().split()[0])

        total_kb = info.get("MemTotal", 0)
        available_kb = info.get("MemAvailable", 0)
        used_kb = total_kb - available_kb

        return {
            "total_gb": round(total_kb / 1024 / 1024, 1),
            "used_gb": round(used_kb / 1024 / 1024, 1),
            "available_gb": round(available_kb / 1024 / 1024, 1),
            "percent": round(used_kb / total_kb * 100, 1) if total_kb else 0,
        }
    except Exception as exc:
        logger.warning("Failed to read memory info: %s", exc)
        return {"total_gb": None, "used_gb": None, "available_gb": None, "percent": None}


def get_temperature() -> str:
    """Read CPU temperature from /sys/class/thermal."""
    try:
        thermal_base = os.path.join(HOST_SYS, "class", "thermal")
        for zone in sorted(os.listdir(thermal_base)):
            temp_file = os.path.join(thermal_base, zone, "temp")
            if os.path.isfile(temp_file):
                with open(temp_file) as f:
                    temp_mc = int(f.read().strip())
                return f"{temp_mc // 1000} C"
        return "unavailable"
    except Exception as exc:
        logger.warning("Failed to read temperature: %s", exc)
        return "unavailable"
