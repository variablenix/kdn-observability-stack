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
