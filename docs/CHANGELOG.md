# Changelog

## Unreleased
- `POST /containers/{name}/start` and `/stop` — a gated admin control over
  which served containers may be started/stopped (system_3 #10491-A /
  #10514). Three layers, each independent: a bearer token (`CONTROL_TOKEN`,
  unset = the endpoints are disabled, same convention as `/report/send`), a
  hard in-code allowlist (`CONTROLLABLE_CONTAINERS`) that refuses a
  disallowed name before any Docker API call goes out — this cell's own
  serving path (server, both client slots, postgres, monitor itself, both
  docker-socket-proxy sidecars) is never on it, regardless of what the proxy
  itself would permit — and a second, write-scoped `docker-socket-proxy`
  sidecar (`DOCKER_SOCKET_WRITE`, compose-side) carrying only
  `ALLOW_START`/`ALLOW_STOP`, no `CONTAINERS`. Uses `docker.APIClient` (low-
  level), not `docker.DockerClient`: the high-level client resolves a
  container via a GET the write-proxy's `CONTAINERS=0` refuses.
- `/containers` reports `disk_mb` per container — the size of its own image,
  joined by the container's full image ID against the same `df()` call
  `/disk` already makes, so two containers sharing one image report the same
  figure rather than double-charging it. `null` when the image ID isn't in
  `df()`'s response, never a false `0`. System_3 task #10496-A1, feeding the
  per-service usage rollup (#10490-C).
- Builds of main's image now run one at a time, and `:latest` and `:main` go
  only on a build of main's current head (`scripts/is-main-head.sh`, unit test
  `sh tests/is_main_head_unit.sh`). Two merges landing seconds apart, or a
  re-run of an older build, can no longer leave `:latest` on an older commit
  for auto-pull to deploy. Test runs are not queued. See system_3 #9984, from
  #9966 (the same guard as aspirant-client #409).
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
