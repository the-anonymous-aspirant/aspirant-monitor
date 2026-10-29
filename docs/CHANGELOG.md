# Changelog

## Unreleased
- `/containers` reports `restart_count` (docker's policy restarts since the
  container was created) and `started_at` (the current run's start) for every
  container. A crash-looping container reads `running` for most of each cycle,
  so state alone shows it healthy between restarts. Both fields come from the
  inspect data the list already reads, so no new socket-proxy endpoint is
  called. See system_3 task #9119.
- CI publishes `sha-<short7>` image tags alongside `:latest`, via
  `docker/metadata-action@v5` — the same three tag rules aspirant-server,
  -client and -commander already use. system_3's deploy-freshness sweep
  asserts a per-commit tag identity, and a moving `:latest` cannot answer
  "is THIS commit published", so the service read `never published (no image
  for HEAD)` even while its image was fresh. See system_3 task #4039.
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
