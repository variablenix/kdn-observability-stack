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
NGINX_FRESH = ' and on(job,instance) (time()-crowdsec_nginx_observation_timestamp_seconds{job="crowdsec-health"}<660) and on(job,instance) (crowdsec_nginx_observation_timestamp_seconds{job="crowdsec-health"}<=time()+60)'
NGINX_STATES = [('UNAVAILABLE', 'gray'), ('IN PROGRESS', 'blue'), ('UP TO DATE', 'green'),
    ('UPDATED', 'green'), ('REVIEW NEEDED', 'orange'), ('WAITING FOR IMAGE AGE', 'blue'),
    ('FAILED / BLOCKED', 'red'), ('ROLLED BACK', 'orange'), ('RECOVERY REQUIRED', 'red'),
    ('DOCS PENDING', 'orange'), ('STALE', 'gray'), ('PREFLIGHT FAILED', 'red'),
    ('VALIDATION COMPLETE', 'blue'), ('DISABLED', 'orange'), ('ELIGIBLE UPDATE QUEUED', 'blue')]


def nginx(metric, labels=''):
    return 'crowdsec_nginx_' + metric + '{job="crowdsec-health"' + labels + '}' + NGINX_FRESH


def nginx_last_event(event):
    """Timestamp or categorical state, never a manufactured event timestamp.

    0 means fresh, successfully read retained history contains no such event.
    -1 means the history is unavailable/incomplete/stale or the scrape is down.
    """
    up = 'up{job="crowdsec-health"}'
    live = ' and on(job,instance) (' + up + ' == 1)'
    complete = '((' + nginx('history_complete') + ') == 1)'
    recorded = '((' + nginx('last_'+event+'_timestamp_seconds') + live + ' and on(job,instance) ' + complete + ') > 0)*1000'
    empty = '(0*' + complete + live + ')'
    unknown = '(0*' + up + '-1)'
    return recorded + ' or on(job,instance) ' + empty + ' or on(job,instance) ' + unknown


def maintenance(d, full=False):
    d.row('Nginx gateway maintenance — fleet-wide')
    p = d.panel('Nginx automatic update status', nginx('state'), 'stat', 6, 5,
        description='Current native controller + independent watcher evidence. No change is a successful check, not a deployed upgrade. Same-pin acceptance is validation. In progress requires a running native service; stale evidence is not healthy.')
    p['fieldConfig']['defaults']['mappings'] = [{'type': 'value', 'options': {
        str(i): {'text': text, 'color': color, 'index': i} for i, (text, color) in enumerate(NGINX_STATES)}}]
    d.panel('Pending nginx advisory reviews', nginx('pending_reviews'), 'stat', 6, 5,
        description='Unacknowledged advisory revisions, not CVE counts. An out-of-policy candidate also sets REVIEW NEEDED even when this is zero.')
    d.panel('Failed automatic transactions — rolling 24h', nginx('transactions_24h', ',kind="failures"'), 'stat', 6, 5,
        description='Retained automatic journal outcomes: rejected preflight, incomplete recovery, or rollback. Excludes acceptance/rehearsal/audit. Failures before journaling are visible in current status, not this count.')
    d.panel('Production rollbacks — rolling 24h', nginx('transactions_24h', ',kind="rollbacks"'), 'stat', 6, 5,
        description='Retained automatic transactions with a changed candidate and completed rollback. Also included in failed transaction count; not additive. Incomplete rollback is RECOVERY REQUIRED, not completed rollback.')
    if not full:
        return
    d.panel('Automatic scheduler enabled', nginx('scheduler_enabled'), 'stat', 6, 4, binary=True)
    d.panel('Controller last check age', 'time()-('+nginx('last_check_timestamp_seconds')+')', 'stat', 6, 4, unit='s',
        description='Daily result may be up to 26 hours old; five-minute observation freshness is enforced separately. STALE after 26 hours.')
    d.panel('Watcher findings', nginx('watch_errors'), 'stat', 6, 4,
        description='Registry, advisory or source/runtime/Internal Dockhand drift findings. Unknown/stale watcher evidence is N/A, not zero.')
    d.panel('Retained history complete', nginx('history_complete'), 'stat', 6, 4, binary=True,
        description='Reader bound is 512 journals, 64 KiB each. Any missing/malformed/unsafe record or overflow makes counts unavailable instead of silently undercounting.')
    d.panel('Nginx transactions — fixed rolling 24h', nginx('transactions_24h'), 'table',
        description='Rolling gauges, not lifetime counters: do not use increase(). Validation failures are separate from automatic failures. Counts use each journal latest write time, not the selected Grafana range.')
    d.panel('Latest recorded nginx transaction', nginx('transaction_info'), 'table',
        description='Mode, phase and outcome of the latest durable transaction. Can precede an in-progress validation or a blocked attempt that did not create a journal. A validation activation is not a production upgrade.')
    for event, title in [('upgrade', 'Last verified production upgrade'), ('rollback', 'Last completed production rollback')]:
        p = d.panel(title, nginx_last_event(event), 'stat', 12, 4, 'dateTimeAsLocal',
            description='Latest retained completed production '+event+'. No recorded event is shown only with fresh, complete history and a successful scrape; incomplete/stale history is explicitly unavailable. Same-pin acceptance is not an upgrade; incomplete recovery is not a completed rollback.')
        p['fieldConfig']['defaults']['noValue'] = 'History unavailable'
        p['fieldConfig']['defaults']['mappings'] = [{'type': 'value', 'options': {
            '0': {'text': 'No recorded '+event, 'color': 'blue'},
            '-1': {'text': 'History unavailable / incomplete', 'color': 'orange'}}}]
    d.note('Maintenance interpretation', 'Seven owned nginx guards use this controller. The independent watcher checks runtime, canonical Ansible and Internal Dockhand definitions. This collector only reads existing records; it never deploys images, retries Cloudflare or changes timers. **Pending review** and **waiting for image age** are deliberate gates. **Rolled back** means recovery completed, not that the candidate was repaired. Same-pin acceptance/rehearsal/audit runs remain separate. Transaction counts are a fixed rolling **24 hours**, using each retained journal’s latest write, not an exhaustive event log. Pre-journal failed attempts appear in current status only. Missing/incomplete history is N/A, not zero. Observation freshness is 11 minutes; daily check freshness is 26 hours. Core protection health and maintenance warnings remain distinct.')


def health(metric, labels=""):
    return "crowdsec_health_" + metric + '{job="crowdsec-health"' + labels + '}' + FRESH


def increase(metric, group="hostname", selector=ENGINE):
    return f'sum by({group})(increase({metric}{selector}[$__range]))'


def rate(metric, group="hostname", selector=ENGINE):
    return f'sum by({group})(rate({metric}{selector}[$__rate_interval]))'


def operational_severity():
    # 0 critical, 1 attention, 2 healthy. Missing/stale inputs remain absent.
    core = '(sum(1-(' + health('entity_healthy') + ')) == bool 0)'
    collections = '(sum(1-(' + health('check_success', ',check=~"machines|bouncers|decisions"') + ')) == bool 0)'
    engines = '(min(up{job=~"crowdsec|crowdsec-agents"}) == bool 1)'
    warnings_clear = '(' + health('success') + ') * on(job,instance) (1-(' + nginx('attention') + '))'
    core_clear = '(' + core + '*' + collections + '*' + engines + ')'
    # Missing maintenance must never hide a positively observed core outage.
    return ('(1+(' + warnings_clear + '))*on() group_left() ' + core_clear
            + ' or on() (0*(' + core_clear + ' == 0))')


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
             "fieldConfig": {"defaults": {"unit": unit, "noValue": "No alert POST observations" if title == "Agent alert POSTs — selected range" else "N/A", "color": {"mode": "palette-classic"},
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
            fields = ["hostname", "server", "mode", "phase", "outcome", "kind", "name", "machine", "bouncer", "check", "source", "version",
                      "reason", "origin", "action", "method", "route", "endpoint", "Value"]
            hidden = ["Time", "__name__", "instance", "job", "location", "role", "use", "os", "kind",
                      "service", "acquis_type", "datasource_type", "stage", "type"]
            if expr and ("crowdsec_health_" in expr or 'crowdsec_nginx_' in expr):
                # This is the collector host, not the agent/bouncer being listed.
                hidden.append("hostname")
            if "versions" in title.lower():
                hidden.append("Value")
            p["transformations"] = [{"id": "organize", "options": {
                "excludeByName": {key: True for key in hidden},
                "indexByName": {key: i for i, key in enumerate(fields)},
                "renameByName": {"hostname": "Host", "server": "Host", "name": "Entity / scenario",
                                 "machine": "Agent", "bouncer": "Bouncer", "check": "Health check",
                                 "source": "Log source", "version": "Version", "reason": "Reason",
                                 "origin": "Origin", "action": "Action", "method": "Method",
                                 "mode": "Run mode", "phase": "Transaction phase", "outcome": "Outcome", "kind": "Transaction category",
                                 "route": "Route", "endpoint": "Endpoint", "Value": "Status" if binary else "Value"}}}]
            if expr and 'crowdsec_nginx_' in expr:
                p['transformations'][0]['options']['excludeByName'].pop('kind', None)
                if 'transaction_info' in expr:
                    p['transformations'][0]['options']['excludeByName']['Value'] = True
                labels = {
                    'Run mode': {'automatic': 'Automatic', 'acceptance': 'Same-pin acceptance', 'rehearsal': 'Rehearsal', 'audit': 'Read-only audit'},
                    'Transaction phase': {x: x.replace('_', ' ').capitalize() for x in (
                        'checking', 'preflighting', 'promoting', 'deploying', 'rolling_back', 'recovery_required',
                        'documentation_pending', 'completed', 'rolled_back', 'preflight_failed', 'no_change',
                        'review_required', 'waiting_for_image_age', 'blocked')},
                    'Outcome': {'not_recorded': 'No terminal outcome', 'activated': 'Validation activated', 'updated': 'Image upgraded',
                        'rolled_back': 'Rollback completed', 'rehearsed_without_image_or_git_changes': 'Rehearsal completed — unchanged',
                        'rehearsal_rolled_back_without_git_changes': 'Rehearsal rollback — no Git change'},
                    'Transaction category': {'updates': 'Verified image upgrades', 'failures': 'Failed automatic transactions',
                        'rollbacks': 'Completed production rollbacks', 'validations': 'Validation / audit runs',
                        'validation_failures': 'Failed validation runs'}}
                for field, values in labels.items():
                    p['fieldConfig']['overrides'].append({'matcher': {'id': 'byName', 'options': field},
                        'properties': [{'id': 'mappings', 'value': [{'type': 'value', 'options': {
                            key: {'text': value, 'index': i} for i, (key, value) in enumerate(values.items())}}]}]})
            if binary:
                p['fieldConfig']['overrides'].append({'matcher': {'id': 'byName', 'options': 'Status'},
                    'properties': [{'id': 'custom.width', 'value': 110},
                                   {'id': 'custom.cellOptions', 'value': {'type': 'color-text'}}]})
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
    p = d.panel("Overall operational health", operational_severity(), "stat", 6, 4,
                description="HEALTHY: protection and maintenance checks pass. ATTENTION: nginx maintenance or update/verification warnings with core fleet online. CRITICAL: an expected agent/bouncer, engine scrape, LAPI or core collection is unhealthy. Missing/stale input is N/A, never healthy.")
    p['fieldConfig']['defaults'].update({'min': 0, 'max': 2, 'color': {'mode': 'thresholds'},
        'mappings': [{'type': 'value', 'options': {
            '0': {'text': 'CRITICAL', 'color': 'red', 'index': 0},
            '1': {'text': 'ATTENTION', 'color': 'orange', 'index': 1},
            '2': {'text': 'HEALTHY', 'color': 'green', 'index': 2}}}],
        'thresholds': {'mode': 'absolute', 'steps': [{'color': 'red', 'value': None}, {'color': 'orange', 'value': 1}, {'color': 'green', 'value': 2}]}})
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
    p = d.panel("Community list freshness", health("check_success", ',check="cloudflare-community-list-status"'), "stat", 6, 4, binary=True,
                description="NEEDS REFRESH is a real freshness warning, not an outage of every agent. See saved retry and current failure reason. Never means a refresh is currently running.")
    p['fieldConfig']['defaults']['mappings'][0]['options']['0'].update(text='NEEDS REFRESH', color='orange')
    p['fieldConfig']['defaults']['mappings'][0]['options']['1'].update(text='CURRENT')
    p['fieldConfig']['defaults']['thresholds']['steps'][0]['color'] = 'orange'
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
    maintenance(d, full=True)
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
    maintenance(d)
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
    maintenance(d)
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
