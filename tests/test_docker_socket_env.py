"""DOCKER_SOCKET env var must control the Docker client base_url.

Regression guard for the docker.sock bind-mount removal on aspirant-cell:
the monitor now reaches the Docker API via a socket-proxy sidecar
(tecnativa/docker-socket-proxy) at tcp://docker-socket-proxy:2375.
Hardcoding unix:///var/run/docker.sock re-introduces the container-escape
attack surface.
"""
from unittest.mock import patch


def test_get_client_uses_docker_socket_env(monkeypatch):
    monkeypatch.setenv("DOCKER_SOCKET", "tcp://docker-socket-proxy:2375")

    import importlib
    from app import config, routes
    importlib.reload(config)
    importlib.reload(routes)

    with patch("docker.DockerClient") as mock_ctor:
        routes._get_client()
        mock_ctor.assert_called_once_with(base_url="tcp://docker-socket-proxy:2375")


def test_get_client_defaults_to_unix_socket(monkeypatch):
    monkeypatch.delenv("DOCKER_SOCKET", raising=False)

    import importlib
    from app import config, routes
    importlib.reload(config)
    importlib.reload(routes)

    with patch("docker.DockerClient") as mock_ctor:
        routes._get_client()
        mock_ctor.assert_called_once_with(base_url="unix:///var/run/docker.sock")


def test_daily_report_collect_uses_docker_socket_env(monkeypatch):
    monkeypatch.setenv("DOCKER_SOCKET", "tcp://docker-socket-proxy:2375")

    import importlib
    from app import config, daily_report
    importlib.reload(config)
    importlib.reload(daily_report)

    with patch("docker.DockerClient") as mock_ctor:
        mock_ctor.return_value.containers.list.return_value = []
        daily_report._collect_container_stats()
        mock_ctor.assert_called_once_with(base_url="tcp://docker-socket-proxy:2375")
