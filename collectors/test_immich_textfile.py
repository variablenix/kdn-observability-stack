import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('collector',Path(__file__).with_name('immich_textfile.py'))
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)


def inventory_fixture():
    d={k:0 for k in ('users','unique_originals','unique_bytes','gifs','external_assets','albums',
        'people','faces','external_libraries','shared_links','sessions','missing_metadata','missing_preview','database_bytes','database_connections','database_deadlocks')}
    d['users']=2
    d['recent']=[]
    d['assets']=[{'account_id':str(i),'account':'Example','media_type':'IMAGE','state':'active',
                  'assets':i,'bytes':i*100,'missing_size':0} for i in (1,2)]
    return d


class InventoryTests(unittest.TestCase):
    def test_accounts_do_not_double_count_totals_or_collide(self):
        m=c.Metrics('example');c.inventory(m,inventory_fixture(),True)
        values=[v for (name,labels),v in m.values.items() if name=='immich_inventory_assets' and ('media_type','IMAGE') in labels and ('state','active') in labels]
        self.assertEqual(values,[3])
        self.assertEqual(sum(name=='immich_account_assets' for name,labels in m.values),2)

    def test_recent_additions_do_not_double_count_account_rows(self):
        data=inventory_fixture();data['recent']=[{'account_id':str(i),'account':'Example','window':'24h','media_type':'IMAGE','assets':i,'bytes':i*100} for i in (1,2)]
        m=c.Metrics('example');c.inventory(m,data,True)
        text=m.render()
        self.assertIn('immich_recent_assets{immich_host="example",media_type="IMAGE",window="24h"} 3',text)
        self.assertIn('immich_recent_bytes{immich_host="example",media_type="IMAGE",window="24h"} 300',text)
        self.assertEqual(sum(name=='immich_account_recent_assets' for name,labels in m.values),8)

    def test_container_without_healthcheck_is_not_claimed_healthy(self):
        state={'Running':True,'StartedAt':'2026-01-01T00:00:00Z'}
        rows='\n'.join(json.dumps(['/immich_'+n,state,0,'example:v1',None]) for n in ('server','machine_learning','postgres','redis'))
        m=c.Metrics('example')
        with patch.object(c,'run',return_value=rows):c.container_metrics(m,{})
        self.assertIn('immich_container_health{immich_host="example",service="redis"} -1',m.render())
        self.assertIn('immich_container_running{immich_host="example",service="redis"} 1',m.render())

    def test_account_labels_are_absent_by_default(self):
        m=c.Metrics('example');c.inventory(m,inventory_fixture())
        self.assertNotIn('account=',m.render());self.assertNotIn('account_id=',m.render())

    def test_empty_media_type_is_real_zero_after_successful_inventory(self):
        m=c.Metrics('example');c.inventory(m,inventory_fixture(),True)
        self.assertIn('immich_inventory_assets{immich_host="example",media_type="VIDEO",state="active"} 0',m.render())

    def test_label_escaping_and_nonfinite_rejection(self):
        m=c.Metrics('example');m.add('test',1,{'label':'quote"\\\n'})
        self.assertIn('label="quote\\"\\\\\\n"',m.render())
        with self.assertRaises(ValueError):m.add('test',float('nan'))

    def test_incomplete_queue_inventory_fails(self):
        with self.assertRaises(ValueError):c.queue_metrics(c.Metrics('example'),[])

    def test_failed_inventory_omits_old_counts_and_records_failure(self):
        with patch.object(c,'run',side_effect=RuntimeError),patch.object(c,'status_metrics',side_effect=RuntimeError):
            text,failed=c.collect({'immich_host':'example','backup_state_directory':'/nonexistent'})
        self.assertEqual(set(failed),{'inventory','queues','backup','containers'})
        self.assertNotIn('immich_inventory_assets{',text)
        self.assertIn('immich_collector_success{component="inventory",immich_host="example"} 0',text)
        self.assertNotIn('immich_collector_timestamp_seconds{',text)


class BackupTests(unittest.TestCase):
    def status_fixture(self, root):
        for name in ('status.json','unas-status.json','daily-report-status.json'):
            (root/name).write_text(json.dumps({'state':'deferred','last_success_utc':'2026-01-01T00:00:00Z'}))
        export={'state':'success','last_success_utc':'2026-01-02T00:00:00Z','source_files':2,
                'canonical_files':2,'unique_bytes':200,'duplicate_paths_avoided':0,'errors':[]}
        cloud={'state':'success','last_success_utc':'2026-01-01T00:00:00Z',
               'time_utc':'2026-01-01T00:00:00Z','expected_unique_files':2,
               'verified_unique_files':2,'pending_files':0,'source_export_complete':True,
               'export_scope':'current-source-export'}
        (root/'media-export-status.json').write_text(json.dumps(export))
        (root/'cloud-media-status.json').write_text(json.dumps(cloud))
        (root/'health-monitor-status.json').write_text(json.dumps({'active_issue_count':0,
            'dropbox_free_bytes':1000,'checked_utc':'2026-01-02T00:00:00Z'}))
        return cloud

    def test_old_cloud_check_cannot_verify_newer_export(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.status_fixture(root);m=c.Metrics('example');c.status_metrics(m,root)
            self.assertIn('immich_cloud_current_source_verified{immich_host="example"} 0',m.render())
            self.assertIn('immich_backup_workflow_state{component="primary",immich_host="example"} 3',m.render())

    def test_cleanup_capture_is_not_current_source_coverage(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);cloud=self.status_fixture(root)
            cloud.update(time_utc='2026-01-03T00:00:00Z',export_scope='initial-cleanup-capture')
            (root/'cloud-media-status.json').write_text(json.dumps(cloud))
            m=c.Metrics('example');c.status_metrics(m,root)
            self.assertIn('immich_cloud_current_source_verified{immich_host="example"} 0',m.render())

    def test_atomic_output_has_complete_content(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'example.prom';p.write_text('old')
            c.atomic_write(p,'new\n');self.assertEqual(p.read_text(),'new\n')
            self.assertEqual(list(Path(d).iterdir()),[p])


if __name__=='__main__':unittest.main()
