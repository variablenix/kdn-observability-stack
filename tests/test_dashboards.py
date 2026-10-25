import importlib.util,json,re,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def module(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
builder=module(ROOT/'builders/immich.py','immich_builder')
exporter=module(ROOT/'tools/export_sanitized.py','sanitizer')
auditor=module(ROOT/'tools/audit_dashboards.py','auditor')
class DashboardTests(unittest.TestCase):
 def test_immich_export_is_reproducible_and_has_graphs(self):
  d=builder.build();self.assertEqual(d,json.loads((ROOT/'services/Immich.json').read_text()))
  titles={p['title'] for p in d['panels'] if p['type']=='timeseries'}
  self.assertTrue({'Photo and video inventory','Inventory by account','Original size by account over time'}<=titles)
 def test_audit_regex_interpolation_preserves_valid_promql_escaping(self):
  text=auditor.interpolate('up{instance=~"$node"}',{'node':{'value':['192.0.2.1:9100'],'multi':True,'all':'.*'}})
  self.assertEqual(text,'up{instance=~"192\\\\.0\\\\.2\\\\.1:9100"}')
  self.assertEqual(auditor.interpolate('$node',{'node':{'value':'$__all','multi':True,'all':'.*'}}),'.*')

 def test_immich_layout_has_no_overlaps(self):
  d=builder.build();ids=[p['id'] for p in d['panels']];self.assertEqual(len(ids),len(set(ids)))
  for i,a in enumerate(d['panels']):
   for b in d['panels'][i+1:]:
    x=a['gridPos'];y=b['gridPos'];self.assertFalse(x['x']<y['x']+y['w'] and y['x']<x['x']+x['w'] and x['y']<y['y']+y['h'] and y['y']<x['y']+x['h'],(a['title'],b['title']))
 def test_sanitization_removes_query_selections_and_preserves_query_macros(self):
  source={'uid':'example','id':42,'version':7,'panels':[{'datasource':{'type':'prometheus','uid':'private-prom'},'targets':[{'expr':'up{instance="10.20.30.40:9100"} and up{instance=~"10\\\\.20\\\\.30\\\\.40:9100"}'}]}],'templating':{'list':[{'name':'host','type':'query','current':{'value':'Private machine'},'options':[{'value':'Private machine'}]}]}}
  result=exporter.sanitize(source,{'private-prom':['DS_PROMETHEUS','prometheus','Prometheus']})
  text=json.dumps(result);self.assertNotIn('Private machine',text);self.assertNotIn('private-prom',text);self.assertNotIn('10.20',text)
  self.assertIn('${DS_PROMETHEUS}',text);self.assertIn('192.0.2.1',text);self.assertEqual(result['version'],1)
 def test_dashboard_models_and_datasource_inputs_are_valid(self):
  count=0
  for folder in ('services','infrastructure','security','containers','unifi','personal'):
   for f in (ROOT/folder).glob('*.json'):
    d=json.loads(f.read_text());self.assertIsInstance(d,dict,f);self.assertTrue(d.get('uid'),f);self.assertIsInstance(d.get('panels'),list,f);count+=1
    declared={v['name'] for v in d.get('__inputs',[])}|{v['name'] for v in d.get('templating',{}).get('list',[])}
    for name in re.findall(r'\$\{(DS_[A-Za-z0-9_-]+)\}',json.dumps(d)):self.assertIn(name,declared,(f,name))
  self.assertEqual(count,32)
if __name__=='__main__':unittest.main()
