# Monitor Service Specification

## Purpose

Lightweight sidecar service that exposes system-level metrics for the Aspirant platform. Two responsibilities:

1. **Metrics API** (existing) — Expose container stats, disk usage, and volume information via REST for the System Health dashboard
2. **Daily report** (new) — Scheduled daily health report email summarizing system state

## Scope

### In scope

- Container metrics for all running services in the Compose stack
- Host disk usage visible from within the container
- Docker volume sizes and image summary
- Host system metrics: CPU load, memory, uptime, temperature (via mounted /proc, /sys)
- Daily health report email (system stats summary)

### Out of scope

- Log aggregation or log forwarding
- Application-level health checks (each service owns its /health endpoint)
- Real-time container alerting (container down/restart detection)
- External heartbeat / dead man's switch (handle separately via host crontab if desired)
- Persistent alert history or alert database
- Web UI for alert configuration (configured via environment variables)
- Metric time-series storage (Netdata already handles real-time charts)

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Service health + Docker socket connectivity |
| `/containers` | GET | Container list with CPU, memory, network stats |
| `/disk` | GET | Disk usage, volume sizes, image summary |
| `/report/status` | GET | Last report timestamp, next scheduled report time |
| `/report/preview` | GET | Generate and return the daily report content without sending email (useful for debugging) |

## Scheduled Tasks

| Task | Interval | Description |
|------|----------|-------------|
| Daily report | Once daily (configurable, default 08:00 CET) | Email a summary of system health: uptime, CPU load, memory, disk, temperature, container status. |

## Daily Report Content

```
Subject: Aspirant Daily Report - {date}

System
  Uptime:       42 days, 3 hours
  CPU load:     0.8 / 1.2 / 0.9 (1m / 5m / 15m)
  Memory:       3.2 GB / 7.8 GB (41%)
  Disk (SSD):   18.4 GB / 50.0 GB (37%)
  Disk (RAID):  412 GB / 1.8 TB (22%)
  Temperature:  52 C

Containers (8/8 running)
  NAME            STATUS    CPU     MEM      UPTIME
  client          running   0.1%    42 MB    12d 4h
  server          running   1.2%    128 MB   12d 4h
  postgres        running   0.8%    256 MB   12d 4h
  monitor         running   0.1%    38 MB    12d 4h
  transcriber     running   0.0%    84 MB    12d 4h
  commander       running   0.0%    52 MB    12d 4h
  translator      running   0.0%    310 MB   12d 4h
  remarkable      running   0.2%    64 MB    12d 4h
```

## Configuration

All via environment variables (12-factor style, consistent with existing config):

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SMTP_HOST` | No | (disabled) | SMTP server hostname |
| `SMTP_PORT` | No | 587 | SMTP port |
| `SMTP_USER` | No | | SMTP username |
| `SMTP_PASSWORD` | No | | SMTP password |
| `ALERT_EMAIL_TO` | No | | Recipient email address |
| `ALERT_EMAIL_FROM` | No | | Sender email address |
| `DAILY_REPORT_HOUR` | No | 8 | Hour (0-23) in CET to send daily report |

If `SMTP_HOST` is not set, the daily report is disabled. The metrics API works regardless.

## Architecture

```
Monitor Service (FastAPI + Docker SDK)
  |
  +-- Metrics API (existing)
  |     GET /health, /containers, /disk
  |     <- called by Go server proxy <- Vue dashboard
  |
  +-- Scheduler (new, runs in-process)
        |
        +-- Daily report task (once daily)
              -> Docker socket: container stats
              -> /proc/loadavg, /proc/meminfo, /proc/uptime
              -> /sys/class/thermal (CPU temperature)
              -> shutil.disk_usage (disk)
              -> Format and send email via SMTP
```

### Host metrics access

The container already mounts `/data:/host/data:ro`. For system metrics, add read-only mounts:

- `/proc:/host/proc:ro` — CPU load, memory, uptime
- `/sys:/host/sys:ro` — CPU temperature

These are standard read-only mounts used by monitoring containers (same pattern as Netdata).

## Non-Functional Requirements

- Stateless: no database, no persistent state
- Read-only Docker socket access (`:ro`)
- Read-only /proc and /sys access (`:ro`)
- Scheduler runs in-process (no external cron, no systemd dependency)
- Graceful degradation: if SMTP fails, log the error and continue; don't crash the metrics API
- All new dependencies must be pure Python (no compiled C extensions, keeps the image small)

## New Dependencies

| Package | Purpose | Size impact |
|---------|---------|-------------|
| `apscheduler` | In-process task scheduler | ~200 KB |
| `aiosmtplib` | Async SMTP client (works with asyncio/FastAPI) | ~50 KB |

No new compiled dependencies. Image size increase: ~1 MB.

## File Structure (after changes)

```
app/
  __init__.py
  config.py          # extended with SMTP and schedule env vars
  main.py            # scheduler setup in lifespan
  routes.py          # existing endpoints + /report/status, /report/preview
  scheduler.py       # NEW: scheduler setup and task registration
  daily_report.py    # NEW: report generation, formatting, and sending
  email.py           # NEW: SMTP email sending utility
  system_metrics.py  # NEW: read /proc, /sys for host metrics
tests/
  test_daily_report.py    # NEW
  test_email.py           # NEW
  test_system_metrics.py  # NEW
```

## Docker Compose Changes (aspirant-deploy)

```yaml
monitor:
  image: ghcr.io/the-anonymous-aspirant/aspirant-monitor:latest
  restart: unless-stopped
  ports:
    - "8085:8000"
  volumes:
    - /var/run/docker.sock:/var/run/docker.sock:ro
    - /data:/host/data:ro
    - /proc:/host/proc:ro    # NEW
    - /sys:/host/sys:ro      # NEW
  environment:               # NEW
    - SMTP_HOST=${SMTP_HOST:-}
    - SMTP_PORT=${SMTP_PORT:-587}
    - SMTP_USER=${SMTP_USER:-}
    - SMTP_PASSWORD=${SMTP_PASSWORD:-}
    - ALERT_EMAIL_TO=${ALERT_EMAIL_TO:-}
    - ALERT_EMAIL_FROM=${ALERT_EMAIL_FROM:-}
    - DAILY_REPORT_HOUR=${DAILY_REPORT_HOUR:-8}
```

## Development Plan

### Phase 1: Foundation
1. Add `apscheduler` and `aiosmtplib` to requirements.txt
2. Extend `app/config.py` with SMTP and schedule env vars
3. Create `app/email.py` — async SMTP send utility
4. Create `app/system_metrics.py` — read /proc, /sys for CPU load, memory, uptime, temperature
5. Create `app/scheduler.py` — APScheduler setup integrated with FastAPI lifespan
6. Verify: scheduler starts and stops cleanly with the app

### Phase 2: Daily report
7. Create `app/daily_report.py` — collect all metrics, format report, send email
8. Register daily report task in scheduler
9. Add `/report/status` and `/report/preview` endpoints
10. Test: mock system metrics and Docker client, verify report format
11. Verify: email report looks correct (manual with real SMTP)

### Phase 3: Integration
12. Update docker-compose.yml and docker-compose.dev.yml with new volumes and env vars
13. Update aspirant-deploy .env.example with new variables
14. Update docs (ARCHITECTURE.md, CHANGELOG.md, README.md, CLAUDE.md)
15. Run full test suite
16. Deploy and verify end-to-end

## Acceptance Criteria

- [ ] Daily report email arrives at configured hour with all system stats
- [ ] Report includes: uptime, CPU load, memory, disk, temperature, all container statuses
- [ ] `/report/preview` returns the report without sending email
- [ ] `/report/status` shows last sent time and next scheduled time
- [ ] Existing /health, /containers, /disk endpoints unchanged
- [ ] Service starts cleanly with no SMTP config (daily report disabled, API works)
- [ ] Scheduler failure does not crash the metrics API
