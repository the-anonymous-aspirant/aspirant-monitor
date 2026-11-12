import os
from unittest.mock import patch

import pytest
from docker.errors import DockerException

from app import config


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
    assert "disks" in data
    assert len(data["disks"]) >= 1
    assert data["disks"][0]["total_gb"] > 0
    assert len(data["volumes"]) == 1
    assert data["volumes"][0]["name"] == "aspirant-online_pgdata"
    assert data["images"]["total_count"] == 2


def test_disk_docker_unavailable(client, mock_docker):
    with patch("app.routes._get_client", side_effect=DockerException("gone")):
        resp = client.get("/disk")
    assert resp.status_code == 503


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses the chmod 0o000 this test relies on")
def test_disk_unreadable_bind_directory_reported_unreadable(client, mock_docker, tmp_path, monkeypatch):
    mock_docker.df.return_value = {"Volumes": [], "Images": []}
    bind_base = tmp_path / "aspirant"
    bind_base.mkdir()

    readable = bind_base / "readable"
    readable.mkdir()
    (readable / "f.bin").write_bytes(b"x" * (2 * 1024 * 1024))

    blocked = bind_base / "blocked"
    blocked.mkdir()
    (blocked / "inside").mkdir()
    os.chmod(blocked, 0o000)
    monkeypatch.setattr(config, "HOST_DATA", str(tmp_path))
    try:
        resp = client.get("/disk")
    finally:
        os.chmod(blocked, 0o755)  # pytest's own tmp_path cleanup needs to enter it

    assert resp.status_code == 200
    volumes = {v["name"]: v for v in resp.json()["volumes"]}
    assert volumes["/data/aspirant/readable"]["size_mb"] == 2.0
    assert volumes["/data/aspirant/readable"].get("unreadable") is not True

    blocked_volume = volumes["/data/aspirant/blocked"]
    assert blocked_volume["size_mb"] is None
    assert blocked_volume["unreadable"] is True
