# aspirant-monitor

System metrics sidecar for the Aspirant platform. Exposes container stats, disk usage, and volume information via REST API by reading from the Docker socket.

## Quick Start

```bash
docker build -f Dockerfile-Monitor -t aspirant-monitor .
docker run -v /var/run/docker.sock:/var/run/docker.sock -p 8085:8000 aspirant-monitor
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check with Docker connectivity status |
| `/containers` | GET | List all containers with CPU, memory, network stats |
| `/disk` | GET | Filesystem usage, Docker volumes, and image summary |

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MONITOR_VERSION` | `0.1.0` | Reported version in health endpoint |
| `DOCKER_SOCKET` | `unix:///var/run/docker.sock` | Docker socket path |

## Testing

```bash
pip install -r requirements.txt
pytest tests/ -v
```

## Architecture

See [docs/](docs/) for detailed documentation:

- [ARCHITECTURE.md](docs/ARCHITECTURE.md) - Data flow and design rationale
- [SPEC.md](docs/SPEC.md) - API specification
- [OPERATIONS.md](docs/OPERATIONS.md) - Operational guide
- [DECISIONS.md](docs/DECISIONS.md) - Architecture decision records
- [CHANGELOG.md](docs/CHANGELOG.md) - Version history
