from unittest.mock import patch, MagicMock

from app.daily_report import generate_report, generate_report_html, _status_color, THRESHOLDS


MOCK_CONTAINERS = [
    {"name": "client", "status": "running", "cpu": "0.1%", "mem": "42 MB", "mem_mb": 42.0, "mem_limit_mb": 512.0, "mem_percent": 8.2, "uptime": "12d 4h"},
    {"name": "server", "status": "running", "cpu": "1.2%", "mem": "128 MB", "mem_mb": 128.0, "mem_limit_mb": 512.0, "mem_percent": 25.0, "uptime": "12d 4h"},
]

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
        patch("app.daily_report._collect_container_stats", return_value=MOCK_CONTAINERS),
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
    @patch("app.daily_report._collect_container_stats", return_value=[])
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
    @patch("app.daily_report._collect_container_stats", return_value=MOCK_CONTAINERS)
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
