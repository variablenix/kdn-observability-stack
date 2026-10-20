# 📊 Global Observability Stack (Sanitized)

Welcome to a public collection of monitoring and observability configurations for a production-grade 10+ node Proxmox environment. The dashboards are designed to help operators evaluate infrastructure patterns before they reach production.

### **Why this exists**
The project follows **Infrastructure as Code** practices and treats self-hosted environments with the same rigor as an enterprise data center. It provides a baseline for others building complex self-hosted stacks involving high-speed networking, security meshes, and containerized services.

### **The "Sanitization" Workflow**
For security and privacy, these files have been processed through a sanitization pipeline before being published from an internal **Gitea** instance.
* **Network Masking:** All public WAN IPs and remote VPS addresses have been replaced with placeholders (`REDACTED_IP`).
* **Domain Generalization:** Internal subdomains (pointing to my **Authentik** SSO, **Gitea** instance, or **Lounge24 Radio** station) have been generalized to `example-user.pro`.
* **Portability:** Hardcoded `datasource` UIDs have been stripped and replaced with template variables (`${DS_PROMETHEUS}`) to ensure these dashboards are "plug-and-play" for the community.
* **Secret Management:** No API keys, tokens, or hashes are contained within this repository.

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
3. Upload the JSON and map the `${DS_...}` variables to your local Prometheus or InfluxDB data sources.

### Soju IRC Bouncer

Import [Soju IRC Bouncer](services/Soju-IRC-Bouncer.json) into the **Services** folder and map `${DS_PROMETHEUS}` to your Prometheus data source. Enable Soju's Prometheus listener and scrape it with the job name `soju`; keep the metrics endpoint on a private network. The dashboard uses a 30-second minimum query step for a 30-second scrape interval. Adjust that step if you use a different scrape interval.

The dashboard covers users, connections, IRC protocol traffic, upstream errors, worker panics, process resources, uptime by instance, and scrape health. Its native metrics work with SQLite and PostgreSQL backends. The Instance selector includes targets whose scrapes are failing, and native queries stay scoped to the `soju` job. **Scrape status** reports exporter reachability; upstream IRC connection failures appear separately in the reliability panels. Graphs require newly collected samples and cannot reconstruct missing metrics history.

Configured network totals, paused and unexpectedly disconnected networks, saved channels, and currently joined channels use the optional read-only `soju_admin_*` textfile collector supplied with [soju-tui's Grafana integration](https://github.com/variablenix/soju-tui/tree/main/grafana). Scrape its private exporter under `soju-admin` and set its `soju_instance` label to the matching native Soju target. These implementation-specific aggregates work with either database backend and count each user/network configuration separately. Saved channels can include parted channels; joined channels reflect live upstream joins. The dashboard excludes failed, unreachable, and older-than-120-second collections, and displays missing counts as N/A. **Counts collector** reports freshness. Native metrics alone continue to populate the remaining panels.

Reliability rates, **Events in selected range**, and the **since start** counters use different time spans. Repeated failed retries of one upstream each count as another attempt. A raw counter does not return to zero when a connection recovers; selected-range estimates use Prometheus `increase()` and are rounded for display. The lifetime totals use a neutral color because they describe historical events rather than current outages.

**Networks down** is the current count of enabled but disconnected configurations. The uptime card shows the shortest uptime among selected Soju processes; the uptime chart shows each process separately.

---
*Maintained by the KDN Observability Stack contributors.*
