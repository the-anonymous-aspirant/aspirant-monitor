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
