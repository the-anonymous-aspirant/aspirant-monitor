# Monitor Architecture

## Overview

```
Browser → Vue Admin (SystemHealth.vue)
  → GET /api/system/containers
  → GET /api/system/disk
  → GET /api/system/db-stats

Go Server (proxy)
  → /system/containers  → monitor:8000/containers
  → /system/disk        → monitor:8000/disk
  → /system/db-stats    → local PostgreSQL query

Monitor Service (FastAPI + Docker SDK)
  → Docker Socket (/var/run/docker.sock)
    → Container stats
    → System df (volumes, images)
    → Disk usage
```

## Data Flow

1. **Container stats**: Docker socket → `container.stats(stream=False)` → CPU/memory/network calculation
2. **Disk usage**: `shutil.disk_usage("/")` for host filesystem, `client.df()` for Docker-managed resources
3. **DB stats**: Server queries PostgreSQL directly via `pg_stat_user_tables` — no monitor involvement

## Docker Socket Access

The monitor container mounts `/var/run/docker.sock` as read-only. This gives it access to:
- List all containers (running and stopped)
- Read container stats (CPU, memory, network I/O)
- Query Docker system information (volumes, images, disk usage)

No write operations are performed through the socket.
