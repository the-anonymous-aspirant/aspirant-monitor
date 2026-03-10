# Decisions

### Docker SDK over raw socket HTTP

**Context:** The monitor needs to query container stats and system information from the Docker daemon.

**Decision:** Use the official `docker` Python SDK instead of raw HTTP calls to the Unix socket.

**Consequences:**
- Cleaner API for stats calculation (handles JSON parsing, error handling)
- Adds ~5 MB to the image (acceptable for a sidecar)
- Well-maintained library with consistent API across Docker versions

### Sidecar over embedded in server

**Context:** System metrics (container CPU/memory, disk usage) require Docker socket access.

**Decision:** Create a separate sidecar container rather than mounting the Docker socket into the Go server.

**Alternatives considered:**
- Mount Docker socket in Go server (rejected: exposes Docker control to a service that handles user auth and DB)
- SSH from server to host (rejected: complex, requires credentials)
- cAdvisor or Prometheus stack (rejected: over-engineered for a personal project)

**Consequences:**
- Clean separation of concerns
- Only the monitor has Docker socket access
- Server proxies requests, keeping the monitor internal
- Additional container, but lightweight (~50 MB image)
