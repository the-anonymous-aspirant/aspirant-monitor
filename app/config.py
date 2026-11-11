import os

SERVICE_NAME = "monitor"
MONITOR_VERSION = os.getenv("MONITOR_VERSION", "0.2.0")
DOCKER_SOCKET = os.getenv("DOCKER_SOCKET", "unix:///var/run/docker.sock")

# Fail-CLOSED self-check: minimum number of containers the monitor expects to
# see. If fewer are visible (including zero when the Docker socket is
# unreachable), the daily report renders a CRITICAL blindness alert rather
# than falsely reporting "All systems healthy". The monitor itself runs in a
# container, so 1 is a safe floor on the deployed stack.
MIN_EXPECTED_CONTAINERS = int(os.getenv("MIN_EXPECTED_CONTAINERS", "1"))

# SMTP configuration (all optional — if SMTP_HOST is unset, email is disabled)
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
ALERT_EMAIL_TO = os.getenv("ALERT_EMAIL_TO", "")
ALERT_EMAIL_FROM = os.getenv("ALERT_EMAIL_FROM", "")

# Send-report endpoint (system_3 #8739): a bearer token that system_3 presents
# on POST /report/send. Unset = the endpoint is disabled (503), so the route
# does not exist operationally until the operator provisions the secret in the
# cell's .env. The recipient is always ALERT_EMAIL_TO; the caps bound what a
# caller can push through the one configured mailbox.
REPORT_SEND_TOKEN = os.getenv("REPORT_SEND_TOKEN", "")
REPORT_SEND_MAX_REQUEST_BYTES = int(os.getenv("REPORT_SEND_MAX_REQUEST_BYTES", str(64 * 1024)))
REPORT_SEND_MAX_SUBJECT_CHARS = 200
REPORT_SEND_MAX_BODY_BYTES = 16 * 1024
REPORT_SEND_MAX_HTML_BYTES = 48 * 1024

# Container start/stop (system_3 #10491-A / #10514): a second, write-scoped
# docker-socket-proxy sidecar (compose service docker-socket-proxy-write;
# see its own comment for why it is not the same sidecar as DOCKER_SOCKET
# above). Same bearer-token shape as REPORT_SEND_TOKEN just above, but a
# distinct secret and a distinct caller (aspirant-server's admin routes, not
# system_3) -- unset = the endpoints are disabled (503), same convention.
DOCKER_SOCKET_WRITE = os.getenv("DOCKER_SOCKET_WRITE", "")
CONTROL_TOKEN = os.getenv("CONTROL_TOKEN", "")

# The hard allowlist of container names this service will start/stop, no
# matter what the write-proxy itself would permit (it has no name filter of
# its own -- see #10514). Deliberately an allowlist of what MAY be
# controlled, not a denylist of what may not: an unlisted name refuses
# closed. Excludes this cell's own serving path (server, both client
# slots, postgres, monitor itself, both docker-socket-proxy sidecars) --
# stopping any of those would either take down the admin page asking for
# the stop, or the data every other service depends on. Covers the
# services report 877 (system_3 #10306) named as disable-for-now
# candidates, plus their tied dependents.
CONTROLLABLE_CONTAINERS = frozenset(
    {
        "aspirant-online-advisor-1",
        "aspirant-online-browser-1",
        "aspirant-online-tor-1",
        "aspirant-online-translator-1",
        "aspirant-online-transcriber-1",
        "aspirant-online-ollama-1",
        "aspirant-online-penpot-frontend-1",
        "aspirant-online-penpot-backend-1",
        "aspirant-online-penpot-postgres-1",
        "aspirant-online-penpot-redis-1",
        "aspirant-online-penpot-exporter-1",
        "aspirant-online-histoire-1",
        "aspirant-online-explorer-1",
        "aspirant-online-explorer-api-1",
    }
)

# Daily report schedule (hour in CET, 0-23)
DAILY_REPORT_HOUR = int(os.getenv("DAILY_REPORT_HOUR", "8"))

# Host paths for system metrics (mounted read-only from host)
HOST_PROC = os.getenv("HOST_PROC", "/host/proc")
HOST_SYS = os.getenv("HOST_SYS", "/host/sys")


def email_enabled() -> bool:
    return bool(SMTP_HOST and ALERT_EMAIL_TO and ALERT_EMAIL_FROM)
