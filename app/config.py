import os

SERVICE_NAME = "monitor"
MONITOR_VERSION = os.getenv("MONITOR_VERSION", "0.1.0")
DOCKER_SOCKET = os.getenv("DOCKER_SOCKET", "unix:///var/run/docker.sock")
