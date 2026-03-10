def test_health_docker_connected(client, mock_docker):
    mock_docker.ping.return_value = True
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["docker_connected"] is True
    assert data["service"] == "monitor"


def test_health_docker_disconnected(client, mock_docker):
    from docker.errors import DockerException

    mock_docker.ping.side_effect = DockerException("connection refused")
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "degraded"
    assert data["docker_connected"] is False
