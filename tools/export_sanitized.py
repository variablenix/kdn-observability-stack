#!/usr/bin/env python3
"""Export dashboard models for publication. Always inspect the resulting diff.

Input: a JSON map of UID -> {data: {dashboard, meta}} API responses.
No authentication or production access is implemented here.
"""
import argparse,copy,json,re
from pathlib import Path

# Explicit file mapping preserves the repository's established paths.
FILES={
 'dockhand-overview-v2':'infrastructure/Dockhand-Environment-Overview.json',
 'cups-print-kdn':'services/CUPS.json','st9brkm':'personal/Minecraft-Bedrock.json',
 'gobot-operations':'services/GoBot-Operations.json','F32fd2rfa':'services/Navidrome.json',
}
IP=re.compile(r'\b(?:\d{1,3}(?:\\{1,2})?\.){3}\d{1,3}\b')


def sanitize(dashboard, bindings=None, redactions=None):
    bindings=bindings or {};redactions=redactions or {}
    d=copy.deepcopy(dashboard);used={};addresses={}
    def text(s):
        for uid,(name,plugin,label) in bindings.items():
            if uid in s:used[name]=(plugin,label);s=s.replace(uid,'${'+name+'}')
        def address(m):
            old=m.group(0);plain=old.replace('\\','')
            if plain in ('0.0.0.0','127.0.0.1'):return old
            addresses.setdefault(plain,'192.0.2.'+str(len(addresses)+1))
            new=addresses[plain]
            if '\\' in old:new=new.replace('.','\\.' if '\\\\' not in old else '\\\\.')
            return new
        s=IP.sub(address,s)
        s=re.sub(r'(?i)(?:[a-z0-9-]+\.)*(?:lab\.)?kdn\.cloud', 'monitoring.example.net',s)
        for old,new in redactions.items():s=s.replace(old,new)
        s=re.sub(r'/Users/[^/\s"<>]+','/workspace',s)
        s=re.sub(r'/home/(?:ak|docker|cupsadmin)(?=/|\b)','/var/lib/monitoring',s)
        s=s.replace('20250413T084245UTC-Other-Lap3','${ActivityGPS}')
        return s
    def walk(x):
        if isinstance(x,str):return text(x)
        if isinstance(x,list):return [walk(v) for v in x]
        if isinstance(x,dict):return {k:walk(v) for k,v in x.items()}
        return x
    d.pop('id',None);d.pop('__inputs',None);d['version']=1
    # Query selections may contain private hosts, MACs, network names or activities.
    for v in d.get('templating',{}).get('list',[]):
        if v.get('type') in ('query','datasource'):
            v['options']=[];v['current']={'text':'All','value':'$__all'} if v.get('includeAll') else {}
    d=walk(d)
    # Remove legacy datasource input names after replacing concrete bindings.
    def refs(x):
        if isinstance(x,dict):
            for k,v in x.items():
                if k=='datasource' and isinstance(v,dict) and v.get('type')=='prometheus' and v.get('uid','').startswith('${DS_'):
                    v['uid']='${DS_PROMETHEUS}';used['DS_PROMETHEUS']=('prometheus','Prometheus')
                refs(v)
        elif isinstance(x,list):
            for v in x:refs(v)
    refs(d)
    d['__inputs']=[{'name':name,'label':label,'type':'datasource','pluginId':plugin,'pluginName':label} for name,(plugin,label) in sorted(used.items())]
    return d


def export(source,root,bindings=None,redactions=None):
    existing={}
    for f in root.glob('*/*.json'):
        try:
            d=json.loads(f.read_text())
            if isinstance(d,dict) and d.get('uid'):existing[d['uid']]=str(f.relative_to(root))
        except (ValueError,OSError):pass
    manifest=[]
    for uid,response in source.items():
        model=response['data']['dashboard'];path=FILES.get(uid) or existing.get(uid)
        if path is None:raise ValueError('No approved output filename for '+uid)
        f=root/path;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(json.dumps(sanitize(model,bindings,redactions),indent=2)+'\n')
        manifest.append({'uid':uid,'file':path,'title':sanitize(model,bindings,redactions)['title']})
    return manifest

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source');p.add_argument('--root',default='.');p.add_argument('--bindings',required=True,help='Private JSON map of source UID to [input name, plugin ID, label]');p.add_argument('--redactions',help='Private JSON map of additional literal replacements');a=p.parse_args()
    manifest=export(json.loads(Path(a.source).read_text()),Path(a.root),json.loads(Path(a.bindings).read_text()),json.loads(Path(a.redactions).read_text()) if a.redactions else {})
    print(json.dumps(manifest,indent=2))
