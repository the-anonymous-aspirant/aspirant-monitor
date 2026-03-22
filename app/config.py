import os

SERVICE_NAME = "monitor"
MONITOR_VERSION = os.getenv("MONITOR_VERSION", "0.2.0")
DOCKER_SOCKET = os.getenv("DOCKER_SOCKET", "unix:///var/run/docker.sock")

# SMTP configuration (all optional — if SMTP_HOST is unset, email is disabled)
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
ALERT_EMAIL_TO = os.getenv("ALERT_EMAIL_TO", "")
ALERT_EMAIL_FROM = os.getenv("ALERT_EMAIL_FROM", "")

# Daily report schedule (hour in CET, 0-23)
DAILY_REPORT_HOUR = int(os.getenv("DAILY_REPORT_HOUR", "8"))

# Host paths for system metrics (mounted read-only from host)
HOST_PROC = os.getenv("HOST_PROC", "/host/proc")
HOST_SYS = os.getenv("HOST_SYS", "/host/sys")


def email_enabled() -> bool:
    return bool(SMTP_HOST and ALERT_EMAIL_TO and ALERT_EMAIL_FROM)
