# Changelog

## Unreleased
- Daily report fails **CLOSED** on Docker-socket blindness: when the socket
  is unreachable OR fewer than `MIN_EXPECTED_CONTAINERS` (default `1`)
  containers are visible, the banner turns RED with a "Monitor blind" alert
  instead of silently reporting "All systems healthy" with 0/0 running. Adds
  `MIN_EXPECTED_CONTAINERS` env var. See task #1875.

## 0.1.0
- Initial release
- `/health` endpoint with Docker socket connectivity check
- `/containers` endpoint with CPU, memory, network stats
- `/disk` endpoint with host disk usage, volume sizes, image summary
