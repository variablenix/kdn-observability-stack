#!/usr/bin/env python3
"""Reconcile imported dashboards with the metrics supported by this installation.

Pure model transformation: no credentials, network access, or deployment writes.
Run against API-model maps before sanitizing exports. Panel IDs and dashboard URLs
are preserved. Optional Garmin workout/GPS views are intentionally omitted until
recorded workouts exist; sleep and daily movement are separate measurements.
"""
import argparse
import copy
import json
from pathlib import Path


def walk(items):
    for panel in items:
        yield panel
        yield from walk(panel.get('panels', []))


def replace(panel, title, queries, unit='short', description='', kind=None):
    """Replace query semantics and stale display overrides together."""
    ds = copy.deepcopy(panel.get('datasource') or panel['targets'][0]['datasource'])
    panel['title'] = title
    panel['description'] = description
    panel['type'] = kind or panel['type']
    panel.pop('transformations', None)
    panel['fieldConfig'] = {'defaults': {'unit': unit, 'noValue': 'Unavailable',
        'color': {'mode': 'palette-classic'}, 'thresholds': {
            'mode': 'absolute', 'steps': [{'color': 'blue', 'value': None}]}}, 'overrides': []}
    panel['targets'] = [dict(refId=chr(65+i), datasource=ds, editorMode='code',
        expr=q, legendFormat=legend, instant=panel['type'] == 'stat',
        range=panel['type'] != 'stat') for i, (q, legend) in enumerate(queries)]
    if panel['type'] == 'stat':
        panel['options'] = {'reduceOptions': {'calcs': ['lastNotNull'], 'fields': '', 'values': False},
                            'colorMode': 'value', 'graphMode': 'none', 'textMode': 'auto'}
    else:
        panel['options'] = {'legend': {'displayMode': 'table', 'placement': 'bottom',
                                     'calcs': ['lastNotNull', 'max']},
                            'tooltip': {'mode': 'multi', 'sort': 'desc'}}
        panel['fieldConfig']['defaults']['custom'] = {'drawStyle': 'line', 'lineWidth': 1,
            'fillOpacity': 10, 'showPoints': 'never', 'spanNulls': False}


def garmin(d):
    by_id = {p['id']: p for p in d['panels']}
    # Fields verified against stored measurements, not presumed device features.
    specs = {
        48: ('Overnight HRV', 'SleepSummary', [('avgOvernightHrv', 'Overnight HRV')], 'ms'),
        53: ('Floors climbed and descended', 'DailyStats', [('floorsAscended', 'Climbed'), ('floorsDescended', 'Descended')], 'short'),
        54: ('Sleep interruptions', 'SleepSummary', [('awakeCount', 'Awakenings'), ('restlessMomentsCount', 'Restless moments')], 'short'),
        43: ('Sleep breathing rate', 'SleepSummary', [('averageRespirationValue', 'Average'), ('lowestRespirationValue', 'Lowest'), ('highestRespirationValue', 'Highest')], 'suffix:breaths/min'),
        50: ('Sleeping skin temperature deviation', 'SleepSummary', [('avgSkinTempDeviationC', 'Deviation from baseline')], 'celsius'),
        49: ('Average sleep stress', 'SleepSummary', [('avgSleepStress', 'Sleep stress')], 'short'),
        45: ('Body Battery on waking', 'DailyStats', [('bodyBatteryAtWakeTime', 'On waking')], 'short'),
        61: ('Body Battery recovered during sleep', 'SleepSummary', [('bodyBatteryChange', 'Overnight change')], 'short'),
        57: ('Daily movement and rest', 'DailyStats', [('activeSeconds', 'Active'), ('sedentarySeconds', 'Sedentary'), ('sleepingSeconds', 'Sleeping')], 's'),
        47: ('Recorded heart-rate samples per day', 'HeartRateIntraday', [('HeartRate', 'Samples')], 'short'),
        46: ('Latest heart-rate sample time', 'HeartRateIntraday', [('HeartRate', 'Sample time')], 'dateTimeAsLocal'),
        73: ('Latest recorded watch upload', 'DeviceSync', [('Device_Name', 'Upload time')], 'dateTimeAsLocal'),
        74: ('Heart-rate sample recency', 'HeartRateIntraday', [('HeartRate', 'Sample age')], 'dateTimeFromNow'),
    }
    unsupported = {34, 38, 41, 55, 60, 63, 64, 69}
    for id_, (title, measurement, fields, unit) in specs.items():
        if id_ not in by_id:
            by_id[id_] = copy.deepcopy(by_id[46])
            by_id[id_]['id'] = id_
        p = by_id[id_]
        timestamp = id_ in (46, 73, 74)
        replace(p, title, [], unit, 'Stored Garmin observations in the selected range. Missing samples remain gaps; no synthetic values or workout history.', 'stat' if timestamp else 'timeseries')
        for i, (field, alias) in enumerate(fields):
            query = f'SELECT mean("{field}") FROM "{measurement}" WHERE $timeFilter GROUP BY time(1d) fill(null) tz(\'$TimeZone\')'
            if id_ == 47:
                query = 'SELECT count("HeartRate") FROM "HeartRateIntraday" WHERE $timeFilter GROUP BY time(1d) fill(null) tz(\'$TimeZone\')'
            if timestamp:
                query = f'SELECT last("{field}") FROM "{measurement}" WHERE $timeFilter'
            p['targets'].append({'refId': chr(65+i), 'datasource': copy.deepcopy(p['datasource']),
                'rawQuery': True, 'query': query, 'resultFormat': 'time_series', 'alias': alias})
        if timestamp:
            # Display the observation's actual timestamp, not its bpm or the query time.
            p['transformations'] = [
                {'id': 'convertFieldType', 'options': {'conversions': [{'targetField': 'Time', 'destinationType': 'number'}]}},
                {'id': 'filterFieldsByName', 'options': {'include': {'names': ['Time']}}}]
            p['options']['reduceOptions']['fields'] = 'Time'
            p['fieldConfig']['defaults']['color'] = {'mode': 'fixed', 'fixedColor': 'blue'}
            p['description'] = 'Actual latest stored observation time in the selected range. A watch upload or a successful dashboard query does not establish new heart-rate or sleep data. Recency is shown relative to the current time.'
    # Repack readable sections instead of retaining large empty GPS map spaces.
    d['panels'] = [p for p in d['panels'] if p['id'] not in unsupported and p['type'] != 'row']
    d['panels'] = [p for p in d['panels'] if p['id'] != 25]  # Upstream donation banner, not telemetry.
    existing = [p for p in d['panels'] if p['id'] not in specs]
    added = [by_id[id_] for id_ in specs]
    ordered = existing + added
    y = x = height = 0
    for p in ordered:
        width = 24 if p['id'] in (59, 66, 67, 65) else (6 if p['type'] in ('stat', 'gauge', 'piechart', 'histogram') else 12)
        h = 5 if p['type'] in ('stat', 'gauge') else 8
        if x + width > 24:
            y += height; x = height = 0
        p['gridPos'] = {'x': x, 'y': y, 'w': width, 'h': h}
        x += width; height = max(height, h)
    d['panels'] = ordered
    for id_, title in {26: 'Latest recorded heart rate', 28: 'Latest recorded resting heart rate',
                       30: 'Latest recorded daily steps', 32: 'Latest recorded sleep hours',
                       35: 'Recorded daily activity'}.items():
        by_id[id_]['title'] = title
    calories = by_id[44]
    calories['title'] = 'Average daily calories'
    calories['description'] = 'Average recorded active and basal calories per day in the selected range; not workout-only energy.'
    calories.pop('transformations', None)
    calories['targets'] = [{'refId': ref, 'datasource': copy.deepcopy(calories['datasource']),
        'rawQuery': True, 'query': f'SELECT mean("{field}") FROM "DailyStats" WHERE $timeFilter',
        'resultFormat': 'time_series', 'alias': alias} for ref,field,alias in (
            ('A', 'activeKilocalories', 'Active'), ('B', 'bmrKilocalories', 'Basal'))]
    calories['fieldConfig']['defaults']['unit'] = 'suffix:kcal'
    d['templating']['list'] = [v for v in d['templating']['list'] if v['name'] != 'ActivityGPS']
    d['description'] = 'Recorded daily health, movement and sleep trends. Workout/GPS, weight, VO2 max and ConnectIQ watch-charge views are omitted because those measurements are not recorded in this deployment. Body Battery is a wellness estimate, not watch charge.'


def improve(model):
    d = copy.deepcopy(model)
    ps = {p['id']: p for p in walk(d['panels'])}
    uid = d['uid']
    def change(id_, title, query, unit='short', legend='{{instance}}', description='', kind=None):
        replace(ps[id_], title, query if isinstance(query, list) else [(query, legend)], unit, description, kind)
    if uid == 'cloudflared-tunnel':
        sel = '{job=~"$job"}'
        change(12, 'Connector uptime', 'time()-process_start_time_seconds'+sel, 's', description='Age of each currently scraped connector process; resets after restart.')
        change(33, 'File descriptor capacity used', '100*process_open_fds'+sel+'/process_max_fds'+sel, 'percent')
        change(52, 'Configuration push outcomes', [('cloudflared_config_local_config_pushes'+sel, '{{instance}} pushes'), ('cloudflared_config_local_config_pushes_errors'+sel, '{{instance}} errors')], description='Native cumulative configuration pushes and errors since connector start. This is not request latency.')
        change(53, 'RPC client latency — since connector start', [(f'histogram_quantile({q}, sum by(instance,le)(cloudflared_rpc_client_latency_secs_bucket'+sel+'))', '{{instance}} '+name) for q,name in [(0.5,'p50'),(0.95,'p95'),(0.99,'p99')]], 's', description='Quantiles of retained control-plane RPC observations since process start, not latency in the selected rate window. Idle control planes need not issue new RPCs. Resets on restart.')
        change(54, 'Go heap capacity in use', '100*go_memstats_heap_inuse_bytes'+sel+'/(go_memstats_heap_inuse_bytes'+sel+'+go_memstats_heap_idle_bytes'+sel+')', 'percent')
        change(55, 'RPC client observations — since connector start', 'sum by(instance)(cloudflared_rpc_client_latency_secs_count'+sel+')', description='Actual histogram sample count. No origin proxy latency is inferred when its histogram has no observations.')
    elif uid == 'dockhand-overview-v2':
        change(2, 'Updates available', 'dockhand_updates_available', description='Native measured count per environment, including zero. Missing environments are not invented as zero.', legend='{{env}}')
        change(11, 'Containers by state — fleet total', 'sum by(state)(dockhand_containers)', legend='{{state}}', description='Fleet totals for each state emitted by Dockhand. Running counts per environment are shown separately. An absent exited/created series is not a measured zero.')
        change(32, 'Images with scan results', 'dockhand_images_scanned', legend='{{env}}', description='Native number of images with scan results. Zero means no scan results are recorded, not zero vulnerabilities. Scan age is not exported.')
    elif uid == 'nNq1Iw5Gz':
        change(11, 'Number of Projects', 'gitea_projects{job="gitea"}')
    elif uid == 'graylog-kdnlab':
        change(35, 'Failure queue depth', 'gl_failure_queue_size{job="graylog"}', description='Measured current failure queue size. This does not infer a historical scheduler failure count.')
        # Process/JVM names also occur in other jobs in the shared Prometheus.
        import re
        for p in ps.values():
            for t in p.get('targets', []):
                t['expr'] = re.sub(r'\b((?:gl_|jvm_|process_)[a-zA-Z0-9_]+)(\{[^}]*\})?', lambda m: m[0] if 'job=' in (m[2] or '') else m[1]+'{job="graylog"'+(','+m[2][1:] if m[2] else '}'), t.get('expr', ''))
    elif uid == 'F32fd2rfa':
        change(35, 'Media scan outcomes — selected range', 'increase(media_scans{job=~"^$job$"}[$__range])', legend='{{instance}} · success={{success}}', description='Observed scan outcome counters. Missing failure series are not silently converted to a zero failure count.')
    elif uid == 'O6v4rMpizda':
        sel = '{app=~"^$application$"}'
        change(37, 'Database connections opened — selected range', 'sum(increase(django_db_new_connections_total'+sel+'[$__range]))', kind='stat')
        change(31, 'Mean database query time', 'sum(rate(django_db_query_duration_seconds_sum'+sel+'[$__rate_interval]))/sum(rate(django_db_query_duration_seconds_count'+sel+'[$__rate_interval]))', 's', kind='stat', description='Mean observed query duration in the rate window. Cache metrics are not emitted by this exporter.')
        change(17, 'Mean HTTP response size', 'sum(rate(django_http_responses_body_total_bytes_sum'+sel+'[$__rate_interval]))/sum(rate(django_http_responses_body_total_bytes_count'+sel+'[$__rate_interval]))', 'bytes', kind='stat', description='Mean measured response body size. Response status trends remain in the Response Status graph.')
    elif uid == 'rYdddlPWk':
        sel = '{instance="$node",job="$job"}'
        change(325, 'Exporter collector health', 'node_scrape_collector_success'+sel, legend='{{collector}}', description='Measured collector success (1) or failure (0) on this host. Does not require physical fan sensors.')
        change(298, 'Runnable and blocked processes', [('node_procs_running'+sel, 'Runnable'), ('node_procs_blocked'+sel, 'Blocked')])
        change(331, 'Established TCP connections', 'node_netstat_Tcp_CurrEstab'+sel, legend='Established')
        change(297, 'TCP connection opens / second', [('rate(node_netstat_Tcp_ActiveOpens'+sel+'[$__rate_interval])', 'Active opens'), ('rate(node_netstat_Tcp_PassiveOpens'+sel+'[$__rate_interval])', 'Passive opens')], 'ops')
        change(332, 'TCP listen queue drops / second', [('rate(node_netstat_TcpExt_ListenDrops'+sel+'[$__rate_interval])', 'Listen drops'), ('rate(node_netstat_TcpExt_ListenOverflows'+sel+'[$__rate_interval])', 'Listen overflows')], 'ops')
        change(320, 'Socket usage by protocol', [('node_sockstat_TCP_inuse'+sel, 'TCP'), ('node_sockstat_UDP_inuse'+sel, 'UDP'), ('node_sockstat_RAW_inuse'+sel, 'RAW')])
        for p in ps.values():
            if p['type'] == 'row' and 'systemd' in p.get('title', '').lower():
                p['title'] = 'Processes and sockets'
    elif uid == 'jMfvAjxWz':
        # Disjoint wired/wireless scopes respect both device and parent filters.
        scope = 'job="unpoller",site_name="$Site",'
        selectors = ['{'+scope+'wired="true",name=~"$Wired",sw_name=~"$Switch"}', '{'+scope+'wired!="true",name=~"$Wireless",ap_name=~"$AP"}']
        terms = ['rate(unpoller_client_'+direction+'_bytes_total'+s+'[$__rate_interval])' for s in selectors for direction in ('receive','transmit')]
        # Union distinct directions only after each rx+tx pair is added.
        expr = 'topk(10,sum by(name)(('+terms[0]+'+'+terms[1]+') or ('+terms[2]+'+'+terms[3]+')))'
        change(15, 'Top 10 clients by combined throughput', expr, 'Bps', '{{name}}', description='Receive + transmit byte rates, respecting site, wired/wireless client and AP/switch selections. No device-name convention is required.')
    elif uid == '9WaGWZaZk':
        change(45, 'Site internet drops — selected range', 'sum by(site_name)(increase(unpoller_site_intenet_drops_total{site_name="$Site"}[$__range]))', legend='{{site_name}}', description='Native site internet-drop counter (exporter spelling: intenet). Applies to the selected site internet subsystem (www), independently of LAN/WLAN filters. DPI categories are not exported by this deployment.')
    elif uid == 'feiibsx498gsgb':
        garmin(d)
    return d


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('source'); cli.add_argument('output')
    args = cli.parse_args()
    models = json.loads(Path(args.source).read_text())
    for response in models.values():
        response['data']['dashboard'] = improve(response['data']['dashboard'])
    Path(args.output).write_text(json.dumps(models, indent=2)+'\n')
