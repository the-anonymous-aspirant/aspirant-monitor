from unittest.mock import patch, mock_open

from app.system_metrics import get_uptime, get_load_average, get_memory, get_temperature


class TestUptime:
    @patch("builtins.open", mock_open(read_data="123456.78 234567.89\n"))
    def test_uptime_parses_correctly(self):
        with patch("app.system_metrics.HOST_PROC", "/host/proc"):
            result = get_uptime()
        assert "1 days" in result
        assert "10 hours" in result

    @patch("builtins.open", side_effect=FileNotFoundError)
    def test_uptime_unavailable_on_error(self, _):
        assert get_uptime() == "unavailable"


class TestLoadAverage:
    @patch("builtins.open", mock_open(read_data="0.52 0.78 0.91 1/234 5678\n"))
    def test_load_average_parses_correctly(self):
        with patch("app.system_metrics.HOST_PROC", "/host/proc"):
            result = get_load_average()
        assert result["load_1m"] == 0.52
        assert result["load_5m"] == 0.78
        assert result["load_15m"] == 0.91

    @patch("builtins.open", side_effect=FileNotFoundError)
    def test_load_average_returns_none_on_error(self, _):
        result = get_load_average()
        assert result["load_1m"] is None


class TestMemory:
    MEMINFO = (
        "MemTotal:        8000000 kB\n"
        "MemFree:         2000000 kB\n"
        "MemAvailable:    4000000 kB\n"
        "Buffers:          500000 kB\n"
    )

    @patch("builtins.open", mock_open(read_data=MEMINFO))
    def test_memory_parses_correctly(self):
        with patch("app.system_metrics.HOST_PROC", "/host/proc"):
            result = get_memory()
        assert result["total_gb"] == 7.6
        assert result["used_gb"] == 3.8
        assert result["percent"] == 50.0

    @patch("builtins.open", side_effect=FileNotFoundError)
    def test_memory_returns_none_on_error(self, _):
        result = get_memory()
        assert result["total_gb"] is None


class TestTemperature:
    def test_temperature_parses_correctly(self):
        with (
            patch("app.system_metrics.HOST_SYS", "/host/sys"),
            patch("os.path.isfile", return_value=True),
            patch("os.listdir", return_value=["thermal_zone0"]),
            patch("builtins.open", mock_open(read_data="52000\n")),
        ):
            result = get_temperature()
        assert result == "52 C"

    @patch("os.listdir", side_effect=FileNotFoundError)
    def test_temperature_unavailable_on_error(self, _):
        assert get_temperature() == "unavailable"
