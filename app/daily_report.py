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

# --- Thresholds ---
# (warn, critical) — None means no threshold for that level
THRESHOLDS = {
    "cpu_load_15m": (2.0, 4.0),
    "memory_percent": (70.0, 90.0),
    "disk_percent": (75.0, 90.0),
    "temperature_c": (65, 80),
    "container_mem_percent": (75.0, 90.0),
}


def _status_color(value, key: str) -> str:
    """Return 'green', 'orange', or 'red' based on threshold for key."""
    if value is None or key not in THRESHOLDS:
        return "green"
    warn, crit = THRESHOLDS[key]
    if value >= crit:
        return "red"
    if value >= warn:
        return "orange"
    return "green"


def _dot(color: str) -> str:
    """Colored status dot for HTML."""
    colors = {"green": "#2ecc71", "orange": "#f39c12", "red": "#e74c3c"}
    hex_color = colors.get(color, colors["green"])
    return f'<span style="color:{hex_color};font-size:18px;">&#9679;</span>'


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
                mem_limit = mem_stats.get("limit", 0)
                cache = mem_stats.get("stats", {}).get("cache", 0)
                mem_used = mem_usage - cache
                mem_mb = mem_used / 1024 / 1024
                mem_limit_mb = mem_limit / 1024 / 1024
                info["mem"] = f"{mem_mb:.0f} MB"
                info["mem_mb"] = mem_mb
                info["mem_limit_mb"] = mem_limit_mb
                if mem_limit > 0:
                    info["mem_percent"] = round(mem_used / mem_limit * 100, 1)
                else:
                    info["mem_percent"] = None
            except Exception:
                info["cpu"] = "?"
                info["mem"] = "?"
                info["mem_mb"] = None
                info["mem_limit_mb"] = None
                info["mem_percent"] = None
        else:
            info["cpu"] = "-"
            info["mem"] = "-"
            info["mem_mb"] = None
            info["mem_limit_mb"] = None
            info["mem_percent"] = None

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
            percent = round(usage.used / usage.total * 100, 1)
            disks.append({
                "label": label,
                "total_gb": round(usage.total / 1024 / 1024 / 1024, 1),
                "used_gb": round(usage.used / 1024 / 1024 / 1024, 1),
                "percent": percent,
            })
        except Exception as exc:
            logger.warning("Failed to get disk usage for %s: %s", path, exc)

    return disks


def _parse_temperature(temp_str: str) -> int | None:
    """Extract numeric temperature from string like '34 C'."""
    if temp_str == "unavailable":
        return None
    try:
        return int(temp_str.split()[0])
    except (ValueError, IndexError):
        return None


def generate_report() -> str:
    """Generate the daily report as a plain-text string (email fallback)."""
    now = datetime.now(timezone.utc)
    lines = [f"Aspirant Daily Report - {now.strftime('%Y-%m-%d')}", ""]

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

    containers = _collect_container_stats()
    running = sum(1 for c in containers if c["status"] == "running")
    total = len(containers)
    lines.append(f"Containers ({running}/{total} running)")

    if containers:
        name_w = max(len(c["name"]) for c in containers)
        name_w = max(name_w, 4)
        lines.append(f"  {'NAME':<{name_w}}  {'STATUS':<10}  {'CPU':>6}  {'MEM':>8}  UPTIME")
        for c in containers:
            lines.append(
                f"  {c['name']:<{name_w}}  {c['status']:<10}  {c['cpu']:>6}  {c['mem']:>8}  {c['uptime']}"
            )

    return "\n".join(lines)


def generate_report_html() -> str:
    """Generate the daily report as styled HTML."""
    now = datetime.now(timezone.utc)

    # Collect all data
    load = get_load_average()
    mem = get_memory()
    disks = _collect_disk_info()
    temp_str = get_temperature()
    temp_c = _parse_temperature(temp_str)
    containers = _collect_container_stats()
    running = sum(1 for c in containers if c["status"] == "running")
    total = len(containers)

    # Determine overall status
    alerts = []
    if load["load_15m"] is not None and _status_color(load["load_15m"], "cpu_load_15m") != "green":
        alerts.append(f"CPU load 15m: {load['load_15m']}")
    if mem["percent"] is not None and _status_color(mem["percent"], "memory_percent") != "green":
        alerts.append(f"Memory: {mem['percent']}%")
    for d in disks:
        if _status_color(d["percent"], "disk_percent") != "green":
            alerts.append(f"Disk ({d['label']}): {d['percent']}%")
    if temp_c is not None and _status_color(temp_c, "temperature_c") != "green":
        alerts.append(f"Temperature: {temp_str}")
    not_running = [c for c in containers if c["status"] != "running"]
    for c in not_running:
        alerts.append(f"Container down: {c['name']}")

    if alerts:
        overall_color = "red" if any("down" in a for a in alerts) else "orange"
        banner_bg = "#fdf2f2" if overall_color == "red" else "#fef9e7"
        banner_border = "#e74c3c" if overall_color == "red" else "#f39c12"
        banner_text = "Needs attention"
    else:
        banner_bg = "#eafaf1"
        banner_border = "#2ecc71"
        banner_text = "All systems healthy"

    # --- Build HTML ---
    css = """
    body { font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; color: #2c3e50; margin: 0; padding: 0; background: #f5f6fa; }
    .container { max-width: 640px; margin: 0 auto; background: #fff; }
    .header { background: #2c3e50; color: #ecf0f1; padding: 20px 24px; }
    .header h1 { margin: 0; font-size: 20px; font-weight: 600; }
    .header .date { color: #95a5a6; font-size: 13px; margin-top: 4px; }
    .banner { padding: 12px 24px; border-left: 4px solid; font-size: 14px; font-weight: 600; }
    .section { padding: 16px 24px; }
    .section h2 { font-size: 14px; text-transform: uppercase; color: #7f8c8d; margin: 0 0 12px 0; letter-spacing: 0.5px; }
    .metric-row { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #f0f0f0; font-size: 14px; }
    .metric-label { color: #7f8c8d; }
    .metric-value { font-weight: 600; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th { text-align: left; color: #7f8c8d; font-weight: 600; padding: 8px 6px; border-bottom: 2px solid #ecf0f1; font-size: 11px; text-transform: uppercase; }
    td { padding: 7px 6px; border-bottom: 1px solid #f5f5f5; }
    tr.down td { background: #fdf2f2; }
    .bar-bg { background: #ecf0f1; border-radius: 3px; height: 8px; width: 100px; display: inline-block; vertical-align: middle; }
    .bar-fill { height: 8px; border-radius: 3px; display: inline-block; }
    .footer { padding: 16px 24px; text-align: center; font-size: 12px; color: #95a5a6; border-top: 1px solid #ecf0f1; }
    .alert-item { font-size: 13px; padding: 2px 0; }
    """

    def bar(percent, key):
        color = {"green": "#2ecc71", "orange": "#f39c12", "red": "#e74c3c"}[_status_color(percent, key)]
        w = min(percent, 100)
        return f'<span class="bar-bg"><span class="bar-fill" style="width:{w}%;background:{color};"></span></span> {percent}%'

    html_parts = [f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{css}</style></head><body>
<div class="container">
<div class="header">
    <h1>Aspirant Daily Report</h1>
    <div class="date">{now.strftime('%A, %B %d, %Y')}</div>
</div>
<div class="banner" style="background:{banner_bg};border-color:{banner_border};">
    {_dot("green" if not alerts else ("red" if "down" in str(alerts) else "orange"))} {banner_text}"""]

    if alerts:
        html_parts.append('<div style="margin-top:6px;">')
        for a in alerts:
            html_parts.append(f'<div class="alert-item">{a}</div>')
        html_parts.append('</div>')

    html_parts.append('</div>')

    # System metrics section
    html_parts.append('<div class="section"><h2>System</h2>')

    html_parts.append(f'<div class="metric-row"><span class="metric-label">Uptime</span><span class="metric-value">{get_uptime()}</span></div>')

    if load["load_1m"] is not None:
        load_color = _status_color(load["load_15m"], "cpu_load_15m")
        html_parts.append(f'<div class="metric-row"><span class="metric-label">CPU Load (1m / 5m / 15m)</span><span class="metric-value">{_dot(load_color)} {load["load_1m"]} / {load["load_5m"]} / {load["load_15m"]}</span></div>')

    if mem["total_gb"] is not None:
        html_parts.append(f'<div class="metric-row"><span class="metric-label">Memory</span><span class="metric-value">{mem["used_gb"]} / {mem["total_gb"]} GB &nbsp;{bar(mem["percent"], "memory_percent")}</span></div>')

    for d in disks:
        html_parts.append(f'<div class="metric-row"><span class="metric-label">Disk ({d["label"]})</span><span class="metric-value">{d["used_gb"]} / {d["total_gb"]} GB &nbsp;{bar(d["percent"], "disk_percent")}</span></div>')

    if temp_c is not None:
        temp_color = _status_color(temp_c, "temperature_c")
        html_parts.append(f'<div class="metric-row"><span class="metric-label">Temperature</span><span class="metric-value">{_dot(temp_color)} {temp_str}</span></div>')

    html_parts.append('</div>')

    # Containers section
    html_parts.append(f'<div class="section"><h2>Containers ({running}/{total} running)</h2>')
    html_parts.append('<table><tr><th>Name</th><th>Status</th><th>CPU</th><th>Memory</th><th>Uptime</th></tr>')

    for c in containers:
        # Short name: strip "aspirant-online-" prefix and "-1" suffix
        short = c["name"]
        if short.startswith("aspirant-online-"):
            short = short[len("aspirant-online-"):]
        if short.endswith("-1"):
            short = short[:-2]

        if c["status"] == "running":
            status_dot = _dot("green")
            mem_color = _status_color(c.get("mem_percent"), "container_mem_percent")
            mem_html = f'{_dot(mem_color)} {c["mem"]}'
            row_class = ""
        else:
            status_dot = _dot("red")
            mem_html = "-"
            row_class = ' class="down"'

        html_parts.append(f'<tr{row_class}><td><b>{short}</b></td><td>{status_dot} {c["status"]}</td><td>{c["cpu"]}</td><td>{mem_html}</td><td>{c["uptime"]}</td></tr>')

    html_parts.append('</table></div>')

    # Thresholds reference
    html_parts.append('<div class="section" style="background:#f9f9f9;"><h2>Thresholds</h2>')
    html_parts.append('<table style="font-size:12px;color:#7f8c8d;">')
    html_parts.append('<tr><th>Metric</th><th>Normal</th><th>Warning</th><th>Critical</th></tr>')
    html_parts.append(f'<tr><td>CPU Load (15m)</td><td>&lt; {THRESHOLDS["cpu_load_15m"][0]}</td><td>&ge; {THRESHOLDS["cpu_load_15m"][0]}</td><td>&ge; {THRESHOLDS["cpu_load_15m"][1]}</td></tr>')
    html_parts.append(f'<tr><td>Memory</td><td>&lt; {THRESHOLDS["memory_percent"][0]}%</td><td>&ge; {THRESHOLDS["memory_percent"][0]}%</td><td>&ge; {THRESHOLDS["memory_percent"][1]}%</td></tr>')
    html_parts.append(f'<tr><td>Disk</td><td>&lt; {THRESHOLDS["disk_percent"][0]}%</td><td>&ge; {THRESHOLDS["disk_percent"][0]}%</td><td>&ge; {THRESHOLDS["disk_percent"][1]}%</td></tr>')
    html_parts.append(f'<tr><td>Temperature</td><td>&lt; {THRESHOLDS["temperature_c"][0]} C</td><td>&ge; {THRESHOLDS["temperature_c"][0]} C</td><td>&ge; {THRESHOLDS["temperature_c"][1]} C</td></tr>')
    html_parts.append(f'<tr><td>Container Mem</td><td>&lt; {THRESHOLDS["container_mem_percent"][0]}% of limit</td><td>&ge; {THRESHOLDS["container_mem_percent"][0]}% of limit</td><td>&ge; {THRESHOLDS["container_mem_percent"][1]}% of limit</td></tr>')
    html_parts.append('</table></div>')

    html_parts.append('<div class="footer">aspirant-monitor &middot; aspirant-cell</div>')
    html_parts.append('</div></body></html>')

    return "\n".join(html_parts)


async def send_daily_report():
    """Generate and send the daily health report."""
    logger.info("Generating daily report...")
    plain = generate_report()
    html = generate_report_html()
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    await send_email(f"Aspirant Daily Report - {date_str}", plain, html=html)
