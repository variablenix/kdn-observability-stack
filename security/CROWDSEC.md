# CrowdSec dashboards

Three complementary dashboards share a portable Prometheus datasource selector,
an Engine host selector populated from `up` (including failed targets), and links
to each other. Their existing UIDs remain stable.

| Dashboard | Focus |
| --- | --- |
| CrowdSec Fleet | Current agent/bouncer health, CAPI proof age, Cloudflare freshness and saved retry, home exemptions, HTTP gateway sync, central decisions and engine availability |
| CrowdSec Metrics | File **and Docker** acquisition, parser lines versus node traversal, allowlists, scenario lifecycle, central API rates/latency and process resources |
| Crowdsec Insights | Selected-range workload/scenario rankings, parsing trends, telemetry sample coverage, scrape reliability, versions and decision context |

Native metrics use `crowdsec` for the central LAPI and `crowdsec-agents` for
agents, with a `hostname` label. Engine queries honor the host selector; central
API and fleet-health queries intentionally do not. Scrapes are expected every
30 seconds. Rates use `$__rate_interval`; reset-aware range estimates use
`increase(...[$__range])`. Adjust the sample-coverage denominator for a different
scrape cadence. Grafana's datasource interval must also reflect that cadence.

The optional operational collector exposes `crowdsec_health_*` in job
`crowdsec-health`, and HTTP sync collectors expose
`crowdsec_http_gateway_*` in `crowdsec-http-gateway-health`. Keep endpoints
private. Health results older than 660 seconds are excluded, not colored green.
Without these collectors the corresponding panels display N/A rather than a
fabricated healthy result. All native queries continue to work independently.

The overall status distinguishes **HEALTHY** (all checks passing), amber
**ATTENTION** (freshness/update/verification warnings with core services online),
and red **CRITICAL** (an unhealthy expected agent/bouncer, engine scrape, LAPI or
core collection). Missing/stale evidence remains N/A. Community-list freshness
uses **NEEDS REFRESH**, not a claim that an update is running. Individual failing
checks and their reasons remain visible; no failure is suppressed to make the
overview green. A scheduled quota retry is not a guaranteed upstream reset.

## Nginx gateway maintenance

All three dashboards include current nginx controller/watch status, pending
advisory review, failed automatic transactions and completed production
rollbacks. Fleet adds scheduler/check age, watcher findings, complete-history
status, the latest durable transaction and last verified upgrade/rollback.
The optional read-only `crowdsec_nginx_*` projection is carried by the existing
private `crowdsec-health` job; no extra datasource or public endpoint is needed.
Maintenance warnings add amber ATTENTION to Fleet's overview without relabeling
a core protection outage. Engine host selection does not filter these panels.

**Up to date** is a successful check, not an upgrade. **Review needed** can mean
a changed advisory revision or an out-of-policy image; advisory counts are not
CVE counts. **Waiting for image age** and **Eligible update queued** are update
gates, not deployment failures. **Rolled back** records completed recovery,
not a fixed candidate; **Recovery required** means incomplete rollback. Native
service activity drives **In progress**, not a queued schedule. Same-pin
acceptance/rehearsal/audit runs are validation, not production upgrades.

`crowdsec_nginx_transactions_24h` is a fixed rolling-24-hour **gauge**, independent
of the selected dashboard time range. It counts retained transaction outcomes
by each journal's latest write time, not all phase transitions or every attempt.
Failures before journaling appear only in current status. Completed automatic
rollbacks are also failed transactions; those counts are not additive.
Validation and validation-failure counts remain separate. New-image upgrades
and production rollbacks require automatic mode and a changed image.

Observations expire after 660 seconds with future-time checks; native daily
check evidence expires after 26 hours. Missing last-upgrade/rollback evidence
is N/A when none is retained. Incomplete/unsafe/over-limit history (512 journals,
64 KiB each) makes counts unavailable, never fabricated zeros. Fixed metric
labels contain only category/mode/phase/outcome enums, not image digests, run
IDs, commit hashes, raw errors or credentials. The private email uses the same
reader and can show versions/short digests without exporting them to Prometheus.

Decision records are not necessarily distinct IPs. Retained alert gauges are
database inventory, not new detections in the selected window. API POST/poll
counts are requests, not alerts or blocked traffic. Scenario overflows may
include tests and private-source events. Parser-node nonmatches are not parser
exceptions. Quiet lazy counters can be absent until their first event; N/A is
not proof of broken acquisition or zero activity.

AppSec is not configured in this deployment. Per-IP/country/ASN/service event
details and Cloudflare WAF request/challenge totals are not exported by the
native engine. The dashboards explicitly disclose these gaps rather than
shipping empty AppSec panels or inventing statistics. The private email report
uses LAPI events for source-to-service/host investigations and links back to
these live views. No private telemetry, endpoints or datasource UID is included
in these public exports.

Rebuild and validate after editing the generator:

```sh
python3 security/build_crowdsec.py
python3 security/build_crowdsec.py --check
python3 -m unittest discover -s security -p 'test_crowdsec_dashboards.py'
```

Deployment should use reviewed, commit-pinned files with checksums. Preserve
existing dashboard UIDs, back up the current dashboards privately, and provision
only these three files into the existing security folder. File provisioning can
overwrite later UI edits; make durable changes in the generator and reconverge.
Do not change Grafana authentication or other dashboard providers to deploy them.
