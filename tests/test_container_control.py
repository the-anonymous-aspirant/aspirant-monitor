"""POST /containers/{name}/start and /stop (system_3 #10491-A / #10514): a
gated admin control over which served containers may be started/stopped --
never this cell's own infrastructure, regardless of what the write-scoped
docker-socket-proxy itself would permit (it has no name filter of its own).
Same bearer-token shape as /report/send, a distinct secret."""

from unittest.mock import patch

import pytest
from docker.errors import APIError, NotFound

from app import config

TOKEN = "control-test-token-0123456789"
OK = {"Authorization": f"Bearer {TOKEN}"}
ALLOWED = "aspirant-online-browser-1"
DISALLOWED = "aspirant-online-postgres-1"  # not in CONTROLLABLE_CONTAINERS


@pytest.fixture
def control_enabled():
    with patch.object(config, "CONTROL_TOKEN", TOKEN), patch.object(
        config, "DOCKER_SOCKET_WRITE", "tcp://docker-socket-proxy-write:2375"
    ):
        yield


@pytest.mark.parametrize("action", ["start", "stop"])
def test_disabled_when_token_unset(client, control_enabled, mock_write_docker, action):
    with patch.object(config, "CONTROL_TOKEN", ""):
        resp = client.post(f"/containers/{ALLOWED}/{action}", headers=OK)
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "control_disabled"
    mock_write_docker.start.assert_not_called()
    mock_write_docker.stop.assert_not_called()


@pytest.mark.parametrize("action", ["start", "stop"])
def test_disabled_when_socket_unset(client, mock_write_docker, action):
    with patch.object(config, "CONTROL_TOKEN", TOKEN), patch.object(config, "DOCKER_SOCKET_WRITE", ""):
        resp = client.post(f"/containers/{ALLOWED}/{action}", headers=OK)
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "control_disabled"


@pytest.mark.parametrize("action", ["start", "stop"])
def test_missing_and_wrong_token_are_refused_alike(client, control_enabled, mock_write_docker, action):
    missing = client.post(f"/containers/{ALLOWED}/{action}")
    wrong = client.post(f"/containers/{ALLOWED}/{action}", headers={"Authorization": "Bearer nope"})
    basic = client.post(f"/containers/{ALLOWED}/{action}", headers={"Authorization": f"Basic {TOKEN}"})
    for resp in (missing, wrong, basic):
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "unauthorized"
    mock_write_docker.start.assert_not_called()
    mock_write_docker.stop.assert_not_called()


@pytest.mark.parametrize("action", ["start", "stop"])
def test_disallowed_name_is_refused_before_any_docker_call(client, control_enabled, mock_write_docker, action):
    resp = client.post(f"/containers/{DISALLOWED}/{action}", headers=OK)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "not_controllable"
    mock_write_docker.start.assert_not_called()
    mock_write_docker.stop.assert_not_called()


def test_own_infrastructure_is_never_on_the_allowlist():
    # The exact property the allowlist exists to guarantee, checked directly
    # against the live set rather than one spot-checked name.
    never = {
        "aspirant-online-server-1",
        "aspirant-online-client-blue-1",
        "aspirant-online-client-green-1",
        "aspirant-online-postgres-1",
        "aspirant-online-monitor-1",
        "aspirant-online-docker-socket-proxy-1",
        "aspirant-online-docker-socket-proxy-write-1",
        "system_3-postgres-1",
        "system_3-test-postgres-1",
        "commander-test-pg5907",
    }
    assert never.isdisjoint(config.CONTROLLABLE_CONTAINERS)


def test_start_happy_path(client, control_enabled, mock_write_docker):
    resp = client.post(f"/containers/{ALLOWED}/start", headers=OK)
    assert resp.status_code == 202
    assert resp.json() == {"name": ALLOWED, "action": "start", "accepted": True}
    mock_write_docker.start.assert_called_once_with(container=ALLOWED)


def test_stop_happy_path(client, control_enabled, mock_write_docker):
    resp = client.post(f"/containers/{ALLOWED}/stop", headers=OK)
    assert resp.status_code == 202
    assert resp.json() == {"name": ALLOWED, "action": "stop", "accepted": True}
    mock_write_docker.stop.assert_called_once_with(container=ALLOWED)


@pytest.mark.parametrize("action", ["start", "stop"])
def test_not_found_is_404(client, control_enabled, mock_write_docker, action):
    getattr(mock_write_docker, action).side_effect = NotFound("no such container")
    resp = client.post(f"/containers/{ALLOWED}/{action}", headers=OK)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


@pytest.mark.parametrize("action", ["start", "stop"])
def test_docker_api_error_is_502(client, control_enabled, mock_write_docker, action):
    getattr(mock_write_docker, action).side_effect = APIError("boom")
    resp = client.post(f"/containers/{ALLOWED}/{action}", headers=OK)
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "docker_error"


def test_write_client_is_a_separate_low_level_client_against_the_write_socket():
    # The exact property #10514's design comment promises: a low-level
    # APIClient (no prior GET to resolve the container, which the write-
    # scoped proxy's CONTAINERS=0 would refuse), pointed at
    # DOCKER_SOCKET_WRITE, never DOCKER_SOCKET.
    import docker

    from app.routes import _get_write_client

    with patch.object(config, "DOCKER_SOCKET_WRITE", "tcp://docker-socket-proxy-write:2375"), patch(
        "docker.APIClient"
    ) as mock_cls:
        _get_write_client()
        mock_cls.assert_called_once_with(base_url="tcp://docker-socket-proxy-write:2375")
    assert docker.APIClient is not docker.DockerClient
