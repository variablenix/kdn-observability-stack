# 📊 Global Observability Stack (Sanitized)

Welcome to a public collection of monitoring and observability configurations for a production-grade 10+ node Proxmox environment. The dashboards are designed to help operators evaluate infrastructure patterns before they reach production.

### **Why this exists**
The project follows **Infrastructure as Code** practices and treats self-hosted environments with the same rigor as an enterprise data center. It provides a baseline for others building complex self-hosted stacks involving high-speed networking, security meshes, and containerized services.

### **The "Sanitization" Workflow**
For security and privacy, these files have been processed through a sanitization pipeline before being published from an internal **Gitea** instance.
* **Network Masking:** Deployment addresses are replaced with documentation examples or placeholders. New exports use RFC 5737 example addresses.
* **Domain Generalization:** Private service domains are generalized to example domains.
* **Portability:** Deployment-specific data-source UIDs are replaced with import inputs such as `${DS_PROMETHEUS}`. Match the query language and adapt site-specific selectors before use.
* **Secret Management:** Live credentials and private telemetry samples are excluded from publication.

### **What’s Monitored?**
* **Core Infrastructure:** Real-time health of a **10+ node Proxmox cluster** and **Docker-GitOps** workflows.
* **Security & Traffic:** Distributed **CrowdSec** bouncers, **Cloudflare WAF** metrics, and **pfSense** firewall throughput.
* **Identity & Access:** Authentication trends and security events from **Authentik** SSO.
* **Media & Apps:** Uptime and listener metrics for **Lounge24 Radio**, a self-hosted station built on **AzuraCast**.
* **Networking:** 2.5Gbps backbone metrics across **UniFi** and **Netgate** hardware.

### **How to Use These**
These dashboards are exported in standard Grafana JSON format. To import them:
1. Download the JSON file for the service you wish to monitor.
2. In your Grafana instance, go to **Dashboards -> Import**.
3. Upload the JSON and map the `${DS_...}` variables to your local Prometheus, InfluxDB, or OpenSearch data sources.

### pfSense and WireGuard

Import [pfSense - Telegraf](infrastructure/pfSense-Telegraf.json) with Prometheus. Set **pfSense Telegraf host** to the `host` label on your Telegraf metrics. The scrape health card expects the `pfsense` job, and the tunnel traffic panels use `tun_wg0`. Adjust these selectors if yours differ.

The interface, system, and PF counter panels use standard Telegraf metrics. Peer handshakes and transfers, WireGuard interface state, the PF state limit, and WAN probe quality also need a separate collector that reports `wireguard_*` and `pfsense_*` metrics. For those panels, set **Collector server** to the `server` label on the `node-exporters` scrape job. Without those metrics, the corresponding panels show no data.

### pfSense firewall blocks

Import [pfSense — Firewall Blocks](infrastructure/pfSense-Firewall-Blocks.json)
with the Grafana OpenSearch plugin. Bind the Graylog message indexes and use
`timestamp` as the time field. Set **Firewall syslog sender** and **Graylog syslog
input ID** to the values Graylog records for your firewall. The dashboard expects
the original pfSense `filterlog` messages on `local0`.

The logged total and inbound/outbound trend use the raw records. Full-range
rankings and breakdowns require indexed `pfsense_*` fields. These include the IP
family, packet addresses, TCP/UDP destination port, interface, protocol and rule
tracker. **Parsed blocks** shows the coverage of enriched records. The
pfBlockerNG count requires a tracker mapping verified against the active firewall
rules. Trend graphs cover source and destination IPs, destination ports,
interfaces, protocols, rule trackers, IP families, and parsed log coverage.
Recent packets show the latest 100 enriched records. Graylog's existing
retention applies. The dashboard covers firewall rules that log their blocks.

### Graylog

Import [Log Analytics](security/Graylog-Log_Analytics-KDN_Lab.json) with the Grafana OpenSearch plugin. Map the OpenSearch input to your Graylog message indexes with `timestamp` as the time field. Enter your TCP syslog, UDP syslog, and GELF input IDs and your pfSense sender address in the dashboard controls. The fleet host dropdown is populated from the selected TCP syslog input. CrowdSec and Relay panels require their corresponding log records.

Import [Service Health](security/Graylog-KDNLab.json) with Prometheus. It uses the `graylog` scrape job for ingest and journal metrics and the `node-exporters` job for filesystem metrics. Set **Node Exporter instance** and **Graylog data mount** to the labels used by your host. Set **Graylog URL** on both dashboards to enable links into your instance.

### Reviewed dashboards and Immich inventory

See the [dated review](docs/dashboard-review-2026-10-24.md) for measured results and limitations across all 32 dashboards. [Immich](docs/IMMICH.md) now includes 74 data panels, six inventory trend graphs, account counts/sizes, recent additions, queues, containers, database, resources and backup/cloud coverage. Its read-only collector and native systemd timer are included.

The [remaining-panel follow-up](docs/dashboard-followup-2026-10-24.md) repairs or replaces unsupported views in 11 dashboards. Its published audit found **826 of 826 panels returning data**, with no empty panel results or query errors in the checked views. Garmin now distinguishes watch uploads from actual health sample freshness; maintenance cards distinguish no recorded events from incomplete history.

InfluxDB dashboards need the correct query language: map the Flux input to a **Flux** connection and Garmin to **InfluxQL**. They are separate data sources. Example addresses, fixed host selectors, bucket names and collector paths must be adapted to the importing deployment. A missing optional metric is labelled as unavailable; it is not converted into a healthy zero.

### Garmin Connect

Import [Garmin Connect Stats](personal/Garmin-Connect-Stats.json) and select the
InfluxQL data source that reads your Garmin database. The summary shows today’s
reported steps, the latest heart-rate reading, and separate ages for the last
watch upload, heart-rate sample, step sample, and sleep record. Recent charts
keep their own 24-hour or local-day windows. Daily activity, Body Battery,
sleep summaries, and overnight sensor history follow the dashboard time picker,
which defaults to 60 days. Zoom to a recorded sleep session for detail, and set
**Local Time Zone** for daily aggregation. Missing samples leave gaps.

Body Battery is Garmin's wellness estimate. To graph the watch's hardware
battery level, GarminHomeAssistant from Connect IQ must report a battery sensor
to Home Assistant, and its samples must reach a Grafana data source.
[GarminHomeAssistant background reporting](https://github.com/house-of-abbey/GarminHomeAssistant/blob/main/BackgroundService.md)
[Garmin fetcher documentation](https://github.com/arpanghosh8453/garmin-grafana)

Dashboard exports can be refreshed with [the sanitizer](tools/export_sanitized.py), a private binding map and optional private literal redactions. Saved query selections are cleared. Inspect every generated diff: automated masking alone does not prove an export is safe to publish. [Provisioning examples](provisioning/) contain no production credentials.

### Soju IRC Bouncer

Import [Soju IRC Bouncer](services/Soju-IRC-Bouncer.json) into the **Services** folder and map `${DS_PROMETHEUS}` to your Prometheus data source. Enable Soju's Prometheus listener and scrape it with the job name `soju`; keep the metrics endpoint on a private network. The dashboard uses a 30-second minimum query step for a 30-second scrape interval. Adjust that step if you use a different scrape interval.

The dashboard covers users, connections, IRC protocol traffic, upstream errors, worker panics, process resources, uptime by instance, and scrape health. Its native metrics work with SQLite and PostgreSQL backends. The Instance selector includes targets whose scrapes are failing, and native queries stay scoped to the `soju` job. **Scrape status** reports exporter reachability; upstream IRC connection failures appear separately in the reliability panels. Graphs require newly collected samples and cannot reconstruct missing metrics history.

Configured network totals, paused and unexpectedly disconnected networks, saved channels, and currently joined channels use the optional read-only `soju_admin_*` textfile collector supplied with [soju-tui's Grafana integration](https://github.com/variablenix/soju-tui/tree/main/grafana). Scrape its private exporter under `soju-admin` and set its `soju_instance` label to the matching native Soju target. These implementation-specific aggregates work with either database backend and count each user/network configuration separately. Saved channels can include parted channels; joined channels reflect live upstream joins. The dashboard excludes failed, unreachable, and older-than-120-second collections, and displays missing counts as N/A. **Counts collector** reports freshness. Native metrics alone continue to populate the remaining panels.

Reliability rates, **Events in selected range**, and the **since start** counters use different time spans. Repeated failed retries of one upstream each count as another attempt. A raw counter does not return to zero when a connection recovers; selected-range estimates use Prometheus `increase()` and are rounded for display. The lifetime totals use a neutral color because they describe historical events rather than current outages.

**Networks down** is the current count of enabled but disconnected configurations. The uptime card shows the shortest uptime among selected Soju processes; the uptime chart shows each process separately.

---
*Maintained by the KDN Observability Stack contributors.*
