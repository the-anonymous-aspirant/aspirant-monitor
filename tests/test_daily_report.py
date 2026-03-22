from unittest.mock import patch, MagicMock

from app.daily_report import generate_report


class TestGenerateReport:
    @patch("app.daily_report.get_temperature", return_value="52 C")
    @patch("app.daily_report.get_memory", return_value={"total_gb": 7.8, "used_gb": 3.2, "available_gb": 4.6, "percent": 41.0})
    @patch("app.daily_report.get_load_average", return_value={"load_1m": 0.8, "load_5m": 1.2, "load_15m": 0.9})
    @patch("app.daily_report.get_uptime", return_value="42 days, 3 hours")
    @patch("app.daily_report._collect_disk_info", return_value=[{"label": "SSD", "total_gb": 50.0, "used_gb": 18.4, "percent": 36.8}])
    @patch("app.daily_report._collect_container_stats")
    def test_report_format(self, mock_containers, *_):
        mock_containers.return_value = [
            {"name": "client", "status": "running", "cpu": "0.1%", "mem": "42 MB", "uptime": "12d 4h"},
            {"name": "server", "status": "running", "cpu": "1.2%", "mem": "128 MB", "uptime": "12d 4h"},
        ]

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
