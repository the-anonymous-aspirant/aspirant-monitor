import logging
import os
import shutil
from datetime import datetime, timezone

import docker
from docker.errors import DockerException
from fastapi import APIRouter
from starlette.responses import JSONResponse

from app.config import MONITOR_VERSION, SERVICE_NAME

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_client():
    return docker.DockerClient(base_url="unix:///var/run/docker.sock")


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


@router.get("/health")
def health():
    try:
        client = _get_client()
        client.ping()
        docker_ok = True
    except DockerException:
        docker_ok = False

    return {
        "status": "healthy" if docker_ok else "degraded",
        "docker_connected": docker_ok,
        "service": SERVICE_NAME,
        "version": MONITOR_VERSION,
    }


@router.get("/containers")
def containers():
    try:
        client = _get_client()
    except DockerException as exc:
        return _error(503, "docker_unavailable", str(exc))

    results = []
    for container in client.containers.list(all=True):
        info = {
            "name": container.name,
            "image": ",".join(container.image.tags) if container.image.tags else container.attrs["Image"][:12],
            "status": container.status,
            "state": container.attrs["State"]["Status"],
        }

        # Calculate uptime from started_at
        started = container.attrs["State"].get("StartedAt", "")
        if started and container.status == "running":
            try:
                start_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
                delta = datetime.now(timezone.utc) - start_dt
                days = delta.days
                hours, rem = divmod(delta.seconds, 3600)
                minutes = rem // 60
                parts = []
                if days:
                    parts.append(f"{days}d")
                if hours:
                    parts.append(f"{hours}h")
                parts.append(f"{minutes}m")
                info["uptime"] = " ".join(parts)
            except (ValueError, TypeError):
                info["uptime"] = "unknown"
        else:
            info["uptime"] = ""

        # Get live stats for running containers
        if container.status == "running":
            try:
                stats = container.stats(stream=False)

                # CPU percentage
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
                    info["cpu_percent"] = round(
                        (cpu_delta / system_delta) * online_cpus * 100, 2
                    )
                else:
                    info["cpu_percent"] = 0.0

                # Memory
                mem_stats = stats.get("memory_stats", {})
                mem_usage = mem_stats.get("usage", 0)
                mem_limit = mem_stats.get("limit", 0)
                cache = mem_stats.get("stats", {}).get("cache", 0)
                mem_used = mem_usage - cache
                info["memory_usage_mb"] = round(mem_used / 1024 / 1024, 1)
                info["memory_limit_mb"] = round(mem_limit / 1024 / 1024, 1)
                if mem_limit > 0:
                    info["memory_percent"] = round(mem_used / mem_limit * 100, 1)
                else:
                    info["memory_percent"] = 0.0

                # Network I/O
                networks = stats.get("networks", {})
                rx = sum(n.get("rx_bytes", 0) for n in networks.values())
                tx = sum(n.get("tx_bytes", 0) for n in networks.values())
                info["network_rx_mb"] = round(rx / 1024 / 1024, 2)
                info["network_tx_mb"] = round(tx / 1024 / 1024, 2)
            except Exception as exc:
                logger.warning("Failed to get stats for %s: %s", container.name, exc)
                info["cpu_percent"] = None
                info["memory_usage_mb"] = None
                info["memory_limit_mb"] = None
                info["memory_percent"] = None
                info["network_rx_mb"] = None
                info["network_tx_mb"] = None
        else:
            info["cpu_percent"] = None
            info["memory_usage_mb"] = None
            info["memory_limit_mb"] = None
            info["memory_percent"] = None
            info["network_rx_mb"] = None
            info["network_tx_mb"] = None

        results.append(info)

    # Sort: running first, then by name
    results.sort(key=lambda c: (0 if c["status"] == "running" else 1, c["name"]))
    return {"containers": results}


@router.get("/disk")
def disk():
    try:
        client = _get_client()
    except DockerException as exc:
        return _error(503, "docker_unavailable", str(exc))

    # Filesystems: root + any extra mounts (e.g. /host/data for RAID)
    disks = []
    mounts = [("/", "System (SSD)")]
    if os.path.isdir("/host/data"):
        mounts.append(("/host/data", "Data (RAID1)"))

    for path, label in mounts:
        usage = shutil.disk_usage(path)
        disks.append({
            "label": label,
            "mount": path,
            "total_gb": round(usage.total / 1024 / 1024 / 1024, 1),
            "used_gb": round(usage.used / 1024 / 1024 / 1024, 1),
            "free_gb": round(usage.free / 1024 / 1024 / 1024, 1),
            "percent_used": round(usage.used / usage.total * 100, 1),
        })

    # Docker system disk usage (images, containers, volumes)
    try:
        df = client.df()
    except DockerException:
        df = {}

    # Volumes
    volumes = []
    for v in df.get("Volumes", []):
        volumes.append({
            "name": v.get("Name", ""),
            "size_mb": round(v.get("UsageData", {}).get("Size", 0) / 1024 / 1024, 1),
            "ref_count": v.get("UsageData", {}).get("RefCount", 0),
        })
    volumes.sort(key=lambda v: v["size_mb"], reverse=True)

    # Images summary
    images = df.get("Images", [])
    total_image_size = sum(img.get("Size", 0) for img in images)

    return {
        "disks": disks,
        "volumes": volumes,
        "images": {
            "total_count": len(images),
            "total_size_mb": round(total_image_size / 1024 / 1024, 1),
        },
    }
