from unittest.mock import patch
from docker.errors import DockerException


def test_disk_info(client, mock_docker):
    mock_docker.df.return_value = {
        "Volumes": [
            {
                "Name": "aspirant-online_pgdata",
                "UsageData": {"Size": 150 * 1024 * 1024, "RefCount": 1},
            }
        ],
        "Images": [
            {"Size": 500 * 1024 * 1024},
            {"Size": 300 * 1024 * 1024},
        ],
    }
    resp = client.get("/disk")
    assert resp.status_code == 200
    data = resp.json()
    assert "disk" in data
    assert data["disk"]["total_gb"] > 0
    assert len(data["volumes"]) == 1
    assert data["volumes"][0]["name"] == "aspirant-online_pgdata"
    assert data["images"]["total_count"] == 2


def test_disk_docker_unavailable(client, mock_docker):
    with patch("app.routes._get_client", side_effect=DockerException("gone")):
        resp = client.get("/disk")
    assert resp.status_code == 503
