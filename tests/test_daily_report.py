import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
from docker.errors import DockerException

from app.daily_report import (
    ContainerStats,
    _blindness_alert,
    _build_report,
    _collect_container_stats,
    _status_color,
    generate_report,
    generate_report_html,
    send_daily_report,
    THRESHOLDS,
)


MOCK_CONTAINERS = [
    {"name": "client", "status": "running", "cpu": "0.1%", "mem": "42 MB", "mem_mb": 42.0, "mem_limit_mb": 512.0, "mem_percent": 8.2, "uptime": "12d 4h"},
    {"name": "server", "status": "running", "cpu": "1.2%", "mem": "128 MB", "mem_mb": 128.0, "mem_limit_mb": 512.0, "mem_percent": 25.0, "uptime": "12d 4h"},
]
MOCK_STATS_HEALTHY = ContainerStats(items=MOCK_CONTAINERS, docker_error=None)
MOCK_STATS_EMPTY = ContainerStats(items=[], docker_error=None)

MOCK_METRICS = {
    "temp": "52 C",
    "memory": {"total_gb": 7.8, "used_gb": 3.2, "available_gb": 4.6, "percent": 41.0},
    "load": {"load_1m": 0.8, "load_5m": 1.2, "load_15m": 0.9},
    "uptime": "42 days, 3 hours",
    "disk": [{"label": "SSD", "total_gb": 50.0, "used_gb": 18.4, "percent": 36.8}],
}


def _apply_patches(func):
    """Apply standard metric patches to a test method."""
    patches = [
        patch("app.daily_report.get_temperature", return_value=MOCK_METRICS["temp"]),
        patch("app.daily_report.get_memory", return_value=MOCK_METRICS["memory"]),
        patch("app.daily_report.get_load_average", return_value=MOCK_METRICS["load"]),
        patch("app.daily_report.get_uptime", return_value=MOCK_METRICS["uptime"]),
        patch("app.daily_report._collect_disk_info", return_value=MOCK_METRICS["disk"]),
        patch("app.daily_report._collect_container_stats", return_value=MOCK_STATS_HEALTHY),
    ]
    for p in reversed(patches):
        func = p(func)
    return func


class TestStatusColor:
    def test_green_below_warn(self):
        assert _status_color(1.0, "cpu_load_15m") == "green"

    def test_orange_at_warn(self):
        assert _status_color(2.5, "cpu_load_15m") == "orange"

    def test_red_at_critical(self):
        assert _status_color(4.5, "cpu_load_15m") == "red"

    def test_container_mem_uses_percentage(self):
        assert "container_mem_percent" in THRESHOLDS
        assert "container_mem_mb" not in THRESHOLDS
        # 50% of limit = green
        assert _status_color(50.0, "container_mem_percent") == "green"
        # 80% of limit = orange
        assert _status_color(80.0, "container_mem_percent") == "orange"
        # 95% of limit = red
        assert _status_color(95.0, "container_mem_percent") == "red"

    def test_none_value_returns_green(self):
        assert _status_color(None, "cpu_load_15m") == "green"

    def test_unknown_key_returns_green(self):
        assert _status_color(50, "unknown_metric") == "green"


class TestGenerateReport:
    @_apply_patches
    def test_report_format(self, *_):
        report = generate_report()

        assert "Aspirant Daily Report" in report
        assert "42 days, 3 hours" in report
        assert "0.8 / 1.2 / 0.9" in report
        assert "3.2 GB / 7.8 GB" in report
        assert "18.4 GB / 50.0 GB" in report
        assert "52 C" in report
        assert "Containers (2/2 running)" in report
        assert "client" in report
        assert "server" in report

    @patch("app.daily_report.get_temperature", return_value="unavailable")
    @patch("app.daily_report.get_memory", return_value={"total_gb": None, "used_gb": None, "available_gb": None, "percent": None})
    @patch("app.daily_report.get_load_average", return_value={"load_1m": None, "load_5m": None, "load_15m": None})
    @patch("app.daily_report.get_uptime", return_value="unavailable")
    @patch("app.daily_report._collect_disk_info", return_value=[])
    @patch("app.daily_report._collect_container_stats", return_value=MOCK_STATS_EMPTY)
    def test_report_handles_unavailable_metrics(self, *_):
        report = generate_report()

        assert "Aspirant Daily Report" in report
        assert "unavailable" in report
        assert "Containers (0/0 running)" in report


class TestGenerateReportHtml:
    @_apply_patches
    def test_html_contains_key_sections(self, *_):
        html = generate_report_html()

        assert "<!DOCTYPE html>" in html
        assert "Aspirant Daily Report" in html
        assert "All systems healthy" in html
        assert "42 days, 3 hours" in html
        assert "52 C" in html
        assert "client" in html
        assert "server" in html
        assert "Thresholds" in html

    @_apply_patches
    def test_html_shows_green_for_healthy(self, *_):
        html = generate_report_html()
        assert "#2ecc71" in html  # green dot present

    @patch("app.daily_report.get_temperature", return_value="72 C")
    @patch("app.daily_report.get_memory", return_value={"total_gb": 8.0, "used_gb": 7.5, "available_gb": 0.5, "percent": 93.0})
    @patch("app.daily_report.get_load_average", return_value={"load_1m": 5.0, "load_5m": 4.5, "load_15m": 4.2})
    @patch("app.daily_report.get_uptime", return_value="1 day")
    @patch("app.daily_report._collect_disk_info", return_value=[{"label": "SSD", "total_gb": 50.0, "used_gb": 48.0, "percent": 96.0}])
    @patch("app.daily_report._collect_container_stats", return_value=MOCK_STATS_HEALTHY)
    def test_html_shows_warnings_for_high_values(self, *_):
        html = generate_report_html()
        assert "Needs attention" in html
        assert "#e74c3c" in html or "#f39c12" in html  # red or orange present


class TestReportEndpoints:
    @patch("app.routes.generate_report", return_value="Test report content")
    def test_preview_endpoint(self, _, client):
        response = client.get("/report/preview")
        assert response.status_code == 200
        assert response.json()["report"] == "Test report content"

    def test_status_endpoint(self, client):
        response = client.get("/report/status")
        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data


# --- Regression: fail-CLOSED on Docker blindness (task 1875) -----------------
#
# The 2026-07-09 daily report showed "Containers (0/0 running)" AND "All
# systems healthy" for ~2 days while the docker-socket-proxy was down. Every
# test below guards against that fail-OPEN behaviour re-appearing.


class TestCollectContainerStatsFailsClosed:
    def test_returns_error_string_when_docker_unavailable(self):
        with patch("app.daily_report.docker.DockerClient") as mock_ctor:
            mock_ctor.side_effect = DockerException("connection refused")
            stats = _collect_container_stats()

        assert stats.items == []
        assert stats.docker_error is not None
        assert "connection refused" in stats.docker_error

    def test_returns_error_string_when_ping_fails(self):
        with patch("app.daily_report.docker.DockerClient") as mock_ctor:
            mock_client = MagicMock()
            mock_client.ping.side_effect = DockerException("proxy unreachable")
            mock_ctor.return_value = mock_client
            stats = _collect_container_stats()

        assert stats.items == []
        assert stats.docker_error is not None
        assert "proxy unreachable" in stats.docker_error

    def test_returns_items_when_docker_healthy(self):
        with patch("app.daily_report.docker.DockerClient") as mock_ctor:
            mock_client = MagicMock()
            mock_client.containers.list.return_value = []
            mock_ctor.return_value = mock_client
            stats = _collect_container_stats()

        assert stats.items == []
        assert stats.docker_error is None


class TestBlindnessAlert:
    def test_docker_error_triggers_alert(self):
        stats = ContainerStats(items=[], docker_error="connection refused")
        alert = _blindness_alert(stats)
        assert alert is not None
        assert "MONITOR BLIND" in alert
        assert "connection refused" in alert

    def test_below_min_triggers_alert(self):
        with patch("app.daily_report.MIN_EXPECTED_CONTAINERS", 3):
            stats = ContainerStats(items=[{"name": "only-one"}], docker_error=None)
            alert = _blindness_alert(stats)
        assert alert is not None
        assert "MONITOR BLIND" in alert
        assert "only 1" in alert

    def test_at_or_above_min_no_alert(self):
        with patch("app.daily_report.MIN_EXPECTED_CONTAINERS", 2):
            stats = ContainerStats(items=MOCK_CONTAINERS, docker_error=None)
            alert = _blindness_alert(stats)
        assert alert is None


BLIND_STATS = ContainerStats(items=[], docker_error="proxy unreachable at tcp://docker-socket-proxy:2375")


class TestReportFailsClosedOnBlindness:
    @patch("app.daily_report.get_temperature", return_value=MOCK_METRICS["temp"])
    @patch("app.daily_report.get_memory", return_value=MOCK_METRICS["memory"])
    @patch("app.daily_report.get_load_average", return_value=MOCK_METRICS["load"])
    @patch("app.daily_report.get_uptime", return_value=MOCK_METRICS["uptime"])
    @patch("app.daily_report._collect_disk_info", return_value=MOCK_METRICS["disk"])
    @patch("app.daily_report._collect_container_stats", return_value=BLIND_STATS)
    def test_html_shows_critical_banner_when_docker_unreachable(self, *_):
        html = generate_report_html()

        # This is the load-bearing regression assertion: a blind monitor MUST
        # NOT render as green/healthy. See task 1875.
        assert "All systems healthy" not in html
        assert "Monitor blind" in html
        assert "MONITOR BLIND" in html
        assert "proxy unreachable" in html
        assert "#e74c3c" in html  # red banner border

    @patch("app.daily_report.get_temperature", return_value=MOCK_METRICS["temp"])
    @patch("app.daily_report.get_memory", return_value=MOCK_METRICS["memory"])
    @patch("app.daily_report.get_load_average", return_value=MOCK_METRICS["load"])
    @patch("app.daily_report.get_uptime", return_value=MOCK_METRICS["uptime"])
    @patch("app.daily_report._collect_disk_info", return_value=MOCK_METRICS["disk"])
    @patch("app.daily_report._collect_container_stats", return_value=BLIND_STATS)
    def test_text_report_shows_critical_when_docker_unreachable(self, *_):
        report = generate_report()

        assert "[CRITICAL]" in report
        assert "MONITOR BLIND" in report
        assert "proxy unreachable" in report

    @patch("app.daily_report.MIN_EXPECTED_CONTAINERS", 3)
    @patch("app.daily_report.get_temperature", return_value=MOCK_METRICS["temp"])
    @patch("app.daily_report.get_memory", return_value=MOCK_METRICS["memory"])
    @patch("app.daily_report.get_load_average", return_value=MOCK_METRICS["load"])
    @patch("app.daily_report.get_uptime", return_value=MOCK_METRICS["uptime"])
    @patch("app.daily_report._collect_disk_info", return_value=MOCK_METRICS["disk"])
    @patch("app.daily_report._collect_container_stats", return_value=MOCK_STATS_HEALTHY)
    def test_html_fails_closed_when_below_min_expected(self, *_):
        html = generate_report_html()

        assert "All systems healthy" not in html
        assert "Monitor blind" in html
        assert "only 2 containers visible" in html

    @patch("app.daily_report.MIN_EXPECTED_CONTAINERS", 2)
    @patch("app.daily_report.get_temperature", return_value=MOCK_METRICS["temp"])
    @patch("app.daily_report.get_memory", return_value=MOCK_METRICS["memory"])
    @patch("app.daily_report.get_load_average", return_value=MOCK_METRICS["load"])
    @patch("app.daily_report.get_uptime", return_value=MOCK_METRICS["uptime"])
    @patch("app.daily_report._collect_disk_info", return_value=MOCK_METRICS["disk"])
    @patch("app.daily_report._collect_container_stats", return_value=MOCK_STATS_HEALTHY)
    def test_html_healthy_when_count_meets_min(self, *_):
        html = generate_report_html()
        assert "All systems healthy" in html
        assert "Monitor blind" not in html


# --- Regression: event loop blocked ~100s at 06:00Z daily report (task 6621,
# remediated by 6675) ------------------------------------------------------
#
# The daily report ran a serial ~2s-per-container docker stats walk twice
# (once per renderer) directly on the uvicorn event loop, blocking
# `/containers` for ~100s every day. The tests below guard the fix: stats are
# fetched concurrently, collected once, and the whole build runs off-loop.


def _mock_container(
    name,
    cpu_usage=300,
    precpu_usage=100,
    system_usage=2000,
    presystem_usage=1000,
    online_cpus=1,
    mem_usage=100 * 1024 * 1024,
    mem_limit=200 * 1024 * 1024,
    cache=0,
):
    """Build a MagicMock docker container with a realistic `.stats()` payload."""
    container = MagicMock()
    container.name = name
    container.status = "running"
    container.attrs = {"State": {"StartedAt": "2026-01-01T00:00:00.000000000Z"}}
    container.stats.return_value = {
        "cpu_stats": {
            "cpu_usage": {"total_usage": cpu_usage},
            "system_cpu_usage": system_usage,
            "online_cpus": online_cpus,
        },
        "precpu_stats": {
            "cpu_usage": {"total_usage": precpu_usage},
            "system_cpu_usage": presystem_usage,
        },
        "memory_stats": {"usage": mem_usage, "limit": mem_limit, "stats": {"cache": cache}},
    }
    return container


class TestCollectContainerStatsConcurrency:
    def test_computes_correct_stats_per_container(self):
        alpha = _mock_container("alpha", cpu_usage=300, precpu_usage=100, mem_usage=100 * 1024 * 1024, mem_limit=200 * 1024 * 1024)
        beta = _mock_container("beta", cpu_usage=600, precpu_usage=100, mem_usage=150 * 1024 * 1024, mem_limit=200 * 1024 * 1024)

        with patch("app.daily_report.docker.DockerClient") as mock_ctor:
            mock_client = MagicMock()
            mock_client.containers.list.return_value = [alpha, beta]
            mock_ctor.return_value = mock_client
            stats = _collect_container_stats()

        assert stats.docker_error is None
        by_name = {c["name"]: c for c in stats.items}
        # cpu% = (cpu_delta / system_delta) * online_cpus * 100
        assert by_name["alpha"]["cpu"] == "20.0%"  # (200/1000)*1*100
        assert by_name["beta"]["cpu"] == "50.0%"  # (500/1000)*1*100
        assert by_name["alpha"]["mem_mb"] == pytest.approx(100.0)
        assert by_name["beta"]["mem_mb"] == pytest.approx(150.0)

    def test_one_container_stats_failure_does_not_affect_others(self):
        good = _mock_container("good", cpu_usage=300, precpu_usage=100)
        bad = _mock_container("bad")
        bad.stats.side_effect = Exception("stats unavailable")

        with patch("app.daily_report.docker.DockerClient") as mock_ctor:
            mock_client = MagicMock()
            mock_client.containers.list.return_value = [good, bad]
            mock_ctor.return_value = mock_client
            stats = _collect_container_stats()

        by_name = {c["name"]: c for c in stats.items}
        assert by_name["good"]["cpu"] == "20.0%"
        assert by_name["bad"]["cpu"] == "?"
        assert by_name["bad"]["mem_mb"] is None


class TestReportsAcceptPrecollectedStats:
    def test_generate_report_skips_recollection_when_stats_given(self):
        with patch("app.daily_report._collect_container_stats") as mock_collect:
            report = generate_report(MOCK_STATS_HEALTHY)
        mock_collect.assert_not_called()
        assert "client" in report

    def test_generate_report_html_skips_recollection_when_stats_given(self):
        with patch("app.daily_report._collect_container_stats") as mock_collect:
            html = generate_report_html(MOCK_STATS_HEALTHY)
        mock_collect.assert_not_called()
        assert "client" in html


class TestBuildReportSharesOneStatsCollection:
    @patch("app.daily_report.get_temperature", return_value=MOCK_METRICS["temp"])
    @patch("app.daily_report.get_memory", return_value=MOCK_METRICS["memory"])
    @patch("app.daily_report.get_load_average", return_value=MOCK_METRICS["load"])
    @patch("app.daily_report.get_uptime", return_value=MOCK_METRICS["uptime"])
    @patch("app.daily_report._collect_disk_info", return_value=MOCK_METRICS["disk"])
    @patch("app.daily_report._collect_container_stats", return_value=MOCK_STATS_HEALTHY)
    def test_collects_stats_exactly_once_for_both_renderers(self, mock_collect, *_):
        plain, html = _build_report()

        assert mock_collect.call_count == 1
        assert "client" in plain
        assert "client" in html


class TestSendDailyReportRunsOffLoop:
    def test_build_runs_via_asyncio_to_thread(self):
        async def fake_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        with patch("app.daily_report.asyncio.to_thread", side_effect=fake_to_thread) as mock_to_thread, \
             patch("app.daily_report._build_report", return_value=("plain text", "<html></html>")) as mock_build, \
             patch("app.daily_report.send_email", new_callable=AsyncMock) as mock_send_email:
            asyncio.run(send_daily_report())

        mock_to_thread.assert_called_once_with(mock_build)
        mock_send_email.assert_awaited_once()
        _, call_args, call_kwargs = mock_send_email.mock_calls[0]
        assert "plain text" in call_args
        assert call_kwargs.get("html") == "<html></html>"
