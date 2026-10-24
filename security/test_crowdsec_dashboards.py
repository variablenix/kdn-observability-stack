"""Offline dashboard invariants; fixtures and exports contain no live telemetry."""
import json
import re
import unittest
from pathlib import Path
import build_crowdsec as builder


class Dashboards(unittest.TestCase):
    def test_generated_exports_are_current(self):
        for name, data in builder.dashboards().items():
            self.assertEqual(json.loads((Path(__file__).parent/name).read_text()), data)

    def test_preserve_existing_urls_and_portable_datasource(self):
        self.assertEqual({d['uid'] for d in builder.dashboards().values()},
                         {'crowdsec-engine', 'e7sWOBVnk', 'kdn-crowdsec-fleet'})
        for d in builder.dashboards().values():
            self.assertEqual(d['templating']['list'][0]['name'], 'DS_PROMETHEUS')
            self.assertEqual(d['templating']['list'][1]['allValue'], '.*')
            self.assertIn('label_values(up', d['templating']['list'][1]['query']['query'])
            for p in d['panels']:
                if p.get('targets'):
                    self.assertEqual(p['datasource'], builder.DS)

    def test_unique_ids_and_nonoverlapping_layouts(self):
        for d in builder.dashboards().values():
            ids = [p['id'] for p in d['panels']]
            self.assertEqual(len(ids), len(set(ids)))
            positions = []
            for p in d['panels']:
                g = p['gridPos']
                self.assertLessEqual(g['x']+g['w'], 24)
                for old in positions:
                    self.assertFalse(g['x'] < old['x']+old['w'] and g['x']+g['w'] > old['x']
                                     and g['y'] < old['y']+old['h'] and g['y']+g['h'] > old['y'])
                positions.append(g)

    def test_tables_prioritize_readable_dimensions_not_exporter_metadata(self):
        for d in builder.dashboards().values():
            for p in d['panels']:
                if p['type'] == 'table':
                    options = p['transformations'][0]['options']
                    self.assertTrue(options['excludeByName']['__name__'])
                    self.assertTrue(options['excludeByName']['instance'])
                    self.assertEqual(options['renameByName']['hostname'], 'Host')

    def test_queries_use_real_families_safe_rates_and_explicit_scoping(self):
        for d in builder.dashboards().values():
            for p in d['panels']:
                for target in p.get('targets', []):
                    q = target['expr']
                    self.assertNotIn('vector(0)', q)
                    self.assertNotIn('cs_bucket_created_total', q)
                    self.assertNotIn('$__interval', q)
                    self.assertNotIn('appsec_', q)
                    self.assertIn('job=', q)
                    if 'cs_lapi_' in q:
                        self.assertIn('job="crowdsec"', q)
                        self.assertNotIn('hostname=~', q)
                    if 'rate(' in q:
                        self.assertIn('[$__rate_interval]', q)
                    if 'increase(' in q:
                        self.assertIn('[$__range]', q)

    def test_public_exports_have_no_private_endpoints_or_local_datasource_ids(self):
        for d in builder.dashboards().values():
            body = json.dumps(d)
            self.assertNotRegex(body, r'\b(?:\d{1,3}\.){3}\d{1,3}\b')
            for private in ('.kdn.cloud', '.kode.im', '/Users/', 'api_key', 'smtp_password'):
                self.assertNotIn(private, body)

    def test_health_is_freshness_guarded_and_coverage_is_not_fabricated(self):
        fleet = builder.fleet()
        for p in fleet['panels']:
            for t in p.get('targets', []):
                if 'crowdsec_health_' in t['expr'] and p['title'] != 'Health snapshot age':
                    self.assertIn('<660', t['expr'])
        notes = json.dumps(builder.insights())
        self.assertIn('sample coverage', notes.lower())
        self.assertIn('not unique attackers', notes)

    def test_overall_status_differentiates_warnings_from_core_outages(self):
        p = next(p for p in builder.fleet()['panels'] if p['title'] == 'Overall operational health')
        mapping = p['fieldConfig']['defaults']['mappings'][0]['options']
        self.assertEqual(mapping['0']['text'], 'CRITICAL')
        self.assertEqual(mapping['1']['text'], 'ATTENTION')
        self.assertEqual(mapping['2']['text'], 'HEALTHY')
        q = p['targets'][0]['expr']
        self.assertIn('entity_healthy', q)
        self.assertIn('machines|bouncers|decisions', q)
        self.assertIn('min(up', q)
        self.assertNotIn('vector(0)', q)


if __name__ == '__main__':
    unittest.main()
