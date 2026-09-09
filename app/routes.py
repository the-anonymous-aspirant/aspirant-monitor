import logging
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import docker
from docker.errors import DockerException
from fastapi import APIRouter
from starlette.responses import JSONResponse

from app.config import DOCKER_SOCKET, MONITOR_VERSION, SERVICE_NAME
from app.scheduler import get_scheduler_status
from app.daily_report import generate_report

logger = logging.getLogger(__name__)
router = APIRouter()

# Docker's `stats?stream=False` samples twice to compute a CPU delta, so each
# call costs ~2s at the docker-socket-proxy regardless of container size —
# unavoidable per call, but fetching them one after another turned a 25-
# container host into a 49s response (#5618). Cap concurrency rather than
# spawning one thread per container so a much larger host doesn't open an
# unbounded number of connections through the proxy in one request.
_MAX_STATS_WORKERS = 25

_EMPTY_STATS = {
    "cpu_percent": None,
    "memory_usage_mb": None,
    "memory_limit_mb": None,
    "memory_percent": None,
    "network_rx_mb": None,
    "network_tx_mb": None,
}


def _stats_for_running_container(container) -> dict:
    """Fetch and compute the stats block for one running container.

    Same computation the route used to run inline, unchanged — only
    extracted so it can be dispatched to a thread pool instead of a serial
    for-loop.
    """
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
            cpu_percent = round((cpu_delta / system_delta) * online_cpus * 100, 2)
        else:
            cpu_percent = 0.0

        # Memory
        mem_stats = stats.get("memory_stats", {})
        mem_usage = mem_stats.get("usage", 0)
        mem_limit = mem_stats.get("limit", 0)
        cache = mem_stats.get("stats", {}).get("cache", 0)
        mem_used = mem_usage - cache
        memory_percent = round(mem_used / mem_limit * 100, 1) if mem_limit > 0 else 0.0

        # Network I/O
        networks = stats.get("networks", {})
        rx = sum(n.get("rx_bytes", 0) for n in networks.values())
        tx = sum(n.get("tx_bytes", 0) for n in networks.values())

        return {
            "cpu_percent": cpu_percent,
            "memory_usage_mb": round(mem_used / 1024 / 1024, 1),
            "memory_limit_mb": round(mem_limit / 1024 / 1024, 1),
            "memory_percent": memory_percent,
            "network_rx_mb": round(rx / 1024 / 1024, 2),
            "network_tx_mb": round(tx / 1024 / 1024, 2),
        }
    except Exception as exc:
        logger.warning("Failed to get stats for %s: %s", container.name, exc)
        return dict(_EMPTY_STATS)


def _get_client():
    return docker.DockerClient(base_url=DOCKER_SOCKET)


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
    running = []  # (index into results, container) for running containers
    for container in client.containers.list(all=True):
        info = {
            "name": container.name,
            # Read the image name from the container's own inspect data
            # (Config.Image), NOT container.image.tags: the latter triggers a
            # GET /images/<id>/json against the docker-socket-proxy, which does
            # not allowlist the images endpoint and returns 403 — taking the
            # whole /containers route to a 500 and blinding container liveness
            # (#5546). Config.Image carries the same tag with no extra API call.
            "image": container.attrs.get("Config", {}).get("Image")
            or container.attrs.get("Image", "")[:12],
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

        if container.status == "running":
            running.append((len(results), container))
        else:
            info.update(_EMPTY_STATS)

        results.append(info)

    # Fetch stats for every running container concurrently instead of one
    # at a time — each `stats(stream=False)` call costs ~2s regardless, so a
    # serial loop over N containers took ~2s*N (49s for 25 containers, #5618).
    if running:
        max_workers = min(len(running), _MAX_STATS_WORKERS)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            stats_blocks = executor.map(
                _stats_for_running_container, (c for _, c in running)
            )
            for (idx, _container), stats_block in zip(running, stats_blocks):
                results[idx].update(stats_block)

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

    # Docker named volumes
    volumes = []
    for v in df.get("Volumes", []):
        volumes.append({
            "name": v.get("Name", ""),
            "size_mb": round(v.get("UsageData", {}).get("Size", 0) / 1024 / 1024, 1),
            "ref_count": v.get("UsageData", {}).get("RefCount", 0),
        })

    # Bind mount directories on /data/aspirant (visible at /host/data/aspirant)
    bind_base = "/host/data/aspirant"
    if os.path.isdir(bind_base):
        for name in sorted(os.listdir(bind_base)):
            dirpath = os.path.join(bind_base, name)
            if os.path.isdir(dirpath):
                total = 0
                for root, _dirs, files in os.walk(dirpath):
                    total += sum(
                        os.path.getsize(os.path.join(root, f))
                        for f in files
                        if os.path.isfile(os.path.join(root, f))
                    )
                volumes.append({
                    "name": f"/data/aspirant/{name}",
                    "size_mb": round(total / 1024 / 1024, 1),
                    "ref_count": -1,
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


@router.get("/report/status")
def report_status():
    return get_scheduler_status()


@router.get("/report/preview")
def report_preview():
    return {"report": generate_report()}
