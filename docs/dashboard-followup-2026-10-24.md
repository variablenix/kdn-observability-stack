# Remaining panel repairs — October 24, 2026

This follows the [initial review](dashboard-review-2026-10-24.md). Its 832-panel / 43-empty result remains the historical result of that earlier pass.

## Verified result

The follow-up changed **11 dashboards**. A fresh audit of the published models at **20:01 PDT** checked all **32 dashboards / 826 target-bearing panels**: **826 returned data, zero empty panel results, zero query errors**. This includes all 74 Immich panels. The lower total reflects removal of eight unsupported Garmin panels and addition of two explicit freshness cards; the remaining unsupported views were replaced with available measurements.

Counts describe backend query results in the checked selections and ranges, including Garmin's 30-day history. They do not guarantee every target within a panel has samples, every possible host/filter selection has data, or that future outages cannot occur. Timestamp transformations were checked in the browser; a Dockhand overview was also rendered using Grafana's native renderer and inspected. Exhaustive rendering checks of every panel/mobile layout were not performed.

## What changed

| Dashboard | Repair |
| --- | --- |
| Cloudflare Tunnel | Replaces nonexistent heartbeat retries and unused proxy/server latency with connector uptime, descriptor capacity, configuration push outcomes, heap capacity and actual RPC observation counts. Client RPC latency explicitly describes observations **since connector start**, rather than implying new RPCs occur during every rate window. |
| CrowdSec Fleet | Upgrade/rollback cards show a retained timestamp, **No recorded upgrade/rollback**, or **History unavailable / incomplete**. No-event status requires fresh, complete history and a successful scrape. Stale, future-dated, incomplete and down-scrape cases cannot appear as uneventful healthy history. |
| Dockhand | Retains native zero update counts previously discarded by `> 0`. Shows measured fleet state totals separately from running containers per environment. Replaces unexported scan age with images having scan results; zero scanned images does not mean zero vulnerabilities. |
| Garmin | Replaces unsupported workout/GPS, VO2, weight and ConnectIQ watch-charge views with recorded sleep, overnight HRV, breathing, skin-temperature deviation, floors, recovery, movement/rest and sample-coverage trends. Reorganizes the layout. Corrects basal calories to use daily statistics instead of unavailable workout records. |
| Gitea | Replaces the unexported Actions count with native project inventory. |
| Graylog | Replaces unexported scheduler failures with measured failure-queue depth. Scopes process/JVM and Graylog queries to the Graylog job so shared metric names cannot mix unrelated services. |
| Navidrome | Shows observed scan outcomes in the selected range, instead of requiring a failure label that has never been emitted. |
| NetBox | Replaces absent query-error/cache/5xx views with measured opened database connections, mean database query time and mean response size. Existing connection-error and status-distribution panels remain. |
| Node Exporter Full | Replaces unavailable VM fan/systemd/detail-TCP views with collector health, runnable/blocked processes, established TCP connections, active/passive opens, listen-queue drops and protocol socket usage. Replacements retain selected host/job scope. |
| UniFi Client Insights | Replaces a camera-name convention matching no clients with top ten clients by combined throughput. Wired and wireless scopes remain disjoint and respect site/client/AP/switch filters. |
| UniFi Network Sites | Replaces unavailable DPI categories with measured internet drops for the selected site, independent of LAN/WLAN filtering. |

### Garmin freshness

A watch-upload marker and an actual health sample are different observations. Native importer polling and read-only upstream checks confirmed that newer daily/heart-rate records were unavailable for the dates checked. Redrawing an older sample as today's value would be misleading.

The dashboard now separates **latest recorded watch upload**, **latest heart-rate sample time** and **sample recency**. Cards previously labelled “Today” now say “Latest recorded” or “Recorded.” Freshness cards use a neutral color. Historical samples remain visible in the selected range; missing days remain gaps. New device measurements must be available upstream before they can appear here.

## Reproduction and safeguards

- [supported_panels.py](../builders/supported_panels.py) is an idempotent, offline model transformation. It preserves dashboard UIDs and replacement panel IDs, and has no credentials or deployment access.
- [build_crowdsec.py](../security/build_crowdsec.py) remains the source for all three CrowdSec exports.
- Live changes used existing file provisioning and its authenticated reload endpoint. Existing models/source files were backed up privately, with dashboard version checks before replacement.
- Exports use portable datasource inputs and the [sanitizer](../tools/export_sanitized.py). Private API snapshots, binding maps, device observations and screenshots are excluded from Git.
- No event history, workouts, errors or numeric zeros were synthesized. CrowdSec's `0` and `-1` fallbacks are mapped categorical states, not event timestamps or counts. A missing target still displays unavailable.

Checks passed: **33 Python regression checks** (12 dashboard/model, 10 CrowdSec, 11 collector), plus **eight synthetic maintenance-history PromQL cases** using the running Prometheus `promtool`. The earlier three Immich PromQL cases were unchanged. The final Dockhand fleet-total refinement was separately queried after the full audit.

```sh
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s security -v
python3 -m unittest discover -s collectors -v
python3 security/build_crowdsec.py --check
promtool test rules tests/crowdsec-history-promql.test.yml
```

Use [audit_dashboards.py](../tools/audit_dashboards.py) with existing Grafana credentials to repeat the backend audit. Do not publish private audit snapshots or authentication material.
