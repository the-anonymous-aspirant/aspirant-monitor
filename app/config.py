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

# Daily report schedule (hour in CET, 0-23)
DAILY_REPORT_HOUR = int(os.getenv("DAILY_REPORT_HOUR", "8"))

# Host paths for system metrics (mounted read-only from host)
HOST_PROC = os.getenv("HOST_PROC", "/host/proc")
HOST_SYS = os.getenv("HOST_SYS", "/host/sys")


def email_enabled() -> bool:
    return bool(SMTP_HOST and ALERT_EMAIL_TO and ALERT_EMAIL_FROM)
