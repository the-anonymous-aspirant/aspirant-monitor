from unittest.mock import MagicMock
from docker.errors import DockerException


def _make_container(name, status="running", image_tags=None):
    c = MagicMock()
    c.name = name
    c.status = status
    c.image.tags = image_tags or [f"ghcr.io/test/{name}:latest"]
    c.attrs = {
        "Image": "sha256:abc123",
        "State": {
            "Status": status,
            "StartedAt": "2026-01-01T00:00:00Z",
        },
    }
    c.stats.return_value = {
        "cpu_stats": {
            "cpu_usage": {"total_usage": 200},
            "system_cpu_usage": 10000,
            "online_cpus": 2,
        },
        "precpu_stats": {
            "cpu_usage": {"total_usage": 100},
            "system_cpu_usage": 9000,
        },
        "memory_stats": {
            "usage": 50 * 1024 * 1024,
            "limit": 2048 * 1024 * 1024,
            "stats": {"cache": 0},
        },
        "networks": {
            "eth0": {"rx_bytes": 1024 * 1024, "tx_bytes": 512 * 1024}
        },
    }
    return c


def test_containers_list(client, mock_docker):
    mock_docker.containers.list.return_value = [
        _make_container("server"),
        _make_container("postgres"),
    ]
    resp = client.get("/containers")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["containers"]) == 2
    names = [c["name"] for c in data["containers"]]
    assert "server" in names


def test_containers_includes_stats(client, mock_docker):
    mock_docker.containers.list.return_value = [_make_container("server")]
    resp = client.get("/containers")
    container = resp.json()["containers"][0]
    assert container["cpu_percent"] is not None
    assert container["memory_usage_mb"] is not None
    assert container["network_rx_mb"] is not None


def test_containers_stopped(client, mock_docker):
    mock_docker.containers.list.return_value = [
        _make_container("stopped-svc", status="exited")
    ]
    resp = client.get("/containers")
    container = resp.json()["containers"][0]
    assert container["cpu_percent"] is None
    assert container["memory_usage_mb"] is None


def test_containers_docker_unavailable(client, mock_docker):
    from app.routes import _get_client
    from unittest.mock import patch

    with patch("app.routes._get_client", side_effect=DockerException("gone")):
        resp = client.get("/containers")
    assert resp.status_code == 503
