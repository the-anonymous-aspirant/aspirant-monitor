from unittest.mock import MagicMock
from docker.errors import APIError, DockerException


class _ImageProxy403:
    """Stand-in for ``container.image`` that fails the way prod does (#5546).

    Accessing ``.tags`` on a real container issues ``GET /images/<id>/json``
    to the docker-socket-proxy, which does not allowlist the images endpoint
    and returns 403 — so the property raises. The route must read the image
    from ``attrs['Config']['Image']`` and never touch this, so the mock proves
    it by blowing up if it does. Before #5546 the mock set ``.image.tags`` to a
    plain list, which is exactly why the test was green while prod 500'd.
    """

    @property
    def tags(self):
        raise APIError("403 Client Error: Forbidden for /images/<id>/json")


def _make_container(name, status="running", image_name=None, restart_count=0):
    c = MagicMock()
    c.name = name
    c.status = status
    c.image = _ImageProxy403()
    c.attrs = {
        "Image": "sha256:abc123",
        "Config": {"Image": image_name or f"ghcr.io/test/{name}:latest"},
        "RestartCount": restart_count,
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


def test_containers_image_from_attrs_not_images_api(client, mock_docker):
    """Regression for #5546: the image name comes from Config.Image, and the
    route survives container.image raising the proxy's 403. Under the old code
    (container.image.tags) this 500s; the _ImageProxy403 mock makes it bite.
    """
    mock_docker.containers.list.return_value = [
        _make_container("commander", image_name="ghcr.io/x/aspirant-commander:latest")
    ]
    resp = client.get("/containers")
    assert resp.status_code == 200
    assert resp.json()["containers"][0]["image"] == "ghcr.io/x/aspirant-commander:latest"


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


def test_containers_report_restart_count_and_started_at(client, mock_docker):
    """A crash-looping container reads `running` between restarts; the restart
    count and the current run's start are what expose the loop (system_3 #9119)."""
    looping = _make_container("tor", restart_count=1369)
    looping.attrs["State"]["StartedAt"] = "2026-10-29T15:14:14.438722647Z"
    mock_docker.containers.list.return_value = [
        looping,
        _make_container("stopped-svc", status="exited", restart_count=2),
    ]
    resp = client.get("/containers")
    by_name = {c["name"]: c for c in resp.json()["containers"]}
    assert by_name["tor"]["restart_count"] == 1369
    assert by_name["tor"]["started_at"] == "2026-10-29T15:14:14.438722647Z"
    assert by_name["stopped-svc"]["restart_count"] == 2
    assert by_name["stopped-svc"]["started_at"] == "2026-01-01T00:00:00Z"


def test_containers_restart_fields_null_when_docker_omits_them(client, mock_docker):
    c = _make_container("fresh", status="created")
    del c.attrs["RestartCount"]
    c.attrs["State"]["StartedAt"] = ""
    mock_docker.containers.list.return_value = [c]
    container = client.get("/containers").json()["containers"][0]
    assert container["restart_count"] is None
    assert container["started_at"] is None


def test_containers_docker_unavailable(client, mock_docker):
    from app.routes import _get_client
    from unittest.mock import patch

    with patch("app.routes._get_client", side_effect=DockerException("gone")):
        resp = client.get("/containers")
    assert resp.status_code == 503
