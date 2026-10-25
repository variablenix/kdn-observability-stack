#!/usr/bin/env python3
import collections
import copy
import json
import re
import time
from pathlib import Path
import argparse,base64,concurrent.futures,datetime,math,os,urllib.request,urllib.error,urllib.parse
URL='';HEADERS={};SOURCES={};BY_NAME={}
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None
OPENER=urllib.request.build_opener(NoRedirect)
def request(task):
    data=json.dumps(task['body']).encode() if 'body' in task else None
    try:
        r=OPENER.open(urllib.request.Request(URL+task['path'],data=data,headers=HEADERS,method=task.get('method','GET')),timeout=60)
        with r:body=json.load(r);status=r.status
    except urllib.error.HTTPError as error:
        # Do not persist backend error bodies: they can include private query text.
        return {'status':error.code,'data':{}}
    except (OSError,ValueError):return {'status':0,'data':{}}
    if task.get('summarize'):
        results={}
        for ref,item in body.get('results',{}).items():
            finite=text=0
            for frame in item.get('frames',[]):
                for field,values in zip(frame.get('schema',{}).get('fields',[]),frame.get('data',{}).get('values',[])):
                    if field.get('type')=='time':continue
                    finite+=sum(isinstance(v,(int,float)) and math.isfinite(v) for v in values)
                    text+=sum(isinstance(v,str) and bool(v) for v in values)
            results[ref]={'finite':finite,'text':text,'error':bool(item.get('error')),'status':item.get('status')}
        body=results
    return {'status':status,'data':body}
def call(tasks):
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:return list(pool.map(request,tasks))



def panels(items):
    for p in items:
        if p.get('targets') and p.get('type') not in ('row','text'):
            yield p
        yield from panels(p.get('panels',[]))


def variables(d):
    out = {'__rate_interval':'5m','__interval':'1m','__range':'3h',
           '__range_s':'10800','__interval_ms':'60000', '__from':str(int((time.time()-10800)*1000)),
           '__to':str(int(time.time()*1000)), '__auto_interval_inter':'1m'}
    for v in d.get('templating',{}).get('list',[]):
        val = v.get('current',{}).get('value')
        if v['type']=='datasource':
            if isinstance(val,list):val=val[0] if val else ''
            if val not in SOURCES:
                val = next((s['uid'] for s in SOURCES.values() if s['type']==v.get('query')), val)
        if val is None or val=='':
            if v.get('includeAll'):val='$__all'
            elif v['type']=='constant':val=v.get('query','')
            else:val=''
        if val=='$__auto':val='1m'
        out[v['name']]={'value':val,'all':v.get('allValue') or '.*','multi':v.get('multi') or v.get('includeAll')}
    return out


def interpolate(text,vs,kind='prometheus'):
    if not isinstance(text,str):return text
    def replace(m):
        name=m.group(1) or m.group(3);fmt=m.group(2)
        if name not in vs:return m.group(0)
        x=vs[name]
        if not isinstance(x,dict):return str(x)
        value=x['value'];all_value=value=='$__all' or isinstance(value,list) and '$__all' in value
        if all_value:return x['all']
        vals=value if isinstance(value,list) else [value]
        if fmt in ('raw','csv'):return ','.join(str(v) for v in vals)
        if fmt=='json':return json.dumps(value)
        if fmt=='doublequote':return ','.join(json.dumps(str(v)) for v in vals)
        if fmt=='singlequote':return ','.join("'"+str(v).replace("'","\\'")+"'" for v in vals)
        if fmt=='regex' or x['multi']:
            escaped=[re.escape(str(v)).replace(r'\ ', ' ').replace(r'\-', '-') for v in vals]
            if kind=='prometheus':escaped=[s.replace('\\','\\\\') for s in escaped]
            return '('+'|'.join(escaped)+')' if len(escaped)>1 else escaped[0]
        return str(value)
    return re.sub(r'\$\{([A-Za-z_][A-Za-z0-9_]*)(?::([^}]+))?\}|\$([A-Za-z_][A-Za-z0-9_]*)',replace,text)


def deep_interpolate(x,vs,kind):
    if isinstance(x,str):return interpolate(x,vs,kind)
    if isinstance(x,list):return [deep_interpolate(v,vs,kind) for v in x]
    if isinstance(x,dict):return {k:deep_interpolate(v,vs,kind) for k,v in x.items()}
    return x


def datasource(target,panel,vs):
    ds=target.get('datasource') or panel.get('datasource') or {'uid':next((s['uid'] for s in SOURCES.values() if s.get('isDefault')),next(iter(SOURCES),''))}
    if isinstance(ds,str):ds={'uid':ds}
    uid=interpolate(ds.get('uid',''),vs)
    source=SOURCES.get(uid) or BY_NAME.get(uid)
    return {'uid':uid,'type':ds.get('type') or (source or {}).get('type','prometheus')}


def run(dashboards,output):
    tasks=[];records=[]
    now=int(time.time()*1000)
    for uid,response in dashboards.items():
        d=response['data']['dashboard'];vs=variables(d)
        match=re.fullmatch(r'now-(\d+)([smhdw])',d.get('time',{}).get('from','now-3h'))
        duration=min(2592000,max(900,int(match[1])*{'s':1,'m':60,'h':3600,'d':86400,'w':604800}[match[2]])) if match else 10800
        interval=max(60000,duration*1000//180)
        vs.update(__interval=str(max(1,interval//1000))+'s',__range=str(duration)+'s',__range_s=str(duration))
        for panel in panels(d.get('panels',[])):
            targets=[]
            for original in panel['targets']:
                if original.get('hide'):continue
                ds=datasource(original,panel,vs)
                t=deep_interpolate(copy.deepcopy(original),vs,ds['type']);t['datasource']=ds
                t.setdefault('refId','A');t.setdefault('maxDataPoints',180);t.setdefault('intervalMs',interval)
                targets.append(t)
            if not targets:continue
            tasks.append({'path':'/api/ds/query','method':'POST','body':{'from':str(now-duration*1000),'to':str(now),'queries':targets},'summarize':True,'timeout':45})
            records.append({'uid':uid,'dashboard':d['title'],'panel_id':panel.get('id'),'title':panel.get('title'),'type':panel.get('type'),'queries':targets})
    print('Auditing panels:',len(tasks),flush=True)
    results=[]
    for start in range(0,len(tasks),40):
        results.extend(call(tasks[start:start+40]))
        print('Completed:',min(start+40,len(tasks)),flush=True)
    for record,result in zip(records,results):
        record.pop('queries',None)
        record['result']=result
        frames=result.get('data',{})
        if result['status']!=200 or any(r.get('error') for r in frames.values() if isinstance(r,dict)):
            record['state']='error'
        elif any(r.get('finite',0) or r.get('text',0) for r in frames.values()):record['state']='data'
        else:record['state']='empty'
    path=Path(output);path.write_text(json.dumps({'checked_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'panels':records},indent=2));path.chmod(0o600)
    counts=collections.defaultdict(collections.Counter)
    for r in records:counts[r['dashboard']][r['state']]+=1
    print(json.dumps(counts,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Read and audit saved Grafana dashboard queries. Results contain counts, not metric values or query bodies. This is a backend audit, not a rendering test. Rate windows are evaluated at 5m.')
    parser.add_argument('--url',required=True);parser.add_argument('--org-id',default='1');parser.add_argument('--input',help='Optional candidate API-model JSON map');parser.add_argument('--output',default='audit-private.json');parser.add_argument('--allow-http',action='store_true')
    args=parser.parse_args();URL=args.url.rstrip('/')
    parsed=urllib.parse.urlparse(URL)
    if parsed.scheme not in ('http','https') or parsed.username or parsed.password:parser.error('Use an HTTP(S) base URL without embedded credentials')
    if parsed.scheme=='http' and not args.allow_http:parser.error('HTTPS required unless --allow-http is explicitly selected for a trusted private endpoint')
    if os.environ.get('GRAFANA_TOKEN'):auth='Bearer '+os.environ['GRAFANA_TOKEN']
    else:auth='Basic '+base64.b64encode((os.environ['GRAFANA_USER']+':'+os.environ['GRAFANA_PASSWORD']).encode()).decode()
    HEADERS={'Authorization':auth,'X-Grafana-Org-Id':args.org_id,'Content-Type':'application/json'}
    response=request({'path':'/api/datasources'})
    if response['status']!=200:raise SystemExit('Cannot read data sources: HTTP '+str(response['status']))
    SOURCES={s['uid']:s for s in response['data']};BY_NAME={s['name']:s for s in SOURCES.values()}
    if args.input:dashboards=json.loads(Path(args.input).read_text())
    else:
        response=request({'path':'/api/search?limit=1000'})
        if response['status']!=200:raise SystemExit('Cannot list dashboards')
        ids=[s['uid'] for s in response['data'] if s['type']=='dash-db']
        dashboards=dict(zip(ids,call([{'path':'/api/dashboards/uid/'+uid} for uid in ids])))
    if any(r.get('status',200)!=200 for r in dashboards.values()):raise SystemExit('Some dashboard reads failed; audit is incomplete')
    run(dashboards,args.output)
