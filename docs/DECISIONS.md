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

### In-process scheduler over external cron

**Context:** Alerting tasks (heartbeat, container watch, daily report) need to run on a schedule.

**Options considered:**
1. Host crontab — rejected: requires host access, not containerized, adds ops burden
2. Separate scheduler container — rejected: over-engineered, adds another service to monitor
3. APScheduler in-process — chosen: runs inside the existing FastAPI app, no external dependencies

**Decision:** APScheduler with asyncio integration, started/stopped via FastAPI lifespan.

**Consequences:**
- Zero additional containers or host configuration
- Scheduler lifecycle tied to the app (restart app = restart scheduler)
- Alert dedup state lives in-memory (acceptable for this use case)
- Task failures are isolated — a failed email send doesn't crash the API

### SMTP over webhook/push services

**Context:** Need to deliver alerts and reports to the user.

**Options considered:**
1. Slack/Discord webhook — rejected: adds external dependency, not everyone checks these
2. Push notification service — rejected: complex setup, mobile app dependency
3. SMTP email — chosen: universal, reliable, works offline-to-online (queued by provider)

**Decision:** Use `aiosmtplib` for async SMTP, compatible with any provider (Gmail, SendGrid, etc.)

**Consequences:**
- Works with any email provider (Gmail app password is simplest)
- No external API keys beyond SMTP credentials
- Async: doesn't block the FastAPI event loop
- Graceful degradation: if SMTP fails, log and continue

