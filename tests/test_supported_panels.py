"""Regression checks for unsupported metrics and misleading empty states."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('supported', ROOT/'builders/supported_panels.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def models():
    for folder in ('services', 'infrastructure', 'security', 'containers', 'unifi', 'personal'):
        for path in (ROOT/folder).glob('*.json'):
            yield json.loads(path.read_text())


class SupportedPanels(unittest.TestCase):
    def setUp(self):
        self.models = {d['uid']: d for d in models()}

    def test_reconciliation_is_idempotent_and_keeps_urls(self):
        for uid, d in self.models.items():
            revised = builder.improve(d)
            self.assertEqual(d, revised, uid)
            self.assertEqual(revised['uid'], uid)

    def test_dockhand_zero_is_not_filtered_and_scanning_is_not_assumed(self):
        d = self.models['dockhand-overview-v2']
        p = {p['id']: p for p in builder.walk(d['panels'])}
        self.assertEqual(p[2]['targets'][0]['expr'], 'dockhand_updates_available')
        self.assertEqual(p[11]['targets'][0]['expr'], 'sum by(state)(dockhand_containers)')
        self.assertIn('no scan results', p[32]['description'])
        self.assertNotIn('scan_oldest_age', json.dumps(d))

    def test_garmin_sample_time_uses_timestamp_not_bpm_and_keeps_gaps(self):
        d = self.models['feiibsx498gsgb']
        p = {p['id']: p for p in d['panels']}
        self.assertEqual(p[46]['type'], 'stat')
        self.assertEqual(p[46]['options']['reduceOptions']['fields'], 'Time')
        self.assertEqual(p[46]['transformations'][-1]['options']['include']['names'], ['Time'])
        for id_ in (48, 53, 54, 43, 50, 49, 45, 61, 57, 47):
            for t in p[id_]['targets']:
                self.assertIn('fill(null)', t['query'])
                self.assertNotIn('fill(0)', t['query'])
        queries = json.dumps([p.get('targets', []) for p in d['panels']])
        for unavailable in ('ActivityGPS', 'ActivitySummary', 'VO2_Max', 'BodyComposition'):
            self.assertNotIn(unavailable, queries, unavailable)
        # BodyBatteryLevel is wellness data; BatteryLevel was watch charge.
        self.assertNotIn('"measurement": "BatteryLevel"', queries)

    def test_garmin_layout_is_nonoverlapping(self):
        ps = self.models['feiibsx498gsgb']['panels']
        self.assertEqual(len({p['id'] for p in ps}), len(ps))
        for i, a in enumerate(ps):
            x = a['gridPos']
            self.assertLessEqual(x['x']+x['w'], 24)
            for b in ps[i+1:]:
                y = b['gridPos']
                self.assertFalse(x['x'] < y['x']+y['w'] and y['x'] < x['x']+x['w']
                                 and x['y'] < y['y']+y['h'] and y['y'] < x['y']+x['h'])

    def test_shared_process_metrics_are_job_scoped(self):
        d = self.models['graylog-kdnlab']
        for p in builder.walk(d['panels']):
            for t in p.get('targets', []):
                self.assertIn('job="graylog"', t['expr'])

    def test_tunnel_control_plane_window_is_explicit(self):
        d = self.models['cloudflared-tunnel']
        p = next(p for p in d['panels'] if p['id'] == 53)
        self.assertIn('since connector start', p['title'])
        for t in p['targets']:
            self.assertIn('histogram_quantile', t['expr'])
            self.assertNotIn('rate(', t['expr'])
        self.assertNotIn('tunnel_timer_retries', json.dumps(d))

    def test_client_topk_respects_wired_and_wireless_scopes(self):
        p = next(p for p in self.models['jMfvAjxWz']['panels'] if p['id'] == 15)
        q = p['targets'][0]['expr']
        for scope in ('$Site', '$AP', '$Switch', '$Wired', '$Wireless'):
            self.assertIn(scope, q)
        self.assertIn('wired="true"', q)
        self.assertIn('wired!="true"', q)
        self.assertNotIn('camera', q)


if __name__ == '__main__':
    unittest.main()
