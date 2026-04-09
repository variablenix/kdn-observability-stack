# 📊 Global Observability Stack (Sanitized)

Welcome to the public mirror of my monitoring and observability configurations. These dashboards are the pulse of my **KDN Lab**, a production-grade 10+ node Proxmox environment where I architect and test infrastructure patterns before they hit production.

### **Why this exists**
As a **Senior Platform & Infrastructure Engineer**, I believe in "Infrastructure as Code" and treating home labs with the same rigor as an enterprise data center. I’m sharing these to provide a baseline for others building complex self-hosted stacks involving high-speed networking, security meshes, and containerized services.

### **The "Sanitization" Workflow**
For security and privacy, these files have been processed through a surgical sanitization pipeline before being mirrored from my internal **Gitea** instance.
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

---
*Maintained by **AK** | [aklein.pro](https://aklein.pro)*
