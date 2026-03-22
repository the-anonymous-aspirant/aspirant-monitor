"""Daily health report: collect metrics, format, and send via email."""

import logging
import shutil
import os
from datetime import datetime, timezone

import docker
from docker.errors import DockerException

from app.system_metrics import get_uptime, get_load_average, get_memory, get_temperature
from app.email import send_email

logger = logging.getLogger(__name__)


def _collect_container_stats() -> list[dict]:
    """Collect stats for all containers. Returns list of dicts."""
    try:
        client = docker.DockerClient(base_url="unix:///var/run/docker.sock")
    except DockerException as exc:
        logger.error("Docker unavailable for daily report: %s", exc)
        return []

    results = []
    for container in client.containers.list(all=True):
        info = {"name": container.name, "status": container.status}

        # Uptime
        started = container.attrs["State"].get("StartedAt", "")
        if started and container.status == "running":
            try:
                start_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
                delta = datetime.now(timezone.utc) - start_dt
                days = delta.days
                hours = delta.seconds // 3600
                minutes = (delta.seconds % 3600) // 60
                parts = []
                if days:
                    parts.append(f"{days}d")
                if hours:
                    parts.append(f"{hours}h")
                parts.append(f"{minutes}m")
                info["uptime"] = " ".join(parts)
            except (ValueError, TypeError):
                info["uptime"] = "?"
        else:
            info["uptime"] = "-"

        # Live stats for running containers
        if container.status == "running":
            try:
                stats = container.stats(stream=False)

                cpu_delta = (
                    stats["cpu_stats"]["cpu_usage"]["total_usage"]
                    - stats["precpu_stats"]["cpu_usage"]["total_usage"]
                )
                system_delta = (
                    stats["cpu_stats"].get("system_cpu_usage", 0)
                    - stats["precpu_stats"].get("system_cpu_usage", 0)
                )
                online_cpus = stats["cpu_stats"].get("online_cpus", 1)
                if system_delta > 0 and cpu_delta >= 0:
                    info["cpu"] = f"{(cpu_delta / system_delta) * online_cpus * 100:.1f}%"
                else:
                    info["cpu"] = "0.0%"

                mem_stats = stats.get("memory_stats", {})
                mem_usage = mem_stats.get("usage", 0)
                cache = mem_stats.get("stats", {}).get("cache", 0)
                mem_used = mem_usage - cache
                info["mem"] = f"{mem_used / 1024 / 1024:.0f} MB"
            except Exception:
                info["cpu"] = "?"
                info["mem"] = "?"
        else:
            info["cpu"] = "-"
            info["mem"] = "-"

        results.append(info)

    results.sort(key=lambda c: (0 if c["status"] == "running" else 1, c["name"]))
    return results


def _collect_disk_info() -> list[dict]:
    """Collect disk usage for known mount points."""
    disks = []
    mounts = [("/", "SSD")]
    if os.path.isdir("/host/data"):
        mounts.append(("/host/data", "RAID"))

    for path, label in mounts:
        try:
            usage = shutil.disk_usage(path)
            disks.append({
                "label": label,
                "total_gb": round(usage.total / 1024 / 1024 / 1024, 1),
                "used_gb": round(usage.used / 1024 / 1024 / 1024, 1),
                "percent": round(usage.used / usage.total * 100, 1),
            })
        except Exception as exc:
            logger.warning("Failed to get disk usage for %s: %s", path, exc)

    return disks


def generate_report() -> str:
    """Generate the daily report as a plain-text string."""
    now = datetime.now(timezone.utc)
    lines = [f"Aspirant Daily Report - {now.strftime('%Y-%m-%d')}", ""]

    # System section
    lines.append("System")
    lines.append(f"  Uptime:       {get_uptime()}")

    load = get_load_average()
    if load["load_1m"] is not None:
        lines.append(
            f"  CPU load:     {load['load_1m']} / {load['load_5m']} / {load['load_15m']} (1m / 5m / 15m)"
        )

    mem = get_memory()
    if mem["total_gb"] is not None:
        lines.append(f"  Memory:       {mem['used_gb']} GB / {mem['total_gb']} GB ({mem['percent']}%)")

    for disk in _collect_disk_info():
        lines.append(
            f"  Disk ({disk['label']}):  {disk['used_gb']} GB / {disk['total_gb']} GB ({disk['percent']}%)"
        )

    temp = get_temperature()
    lines.append(f"  Temperature:  {temp}")
    lines.append("")

    # Containers section
    containers = _collect_container_stats()
    running = sum(1 for c in containers if c["status"] == "running")
    total = len(containers)
    lines.append(f"Containers ({running}/{total} running)")

    if containers:
        # Column widths
        name_w = max(len(c["name"]) for c in containers)
        name_w = max(name_w, 4)  # minimum "NAME"
        lines.append(f"  {'NAME':<{name_w}}  {'STATUS':<10}  {'CPU':>6}  {'MEM':>8}  UPTIME")
        for c in containers:
            lines.append(
                f"  {c['name']:<{name_w}}  {c['status']:<10}  {c['cpu']:>6}  {c['mem']:>8}  {c['uptime']}"
            )

    return "\n".join(lines)


async def send_daily_report():
    """Generate and send the daily health report."""
    logger.info("Generating daily report...")
    report = generate_report()
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    await send_email(f"Aspirant Daily Report - {date_str}", report)
