#!/usr/bin/env python3
"""Build portable CrowdSec dashboards; no production telemetry or credentials."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DS = {"type": "prometheus", "uid": "${DS_PROMETHEUS}"}
ENGINE = '{job=~"crowdsec|crowdsec-agents",hostname=~"${hostname:regex}"}'
LAPI = '{job="crowdsec"}'
HEALTH = '{job="crowdsec-health"}'
FRESH = ' and on(job,instance) (time()-crowdsec_health_last_run_timestamp_seconds{job="crowdsec-health"}<660)'
SOURCES = '{job=~"crowdsec|crowdsec-agents",hostname=~"${hostname:regex}",__name__=~"cs_filesource_hits_total|cs_dockersource_hits_total"}'


def health(metric, labels=""):
    return "crowdsec_health_" + metric + '{job="crowdsec-health"' + labels + '}' + FRESH


def increase(metric, group="hostname", selector=ENGINE):
    return f'sum by({group})(increase({metric}{selector}[$__range]))'


def rate(metric, group="hostname", selector=ENGINE):
    return f'sum by({group})(rate({metric}{selector}[$__rate_interval]))'


class Dashboard:
    def __init__(self, title, uid, description):
        self.data = {"id": None, "uid": uid, "title": title, "description": description,
                     "tags": ["crowdsec", "security", "fleet"], "timezone": "browser",
                     "schemaVersion": 41, "version": 1, "editable": True,
                     "refresh": "30s", "time": {"from": "now-24h", "to": "now"},
                     "timepicker": {}, "annotations": {"list": []}, "panels": [],
                     "links": [{"title": title, "url": "/d/"+link, "type": "link", "keepTime": True,
                                "includeVars": True} for title, link in
                               [("Fleet", "kdn-crowdsec-fleet"), ("Metrics", "crowdsec-engine"), ("Insights", "e7sWOBVnk")]],
                     "templating": {"list": [
                         {"name": "DS_PROMETHEUS", "label": "Prometheus", "type": "datasource",
                          "query": "prometheus", "refresh": 1, "current": {}, "options": []},
                         {"name": "hostname", "label": "Engine host", "type": "query", "datasource": DS,
                          "definition": 'label_values(up{job=~"crowdsec|crowdsec-agents"},hostname)',
                          "query": {"query": 'label_values(up{job=~"crowdsec|crowdsec-agents"},hostname)', "refId": "hosts"},
                          "refresh": 1, "sort": 1, "multi": True, "includeAll": True, "allValue": ".*",
                          "current": {"text": "All", "value": "$__all"}, "options": []}]}}
        self.y = 0
        self.x = 0
        self.height = 0

    def panel(self, title, expr=None, kind="timeseries", width=12, height=8, unit="short",
              description="", legend="{{hostname}}", binary=False, text=None):
        if self.x + width > 24:
            self.y += self.height
            self.x = self.height = 0
        p = {"id": len(self.data["panels"])+1, "title": title, "type": kind,
             "description": description, "gridPos": {"x": self.x, "y": self.y, "w": width, "h": height},
             "fieldConfig": {"defaults": {"unit": unit, "noValue": "N/A", "color": {"mode": "palette-classic"},
                                          "thresholds": {"mode": "absolute", "steps": [{"color": "blue", "value": None}]}}, "overrides": []},
             "options": {}}
        if expr:
            p["datasource"] = DS
            p["targets"] = [{"refId": "A", "expr": expr, "legendFormat": legend, "editorMode": "code",
                             "instant": kind in ("stat", "table", "bargauge"), "range": kind == "timeseries",
                             "format": "table" if kind == "table" else "time_series", "interval": "30s"}]
            p["interval"] = "30s"
        if kind == "stat":
            p["options"] = {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                            "colorMode": "value", "graphMode": "none", "textMode": "auto", "orientation": "auto"}
        elif kind == "timeseries":
            p["options"] = {"legend": {"displayMode": "table", "placement": "bottom", "calcs": ["lastNotNull", "max"]},
                            "tooltip": {"mode": "multi", "sort": "desc"}}
            p["fieldConfig"]["defaults"]["custom"] = {"drawStyle": "line", "lineWidth": 1,
                "fillOpacity": 10, "showPoints": "never", "spanNulls": False, "axisCenteredZero": False}
        elif kind == "table":
            p["options"] = {"showHeader": True, "cellHeight": "sm", "footer": {"show": False}}
            fields = ["hostname", "server", "name", "machine", "bouncer", "check", "source", "version",
                      "reason", "origin", "action", "method", "route", "endpoint", "Value"]
            hidden = ["Time", "__name__", "instance", "job", "location", "role", "use", "os", "kind",
                      "service", "acquis_type", "datasource_type", "stage", "type"]
            if "versions" in title.lower():
                hidden.append("Value")
            p["transformations"] = [{"id": "organize", "options": {
                "excludeByName": {key: True for key in hidden},
                "indexByName": {key: i for i, key in enumerate(fields)},
                "renameByName": {"hostname": "Host", "server": "Host", "name": "Entity / scenario",
                                 "machine": "Agent", "bouncer": "Bouncer", "check": "Health check",
                                 "source": "Log source", "version": "Version", "reason": "Reason",
                                 "origin": "Origin", "action": "Action", "method": "Method",
                                 "route": "Route", "endpoint": "Endpoint", "Value": "Status" if binary else "Value"}}}]
        elif kind == "text":
            p["options"] = {"mode": "markdown", "content": text}
        elif kind == "row":
            p.update(collapsed=False, panels=[])
        if binary:
            p["fieldConfig"]["defaults"].update({"min": 0, "max": 1,
                "mappings": [{"type": "value", "options": {
                    "0": {"text": "FAILED", "color": "red", "index": 0},
                    "1": {"text": "PASSING", "color": "green", "index": 1}}}],
                "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "green", "value": 1}]}})
        self.data["panels"].append(p)
        self.x += width
        self.height = max(self.height, height)
        return p

    def note(self, title, text, height=4):
        return self.panel(title, kind="text", width=24, height=height, text=text)

    def row(self, title):
        if self.x:
            self.y += self.height
        self.x = self.height = 0
        self.panel(title, kind="row", width=24, height=1)
        self.y += 1
        self.x = self.height = 0


def fleet():
    d = Dashboard("CrowdSec Fleet", "kdn-crowdsec-fleet", "Operational assurance: current agents, remediation, CAPI and Cloudflare freshness. Engine host filters do not scope central LAPI or fleet health.")
    d.note("Read this first", "**Engine host** filters engine panels. LAPI, bouncer and health panels deliberately remain fleet-wide. **N/A is not healthy or zero.** Health results older than 11 minutes are excluded. Historical graphs and retained alert records are not new attacks. The private email report supplies source IP, country, ASN and service/host investigations; these are not exposed by native engine metrics.", 4)
    d.panel("Overall operational health", health("success"), "stat", 6, 4, binary=True, description="A genuine Cloudflare freshness failure remains FAILED even when every agent is online.")
    d.panel("Central LAPI scrape", 'up{job="crowdsec"}', "stat", 6, 4, binary=True)
    d.panel("Selected engines up", 'sum(up'+ENGINE+')', "stat", 6, 4)
    d.panel("Selected engines configured", 'count(up'+ENGINE+')', "stat", 6, 4)
    d.panel("Healthy monitored agents", 'sum('+health("entity_healthy", ',kind="machine"')+')', "stat", 6, 4)
    d.panel("Healthy monitored bouncers", 'sum('+health("entity_healthy", ',kind="bouncer"')+')', "stat", 6, 4)
    d.panel("Active LAPI decision records", 'sum(cs_active_decisions'+LAPI+')', "stat", 6, 4, description="Records, not necessarily distinct IPs or blocked requests. Includes community/list origins.")
    d.panel("Retained alert records", 'sum(cs_alerts'+LAPI+')', "stat", 6, 4, description="Current database retention, not a rolling-24-hour detection count.")
    d.row("Current fleet assurance")
    d.panel("Every monitored agent", health("entity_healthy", ',kind="machine"'), "table", binary=True, description="Current expected machine health; includes absent registrations as failed.")
    d.panel("Every monitored bouncer", health("entity_healthy", ',kind="bouncer"'), "table", binary=True)
    d.panel("All availability checks", health("check_success"), "table", binary=True)
    d.panel("Current failure reasons", health("check_failure_reason"), "table", description="Only active failures emit this metric. No rows means no recorded failure reasons, provided the health snapshot is fresh.")
    d.panel("Health snapshot age", 'time()-crowdsec_health_last_run_timestamp_seconds'+HEALTH, "stat", 6, 4, "s")
    d.panel("CAPI last verified age", '(time()-crowdsec_health_capi_last_verified_timestamp_seconds'+HEALTH+')'+FRESH, "stat", 6, 4, "s", description="Age of a successful verification, not an authentication probe from this dashboard.")
    d.panel("Home IPv4 DDNS refresh", health("check_success", ',check="ddns-sync-status"'), "stat", 6, 4, binary=True)
    d.panel("Home IPv6 prefix refresh", health("check_success", ',check="prefix-sync-status"'), "stat", 6, 4, binary=True)
    d.panel("Machine last-seen age", health("entity_age_seconds", ',kind="machine"'), legend="{{name}}", unit="s")
    d.panel("Bouncer last-pull age", health("entity_age_seconds", ',kind="bouncer"'), legend="{{name}}", unit="s")
    d.row("Cloudflare and public HTTP gateways")
    d.panel("Community list freshness", health("check_success", ',check="cloudflare-community-list-status"'), "stat", 6, 4, binary=True)
    d.panel("Community list last verification age", '(time()-crowdsec_health_cloudflare_bulk_last_verified_timestamp_seconds'+HEALTH+')'+FRESH, "stat", 6, 4, "s")
    d.panel("Saved next bulk attempt", '('+health("cloudflare_bulk_next_attempt_timestamp_seconds")+')*1000', "stat", 6, 4, "dateTimeAsLocal", description="Read-only saved quota retry. Viewing does not retry, reset or advance it.")
    d.panel("Community candidates omitted", health("cloudflare_bulk_omitted"), "stat", 6, 4, description="Capacity exclusions, not blocked Cloudflare requests.")
    d.panel("HTTP gateway synchronization", 'crowdsec_http_gateway_sync_success{job="crowdsec-http-gateway-health"}', "table", binary=True, description="Local decision sync health. Also review central sync-status and bootstrap checks above for freshness.")
    d.panel("HTTP gateway last apply age", 'time()-crowdsec_http_gateway_last_apply_success_timestamp_seconds{job="crowdsec-http-gateway-health"}', unit="s", legend="{{server}}")
    d.note("Enforcement boundaries", "Cloudflare list freshness, LAPI polling and actual request blocking are separate signals. Current metrics do **not** expose Cloudflare WAF request/challenge totals or per-IP/geo events. Host firewalls protect direct connections; tunnel traffic requires HTTP/edge enforcement. No AppSec/WAF engine metrics are configured, so empty AppSec panels are intentionally not shown.")
    d.row("Decisions and API activity")
    d.panel("Active decisions by origin/action", 'sum by(origin,action)(cs_active_decisions'+LAPI+')', legend="{{origin}} / {{action}}")
    d.panel("Top decision reasons — current records", 'topk(10,sum by(reason)(cs_active_decisions'+LAPI+'))', "table")
    d.panel("Bouncer pulls — selected range", increase("cs_lapi_bouncer_requests_total", "bouncer", LAPI), "table", description="Reset-aware request estimates, not blocked traffic.")
    d.panel("Agent alert POSTs — selected range", increase("cs_lapi_machine_requests_total", "machine", '{job="crowdsec",method="POST",route="/v1/alerts"}'), "table", description="POST requests may contain multiple alerts; not the number of detections.")
    d.panel("Bouncer request rate", rate("cs_lapi_bouncer_requests_total", "bouncer", LAPI), legend="{{bouncer}}", unit="reqps")
    d.panel("LAPI requests by route", rate("cs_lapi_route_requests_total", "route,method", LAPI), legend="{{method}} {{route}}", unit="reqps")
    d.row("Engine workload and availability")
    d.panel("Engine scrape availability", 'up'+ENGINE, binary=True)
    d.panel("Engine versions", 'cs_info'+ENGINE, "table", description="Version is a label. cs_info intentionally has numeric value zero; that is not a health failure.")
    d.panel("Log lines — selected range", f'sum by(hostname)(increase({SOURCES}[$__range]))', "table")
    d.panel("Scenario overflows — selected range", increase("cs_bucket_overflowed_total", "hostname,name"), "table", description="Overflows can include tests/internal sources; not confirmed external attackers.")
    d.panel("Engine resident memory", 'process_resident_memory_bytes'+ENGINE, unit="bytes")
    d.panel("Observed process start changes — selected range", 'changes(process_start_time_seconds'+ENGINE+'[$__range])', "table", description="Observed changes only; restarts between scrapes may be missed.")
    return d.data


def metrics():
    d = Dashboard("CrowdSec Metrics", "crowdsec-engine", "Engine pipeline and central LAPI performance, with current native metric names and portable selectors.")
    d.note("Metric semantics", "Engine panels honor **Engine host**. Central API panels always use the LAPI job, even if an agent is selected. Rates use a scrape-safe interval; totals use the selected time range and are estimates. Quiet counter families may not exist until their first event: N/A is explicitly not a zero. Parser-node hits count traversal, not unique input lines.")
    d.panel("Selected engine targets", 'count(up'+ENGINE+')', "stat", 6, 4)
    d.panel("Selected engine targets up", 'sum(up'+ENGINE+')', "stat", 6, 4)
    d.panel("Acquired lines — selected range", f'sum(increase({SOURCES}[$__range]))', "stat", 6, 4)
    d.panel("Parser successes — selected range", 'sum(increase(cs_parser_hits_ok_total'+ENGINE+'[$__range]))', "stat", 6, 4)
    d.row("Acquisition and parsing")
    d.panel("Input lines per second", f'sum by(hostname)(rate({SOURCES}[$__rate_interval]))', unit="ops")
    d.panel("Input by source — selected range", f'topk(20,sum by(hostname,source)(increase({SOURCES}[$__range])))', "table")
    d.panel("Parser successful lines per second", rate("cs_parser_hits_ok_total"), unit="ops")
    d.panel("Parser unparsed lines per second", rate("cs_parser_hits_ko_total"), unit="ops", description="Many benign application lines have no matching security parser. Investigate sustained unexpected changes, not every unparsed line.")
    d.panel("Parser unparsed sources — selected range", 'topk(20,'+increase("cs_parser_hits_ko_total", "hostname,source")+')', "table")
    d.panel("Allowlisted node matches — selected range", increase("cs_node_wl_hits_ok_total", "hostname,name,reason"), "table", description="Node-level match counts, not guaranteed unique lines or dropped requests.")
    d.panel("Parser-node successful hits", rate("cs_node_hits_ok_total", "hostname,name"), legend="{{hostname}} / {{name}}", unit="ops")
    d.panel("Parser-node nonmatches", 'topk(10,'+rate("cs_node_hits_ko_total", "hostname,name")+')', legend="{{hostname}} / {{name}}", unit="ops", description="Nonmatches during parser traversal are expected; not parser exceptions.")
    d.row("Scenario lifecycle")
    d.panel("Bucket instantiations per second", rate("cs_bucket_instantiation_total", "hostname,name"), legend="{{hostname}} / {{name}}", unit="ops")
    d.panel("Bucket events poured per second", rate("cs_bucket_poured_total", "hostname,name"), legend="{{hostname}} / {{name}}", unit="ops")
    d.panel("Scenario overflows — selected range", increase("cs_bucket_overflowed_total", "hostname,name"), "table")
    d.panel("Underflows — selected range", increase("cs_bucket_underflowed_total", "hostname,name"), "table")
    d.panel("Active buckets", 'sum by(hostname,name)(cs_buckets'+ENGINE+')', legend="{{hostname}} / {{name}}")
    d.panel("Canceled buckets — selected range", increase("cs_bucket_canceled_total", "hostname,name"), "table", description="May be absent until emitted. No series is not a healthy-zero assertion.")
    d.row("Central Local API — intentionally fleet-wide")
    d.panel("LAPI request rate", rate("cs_lapi_route_requests_total", "route,method", LAPI), unit="reqps", legend="{{method}} {{route}}")
    d.panel("Requests by route — selected range", increase("cs_lapi_route_requests_total", "route,method", LAPI), "table")
    d.panel("LAPI p95 request latency", 'histogram_quantile(0.95,sum by(le,endpoint,method)(rate(cs_lapi_request_duration_seconds_bucket'+LAPI+'[$__rate_interval]))) and on(endpoint,method) (sum by(endpoint,method)(rate(cs_lapi_request_duration_seconds_count'+LAPI+'[$__rate_interval]))>0)', unit="s", legend="{{method}} {{endpoint}}", description="A route without observations in the interval has no quantile, not zero latency.")
    d.panel("LAPI mean latency", 'sum by(endpoint,method)(rate(cs_lapi_request_duration_seconds_sum'+LAPI+'[$__rate_interval]))/(sum by(endpoint,method)(rate(cs_lapi_request_duration_seconds_count'+LAPI+'[$__rate_interval]))>0)', unit="s", legend="{{method}} {{endpoint}}")
    d.panel("Agent API request rate", rate("cs_lapi_machine_requests_total", "machine", LAPI), unit="reqps", legend="{{machine}}")
    d.panel("Bouncer API request rate", rate("cs_lapi_bouncer_requests_total", "bouncer", LAPI), unit="reqps", legend="{{bouncer}}")
    d.row("Process resources")
    d.panel("CPU — cores consumed", 'rate(process_cpu_seconds_total'+ENGINE+'[$__rate_interval])', unit="cores", description="One core = 1. Can exceed 1 for a multithreaded process.")
    d.panel("Resident memory", 'process_resident_memory_bytes'+ENGINE, unit="bytes")
    d.panel("Open file descriptors", 'process_open_fds'+ENGINE)
    d.panel("File descriptor limit utilization", 'process_open_fds'+ENGINE+'/process_max_fds'+ENGINE, unit="percentunit")
    d.panel("Engine uptime", 'time()-process_start_time_seconds'+ENGINE, unit="s")
    d.panel("Parsing p95 by source", 'histogram_quantile(0.95,sum by(le,hostname,source)(rate(cs_parsing_time_seconds_bucket'+ENGINE+'[$__rate_interval]))) and on(hostname,source) (sum by(hostname,source)(rate(cs_parsing_time_seconds_count'+ENGINE+'[$__rate_interval]))>0)', unit="s", legend="{{hostname}} / {{source}}")
    return d.data


def insights():
    d = Dashboard("Crowdsec Insights", "e7sWOBVnk", "Detection trends, source workload and telemetry quality. No raw attacker identities are exported by these metrics.")
    d.note("What these insights can and cannot show", "**Overflows** describe scenario activity, not unique attackers. Tests and internal events are included in native counters. The email report separates them using LAPI event data and identifies service + host, IP, country and ASN. Those dimensions cannot be invented from aggregate metrics. Current retained alerts and active decision records are separate inventories.")
    d.panel("Acquired lines — selected range", f'sum(increase({SOURCES}[$__range]))', "stat", 6, 4)
    d.panel("Parser successes — selected range", 'sum(increase(cs_parser_hits_ok_total'+ENGINE+'[$__range]))', "stat", 6, 4)
    d.panel("Unparsed lines — selected range", 'sum(increase(cs_parser_hits_ko_total'+ENGINE+'[$__range]))', "stat", 6, 4)
    d.panel("Scenario overflows — selected range", 'sum(increase(cs_bucket_overflowed_total'+ENGINE+'[$__range]))', "stat", 6, 4)
    d.row("Where activity is concentrated")
    d.panel("Top 10 scenario overflows — selected range", 'topk(10,'+increase("cs_bucket_overflowed_total", "hostname,name")+')', "table")
    d.panel("Scenario overflow rate", rate("cs_bucket_overflowed_total", "hostname,name"), unit="ops", legend="{{hostname}} / {{name}}")
    d.panel("Top 15 log sources — selected range", f'topk(15,sum by(hostname,source)(increase({SOURCES}[$__range])))', "table")
    d.panel("Input rate by source", f'topk(10,sum by(hostname,source)(rate({SOURCES}[$__rate_interval])))', unit="ops", legend="{{hostname}} / {{source}}")
    d.panel("Parser successes by host — selected range", increase("cs_parser_hits_ok_total"), "table")
    d.panel("Unparsed by host — selected range", increase("cs_parser_hits_ko_total"), "table")
    d.panel("Parser success share of evaluated lines", rate("cs_parser_hits_ok_total")+'/('+rate("cs_parser_hits_total")+'>0)', unit="percentunit", description="Success / evaluated parser lines. Not parser-node traversal ratio. No observations gives N/A, not 100%.")
    d.panel("Allowlist node matches by reason — selected range", increase("cs_node_wl_hits_ok_total", "hostname,reason"), "table")
    d.row("Telemetry coverage and freshness")
    d.panel("Current scrape status — selected engines", 'up'+ENGINE, "table", binary=True)
    d.panel("Scrape success share — selected range", 'avg_over_time(up'+ENGINE+'[$__range])', "table", unit="percentunit", description="Only observed samples. Combine with sample coverage; downtime in Prometheus itself is not counted as failed scrapes.")
    d.panel("Sample coverage — expected 30s scrape", 'clamp_max(count_over_time(up'+ENGINE+'[$__range])/($__range_s/30),1)', "table", unit="percentunit", description="Approximation for the configured 30-second cadence. Adjust denominator if scrape interval differs. Shows newly added targets/history gaps.")
    d.panel("Scrape duration", 'scrape_duration_seconds'+ENGINE, unit="s")
    d.panel("Observed process start changes — selected range", 'changes(process_start_time_seconds'+ENGINE+'[$__range])', "table")
    d.panel("Current engine versions", 'cs_info'+ENGINE, "table", description="Read the version label; the info metric value is intentionally zero.")
    d.row("Decision and alert context — central LAPI")
    d.panel("Current active decisions by origin", 'sum by(origin)(cs_active_decisions'+LAPI+')', legend="{{origin}}")
    d.panel("Current active decisions by action", 'sum by(action)(cs_active_decisions'+LAPI+')', legend="{{action}}")
    d.panel("Retained alerts by scenario", 'topk(10,sum by(reason)(cs_alerts'+LAPI+'))', "table", description="Retention inventory, not selected-range alert arrivals. Metric labels may aggregate events at the central API.")
    d.panel("Agent alert POSTs — selected range", increase("cs_lapi_machine_requests_total", "machine", '{job="crowdsec",method="POST",route="/v1/alerts"}'), "table")
    d.note("Quiet services and missing capabilities", "Internal-only services can be quiet. A missing lazy scenario counter is not proof that acquisition is broken: inspect input, parser successes, scrape coverage and the named source. Empty per-event tables may be normal. AppSec metrics, per-IP geography and Cloudflare request/challenge totals are not available in these native metrics and are not replaced with fabricated zeros.")
    return d.data


def dashboards():
    return {"CrowdSec-Fleet.json": fleet(), "CrowdSec-Metrics-.json": metrics(), "CrowdSec-Insights.json": insights()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for name, data in dashboards().items():
        expected = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        path = ROOT / name
        if args.check:
            if path.read_text() != expected:
                raise SystemExit("Generated dashboard differs: " + name)
        else:
            path.write_text(expected)


if __name__ == "__main__":
    main()
