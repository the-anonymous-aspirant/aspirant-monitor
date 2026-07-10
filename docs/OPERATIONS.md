# Monitor Operations

## Running Locally

```bash
# Create virtual environment and install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run (requires Docker socket access)
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Run tests
pytest tests/ -v
```

## Docker

```bash
# Build
docker build -t aspirant-monitor .

# Run (must mount Docker socket)
docker run -p 8085:8000 -v /var/run/docker.sock:/var/run/docker.sock:ro aspirant-monitor
```

## Endpoints

```bash
# Health check
curl http://localhost:8085/health

# Container stats
curl http://localhost:8085/containers

# Disk and volume info
curl http://localhost:8085/disk
```

## Troubleshooting

### Docker socket permission denied
Ensure the container user has access to `/var/run/docker.sock`. On Linux, the container user may need to be in the `docker` group.

### Empty container stats
Container stats are only available for running containers. Stopped containers will show `null` for CPU, memory, and network fields.

### Daily report says "Monitor blind"
The daily report fails **CLOSED** on Docker-socket blindness. When `DOCKER_SOCKET`
is unreachable (e.g. the `docker-socket-proxy` sidecar has crashed) OR when
fewer than `MIN_EXPECTED_CONTAINERS` containers are visible, the report
banner turns RED with a "Monitor blind" alert rather than silently reporting
"All systems healthy" with `Containers (0/0 running)`.

To resolve:
- Verify the docker-socket-proxy is reachable from the monitor: `docker exec aspirant-monitor curl -sf http://docker-socket-proxy:2375/_ping`.
- Confirm the socket proxy container is running: `docker ps --filter name=docker-socket-proxy`.
- If the proxy crashed, restart it: `docker compose up -d docker-socket-proxy`.
- Tune the floor with `MIN_EXPECTED_CONTAINERS` (default `1`) if the deployed
  stack expects more than one container to be running at all times.

Rationale: a monitor that reports green while blind is worse than no monitor
at all — the 2026-07-09 daily report showed "All systems healthy" for ~2 days
while the docker-socket-proxy was down. See task #1875.
