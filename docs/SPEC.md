# Monitor Service Specification

## Purpose

Lightweight sidecar service that exposes system-level metrics by reading from the Docker socket. Provides container stats (CPU, memory, network), disk usage, and volume information through a REST API.

## Scope

- Container metrics for all running services in the Compose stack
- Host disk usage visible from within the container
- Docker volume sizes and image summary
- No database, no state, no external dependencies beyond the Docker socket

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Service health + Docker socket connectivity |
| `/containers` | GET | Container list with CPU, memory, network stats |
| `/disk` | GET | Disk usage, volume sizes, image summary |

## Architecture

The monitor runs as a sidecar container with read-only access to the Docker socket (`/var/run/docker.sock`). It uses the Docker SDK for Python to query container stats and system information.

The Go server proxies requests to the monitor at `/api/system/*`, keeping the monitor internal to the Docker network.

## Non-Functional Requirements

- Stateless: no database, no persistent storage
- Read-only Docker socket access (`:ro`)
- Lightweight: minimal dependencies (FastAPI + Docker SDK)
- Port: 8085 (external) -> 8000 (internal)
