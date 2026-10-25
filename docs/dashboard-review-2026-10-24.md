# Dashboard review — 2026-10-24 Pacific

The [later follow-up](dashboard-followup-2026-10-24.md) resolves the remaining unsupported/empty panels. Results below describe the earlier pass.

## Verified result

Reviewed **32 saved dashboards in seven folders**. Applied fixes or missing-data explanations to 25 dashboards across Services, Infrastructure, Containers, Network, Personal and Security. The other dashboards' working queries were retained. Existing CrowdSec provisioning changes were reconciled from the current source rather than overwritten with an older export.

The final backend audit covered **832 target-bearing panels** using each dashboard's applicable range, including the 30-day Garmin view. At 17:25 PDT, results: **789 returned numeric/text data, 43 had no observations, zero query errors**. All **74 Immich panels** returned data, including its six inventory trends and the two repaired runtime charts. These counts describe query results, not proof that every visualization or underlying service is defect-free. Desktop Immich rendering was inspected; exhaustive visual checks of every panel and mobile layouts were not performed.

## Repairs

| Area | Change |
| --- | --- |
| Immich | Added private aggregate collection and full inventory, account, addition, queue, database, container, backup/cloud and storage views; added six inventory graphs. Replaced absent HTTP metrics with accurately named repository metrics. Fixed short-window subqueries, duplicate arithmetic and All-host scoping. |
| InfluxDB / Docker / Telegraf | Added a separate read-only Flux connection, preserving Garmin's InfluxQL connection. Rebound Flux queries, corrected the Grafana host selection and removed a saved historical absolute range. Host OS panels use the measured host exporter where containerized Telegraf does not emit the requested input. |
| Speedtest | Repaired the invalid integration credential and missing destination bucket. Restored **2,707 completed stored results** through the application's point builder. Separate bucket-scoped application write and Grafana read credentials are private. No new bandwidth test was launched. |
| Proxmox | Populated the instance selector and used native CPU ratio directly, without dividing it again by vCPU count. |
| macOS | Matched the deployed exporter job and populated the selectors from current scrape targets. |
| Authentik | Corrected Prometheus targets bound to InfluxQL; replaced removed task metrics and unused LDAP panels with current task/request measurements. Units and rate labels match their actual meaning. |
| CUPS | Corrected a stale individual socket bind after CUPS replaced the socket. The exporter now mounts the socket directory read-only; scheduler collection recovered. Completed jobs are labelled retained records, not lifetime totals. |
| GoBot | Recovered the configured private stats listener and ordered startup after its WireGuard interface. The configured GoBot target remains distinct from the Soju aggregate exporter; no public listener was added. |
| Soju | Added the missing scrape for its existing private aggregate collector. Configured/connected network and saved/joined channel panels now receive fresh data. |
| Node exporter | Enabled process counts on the required hosts; replaced unavailable detailed IRQ data with collected aggregate interrupt rate. |
| UniFi | Fixed the Now panel's missing data source and the All-ports regex selection. |

## Intentionally absent observations

The 43 nonnumeric panels include Garmin activity/GPS/weight/optional sensor data not recorded in the selected period, optional VM hardware/systemd/TCP detail, unexposed Actions/DPI/scan-age metrics, no matching camera clients/container states, no retry/error/alert events and production maintenance records that have not been recorded. Panels explain these conditions. We did **not** fabricate zeros, enable unrelated integrations, simulate events, start upgrade/rollback actions or claim missing history exists.

Scrape health is separate from application/collector health. For example, a reachable CUPS exporter can still report CUPS unavailable, and an empty failed-event series does not establish complete coverage of all possible errors.

## Persistence and publication

- Protected Grafana database and affected configuration backups were taken before changes.
- Dashboard updates are file-provisioned into the existing folders and UIDs. Existing CrowdSec and Soju providers were preserved. UI edits are allowed, but a later source-file change can overwrite them; maintain the source too.
- Relevant Dockhand saved Compose files were synchronized with the deployed node-exporter, Grafana provisioning mount and CUPS changes, preserving CA mounts and other services. Immich was not restarted.
- Native timers collect Immich statistics independently of the laptop. Native backup, report, sharing and music schedules were not changed.
- Keep the separate `soju-admin` scrape when rendering Prometheus configuration from external automation. The sanitized [scrape examples](../provisioning/metrics-jobs.example.yaml) distinguish it from native Soju and GoBot. The external automation repository is not part of this publication.
- All 32 dashboard exports in this repository use portable data-source inputs and sanitized example addresses/selections. Private deployment config, tokens, actual account values, metrics samples and screenshots are excluded.

## Recheck

```sh
python3 -m unittest discover -s collectors -v
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s security -v
python3 security/build_crowdsec.py --check
promtool test rules tests/immich-promql.test.yml
```

[Audit tool](../tools/audit_dashboards.py) reads live saved models and data-source bindings through Grafana's API using an existing read-capable credential from environment variables. It reports per-query finite/text counts and errors without storing raw metric values or query bodies. The output is private and does not replace browser verification. Do not commit it without review.

```sh
# Supply GRAFANA_TOKEN, or GRAFANA_USER and GRAFANA_PASSWORD, privately.
python3 tools/audit_dashboards.py --url https://grafana.example.net --output audit-private.json
```

The audit uses five-minute rate windows; UI behavior at other intervals must still be checked. The repaired Immich runtime subqueries explicitly use a safe five-minute window.

Verification passed: 25 Python regression checks (collector, dashboard/export/audit and CrowdSec), three synthetic PromQL cases, Prometheus configuration validation, collector exposition validation, and systemd unit validation. A separate run of the published audit tool against the live API exited successfully. Observation counts can change as activity occurs or the selected range moves.
