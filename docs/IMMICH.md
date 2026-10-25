# Immich observability

[Dashboard](../services/Immich.json) · [builder](../builders/immich.py) · [collector](../collectors/immich_textfile.py)

Tested with Immich 3.3.5, Grafana 13.0.2 and Prometheus. This dashboard contains 74 data panels, including six inventory trend graphs. Native Immich telemetry alone does not expose the library and complete queue inventory used here.

## Measurements

- Active accounts; active photos/videos; known original size; unique checksum groups and logical size; GIFs, albums, shared person identities, detected faces, external libraries/assets and unexpired public-link records.
- Photo/video counts and sizes by account, with optional account labels. Six trends show media counts/sizes, references versus unique content, and per-account counts/sizes.
- Additions over rolling 24 hours and seven days, plus sizes and per-account additions. These use **asset creation in Immich**, including imports and library discovery. They do not establish the capture date, exact upload device, or original device-upload time.
- All 19 configured Bull queues: active, waiting, prioritized, delayed, failed, completed, paused and waiting for children. Retained queue records are not lifetime counters. Native job success/failure counters provide separate processing trends.
- Missing metadata/preview records, unknown original sizes and trash. A missing preview record can reflect format support or processing state; it alone does not establish a media or backup error.
- PostgreSQL database size, current connections and deadlocks since database statistics reset.
- Docker running/health states, uptime and restarts for server, machine learning, PostgreSQL and Redis. A container without a health check displays **No health check**, not Healthy. Restart counts reset on container recreation.
- Recorded primary/replica/export/cloud/report states and last successes; export errors; verified/pending cloud files; verification/health ages; Dropbox free space; native health issues.
- Native API/worker metrics availability, process CPU/memory, repository operation rate/mean latency, host CPU/memory/swap, filesystem capacity and network/disk traffic.

Inventory history begins when collection is enabled. Existing Prometheus history supplies native resource/job charts; database counts are not backfilled into periods when they were never measured. Known bytes are logical original sizes, not physical NAS usage. Repeated NAS mounts may share one storage pool and must not be summed.

The tested Immich version emits no native HTTP request metrics on its metrics endpoints. Repository calls are labelled as repository calls; they are not presented as HTTP requests. Native repository durations are **milliseconds**. Multi-metric rates preserve the metric name in an operation label before evaluating a subquery, preventing label collisions. Runtime subqueries use a five-minute window with 30-second samples so short automatic windows cannot collapse to a single point.

## Collector and freshness

The Python standard-library collector runs once per minute. It uses a PostgreSQL **READ ONLY** transaction with statement/lock timeouts, fixed Redis read commands and Docker inspection. It reads existing protected backup state. It does not read media contents, run backups, alter database records, mutate queues or send notifications. Filenames, emails, GPS and share keys are never emitted.

Inventory, queues, backup state and containers commit independently. A failed component omits its data and emits success=0 without advancing its success timestamp. Instant panels require success=1 and a successful read within 180 seconds. Graphs retain valid historical samples and show gaps for unavailable collection. Collection-health panels expose failures and age directly. No missing component is converted into a healthy zero.

`include_account_labels` defaults to false. Enabling it publishes account names/IDs and aggregate sizes/counts to the private metrics system. Protect the exporter and Grafana accordingly; keep this endpoint out of public sharing tunnels.

Backup status is reported as recorded. Deferred is distinct from success and failure. Current-source cloud coverage requires complete current-source scope, zero pending files, matching expected/verified counts, zero export errors and a cloud check at least as new as the export. It does not assert that a later, still-unexported upload is already protected. Ages remain visible. Historical cleanup waivers and completed cleanup records are not modified.

## Installation

1. Copy the collector to `/opt/immich-observability/immich_textfile.py` and create a private config from [the example](../collectors/immich-config.example.json). Set the real host, container names and existing backup-state directory. Keep the config mode 600.
2. Choose an existing account permitted to inspect the containers and read the protected backup state. Set `User=` in [the service](../collectors/immich-observability.service) accordingly. **Docker group membership grants powerful host access**; read-only behavior of this script does not restrict that account's Docker permissions.
3. Create `/var/lib/node_exporter/textfile_collector`, writable by that account. Mount/read it through the existing node exporter. With a host root mounted at `/rootfs`, add `--collector.textfile.directory=/rootfs/var/lib/node_exporter/textfile_collector`. Preserve the exporter's other arguments, mounts, CA files and image. Recreate only that exporter without pulling an unrelated image update.
4. Install the service/timer, run `systemd-analyze verify`, then start the service. Require all four `immich_collector_success` values to be 1 and `node_textfile_scrape_error` to be 0. Validate exposition with `promtool check metrics` before enabling the timer.
5. Enable `immich-observability.timer`. The VM runs it independently of an operator's laptop. Leave native backup/report schedules intact.
6. Enable Immich native telemetry and scrape its API/worker ports with `job="immich"`; scrape node exporter with `job="node-exporters"`. Keep all endpoints private. See [Immich monitoring](https://docs.immich.app/features/monitoring/).
7. Import the dashboard and map `DS_PROMETHEUS`. Its host selector comes from `immich_host`. The **All** selection joins host metrics against actual Immich collector hosts, preventing unrelated fleet nodes from appearing.

The collector intentionally fails if the expected database or queue schema changes. Revalidate it after Immich upgrades; do not weaken its failure gates to obtain numbers.

## Regeneration and checks

```sh
python3 builders/immich.py
python3 -m unittest discover -s collectors -v
python3 -m unittest discover -s tests -v
promtool test rules tests/immich-promql.test.yml
```

The synthetic PromQL checks verify duplicate-count arithmetic, exclusion of unrelated hosts under All, and omission of failed/stale collection. They contain no production inventory.
