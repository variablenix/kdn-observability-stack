#!/usr/bin/env python3
"""Read-only Immich aggregates for node_exporter's private textfile collector.

No API key, media reads, queue mutations, or database writes are performed.
Account labels are opt-in; filenames, email addresses and locations are never emitted.
"""
import argparse
import datetime as dt
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import time

SQL = r'''
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '5000ms';
SET LOCAL lock_timeout = '1000ms';
SELECT json_build_object(
 'database_bytes',pg_database_size(current_database()),
 'database_connections',(SELECT numbackends FROM pg_stat_database WHERE datname=current_database()),
 'database_deadlocks',(SELECT deadlocks FROM pg_stat_database WHERE datname=current_database()),
 'recent',(SELECT coalesce(json_agg(t),'[]'::json) FROM (
   SELECT u.id AS account_id,u.name AS account,a.type AS media_type,w.period_label AS window,count(*) AS assets,coalesce(sum(e."fileSizeInByte"),0) AS bytes
   FROM asset a JOIN "user" u ON u.id=a."ownerId" LEFT JOIN asset_exif e ON e."assetId"=a.id
   CROSS JOIN (VALUES ('24h',interval '1 day'),('7d',interval '7 days')) w(period_label,period)
   WHERE u."deletedAt" IS NULL AND a."deletedAt" IS NULL AND a.status='active' AND a."createdAt">now()-w.period
   GROUP BY u.id,u.name,a.type,w.period_label) t),
 'users',(SELECT count(*) FROM "user" WHERE "deletedAt" IS NULL AND status='active'),
 'assets',(SELECT coalesce(json_agg(t),'[]'::json) FROM (
   SELECT u.id AS account_id,u.name AS account,a.type AS media_type,
    CASE WHEN a."deletedAt" IS NOT NULL OR a.status='trashed' THEN 'trashed' ELSE 'active' END AS state,
    count(*) AS assets,coalesce(sum(e."fileSizeInByte"),0) AS bytes,
    count(*) FILTER (WHERE e."fileSizeInByte" IS NULL) AS missing_size
   FROM asset a JOIN "user" u ON u.id=a."ownerId"
   LEFT JOIN asset_exif e ON e."assetId"=a.id
   WHERE u."deletedAt" IS NULL
   GROUP BY u.id,u.name,a.type,4) t),
 'unique_originals',(SELECT count(*) FROM (SELECT a.checksum,a."checksumAlgorithm" FROM asset a JOIN "user" u ON u.id=a."ownerId" WHERE a."deletedAt" IS NULL AND a.status='active' AND u."deletedAt" IS NULL GROUP BY a.checksum,a."checksumAlgorithm") t),
 'unique_bytes',(SELECT coalesce(sum(bytes),0) FROM (
   SELECT max(e."fileSizeInByte") AS bytes FROM asset a JOIN "user" u ON u.id=a."ownerId" LEFT JOIN asset_exif e ON e."assetId"=a.id
   WHERE a."deletedAt" IS NULL AND a.status='active' AND u."deletedAt" IS NULL GROUP BY a.checksum,a."checksumAlgorithm") t),
 'gifs',(SELECT count(*) FROM asset WHERE "deletedAt" IS NULL AND status='active' AND lower("originalFileName") LIKE '%.gif'),
 'external_assets',(SELECT count(*) FROM asset WHERE "deletedAt" IS NULL AND status='active' AND "isExternal"),
 'albums',(SELECT count(*) FROM album WHERE "deletedAt" IS NULL),
 'people',(SELECT count(DISTINCT "personGroupId") FROM person),
 'faces',(SELECT count(*) FROM asset_face f JOIN asset a ON a.id=f."assetId" WHERE a."deletedAt" IS NULL AND a.status='active'),
 'external_libraries',(SELECT count(*) FROM library WHERE "deletedAt" IS NULL),
 'shared_links',(SELECT count(*) FROM shared_link WHERE "expiresAt" IS NULL OR "expiresAt">now()),
 'sessions',(SELECT count(*) FROM session WHERE "expiresAt" IS NULL OR "expiresAt">now()),
 'missing_metadata',(SELECT count(*) FROM asset a LEFT JOIN asset_job_status j ON j."assetId"=a.id WHERE a."deletedAt" IS NULL AND a.status='active' AND j."metadataExtractedAt" IS NULL),
 'missing_preview',(SELECT count(*) FROM asset a WHERE a."deletedAt" IS NULL AND a.status='active' AND NOT EXISTS(SELECT 1 FROM asset_file f WHERE f."assetId"=a.id AND f.type='preview'))
);
COMMIT;
'''

QUEUES = ('thumbnailGeneration','metadataExtraction','videoConversion','faceDetection',
          'facialRecognition','smartSearch','duplicateDetection','backgroundTask',
          'storageTemplateMigration','migration','search','sidecar','library',
          'notifications','backupDatabase','ocr','workflow','integrityCheck','editor')
QUEUE_LUA = r'''
local out={}
local found=0
for i=2,#ARGV do
 local base=ARGV[1]..':'..ARGV[i]..':'
 found=found+redis.call('EXISTS',base..'meta')
 table.insert(out,{ARGV[i],redis.call('LLEN',base..'active'),redis.call('LLEN',base..'wait'),
  redis.call('ZCARD',base..'prioritized'),redis.call('ZCARD',base..'delayed'),
  redis.call('ZCARD',base..'failed'),redis.call('ZCARD',base..'completed'),
  redis.call('LLEN',base..'paused'),redis.call('ZCARD',base..'waiting-children'),
  tonumber(redis.call('HGET',base..'meta','paused')) or 0})
end
if found~=(#ARGV-1) then return redis.error_reply('Incomplete queue metadata') end
return cjson.encode(out)
'''
QUEUE_STATES = ('active','waiting','prioritized','delayed','failed','completed','paused','waiting_children')


def run(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=25, check=True)
    return result.stdout.strip()


def timestamp(value):
    if not value:
        return None
    parsed = dt.datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Timezone required')
    return parsed.timestamp()


def escape(value):
    return str(value).replace('\\','\\\\').replace('\n','\\n').replace('"','\\"')


class Metrics:
    def __init__(self, host):
        self.host = host
        self.values = {}

    def add(self, name, value, labels=None):
        value = float(value)
        if not math.isfinite(value):
            raise ValueError('Non-finite metric')
        labels = {'immich_host':self.host, **(labels or {})}
        key = (name, tuple(sorted(labels.items())))
        self.values[key] = self.values.get(key,0) + value

    def render(self):
        lines=[]
        previous=None
        for (name,labels),value in sorted(self.values.items()):
            if name!=previous:
                lines.append('# HELP '+name+' Immich aggregate: '+name.removeprefix('immich_').replace('_',' ')+'.')
                lines.append('# TYPE '+name+' gauge')
                previous=name
            labeltext=','.join(k+'="'+escape(v)+'"' for k,v in labels)
            lines.append(name+'{'+labeltext+'} '+format(value,'.15g'))
        return '\n'.join(lines)+'\n'


def inventory(metrics, data, accounts=False):
    for key in ('users','unique_originals','unique_bytes','gifs','external_assets',
                'albums','people','faces','external_libraries','shared_links','sessions',
                'missing_metadata','missing_preview','database_bytes','database_connections','database_deadlocks'):
        metrics.add('immich_inventory_'+key, data[key])
    # Emit both media types even when one has no assets, from a successful SQL inventory.
    for media in ('IMAGE','VIDEO'):
        for state in ('active','trashed'):
            labels={'media_type':media,'state':state}
            metrics.add('immich_inventory_assets',0,labels)
            metrics.add('immich_inventory_original_bytes',0,labels)
            metrics.add('immich_inventory_missing_size',0,labels)
    for row in data['assets']:
        labels={'media_type':row['media_type'],'state':row['state']}
        metrics.add('immich_inventory_assets',row['assets'],labels)
        metrics.add('immich_inventory_original_bytes',row['bytes'],labels)
        metrics.add('immich_inventory_missing_size',row['missing_size'],labels)
        if accounts:
            labels.update(account=row['account'],account_id=row['account_id'])
            metrics.add('immich_account_assets',row['assets'],labels)
            metrics.add('immich_account_original_bytes',row['bytes'],labels)



    account_rows={(r['account_id'],r['account']) for r in data['assets']}
    for window in ('24h','7d'):
        for media in ('IMAGE','VIDEO'):
            labels={'window':window,'media_type':media}
            metrics.add('immich_recent_assets',0,labels)
            metrics.add('immich_recent_bytes',0,labels)
            if accounts:
                for account_id,account in account_rows:
                    account_labels={**labels,'account_id':account_id,'account':account}
                    metrics.add('immich_account_recent_assets',0,account_labels)
                    metrics.add('immich_account_recent_bytes',0,account_labels)
    for row in data['recent']:
        labels={'window':row['window'],'media_type':row['media_type']}
        metrics.add('immich_recent_assets',row['assets'],labels)
        metrics.add('immich_recent_bytes',row['bytes'],labels)
        if accounts:
            labels.update(account=row['account'],account_id=row['account_id'])
            metrics.add('immich_account_recent_assets',row['assets'],labels)
            metrics.add('immich_account_recent_bytes',row['bytes'],labels)


def queue_metrics(metrics, rows):
    if {r[0] for r in rows} != set(QUEUES):
        raise ValueError('Incomplete queue inventory')
    for row in rows:
        if len(row)!=10:
            raise ValueError('Invalid queue shape')
        for state,value in zip(QUEUE_STATES,row[1:9]):
            metrics.add('immich_queue_jobs',value,{'queue':row[0],'state':state})
        metrics.add('immich_queue_paused',row[9],{'queue':row[0]})


def state_file(root, name):
    value=json.loads((root/name).read_text())
    if not isinstance(value,dict):
        raise ValueError('Invalid status object')
    return value


def status_metrics(metrics, root):
    sources={'primary':'status.json','replica':'unas-status.json','export':'media-export-status.json',
             'cloud':'cloud-media-status.json','daily_report':'daily-report-status.json'}
    states={'success':1,'complete':1,'completed':1,'running':2,'deferred':3,'failed':0,'error':0}
    loaded={}
    for component,name in sources.items():
        status=state_file(root,name);loaded[component]=status
        metrics.add('immich_backup_workflow_state',states.get(status.get('state'),-1),{'component':component})
        ts=timestamp(status.get('last_success_utc'))
        if ts is not None:
            metrics.add('immich_backup_last_success_timestamp_seconds',ts,{'component':component})
    cloud=loaded['cloud'];export=loaded['export']
    for source,keys in ((cloud,('expected_unique_files','verified_unique_files','pending_files')),
                        (export,('source_files','canonical_files','unique_bytes','duplicate_paths_avoided','errors'))):
        for key in keys:
            value=source[key]
            metrics.add('immich_'+('cloud_' if source is cloud else 'export_')+key,len(value) if isinstance(value,list) else value)
    cloud_ts=timestamp(cloud.get('time_utc'))
    export_ts=timestamp(export.get('last_success_utc'))
    if cloud_ts is not None:metrics.add('immich_cloud_verification_timestamp_seconds',cloud_ts)
    current=(cloud.get('source_export_complete') is True and cloud.get('export_scope')=='current-source-export'
             and cloud.get('pending_files')==0 and cloud.get('expected_unique_files')==cloud.get('verified_unique_files')
             and not export.get('errors') and cloud_ts is not None and export_ts is not None and cloud_ts>=export_ts)
    metrics.add('immich_cloud_current_source_verified',int(current))
    health=state_file(root,'health-monitor-status.json')
    metrics.add('immich_backup_health_issues',health['active_issue_count'])
    metrics.add('immich_dropbox_free_bytes',health['dropbox_free_bytes'])
    metrics.add('immich_backup_health_timestamp_seconds',timestamp(health['checked_utc']))



def container_metrics(metrics, config):
    services={'server':config.get('server_container','immich_server'),
              'machine_learning':config.get('machine_learning_container','immich_machine_learning'),
              'postgres':config.get('postgres_container','immich_postgres'),
              'redis':config.get('redis_container','immich_redis')}
    template='[{{json .Name}},{{json .State}},{{json .RestartCount}},{{json .Config.Image}},{{json (index .Config.Labels "org.opencontainers.image.version")}}]'
    rows=[json.loads(line) for line in run(['docker','inspect','--format',template,*services.values()]).splitlines()]
    indexed={row[0].lstrip('/'):row for row in rows}
    for service,name in services.items():
        _,state,restarts,image,version=indexed[name]
        labels={'service':service}
        metrics.add('immich_container_running',int(state['Running']),labels)
        health=state.get('Health',{}).get('Status')
        metrics.add('immich_container_health',{'healthy':1,'unhealthy':0,'starting':2}.get(health,-1),labels)
        metrics.add('immich_container_restarts',restarts,labels)
        started=timestamp(state.get('StartedAt'))
        if started and started>0:metrics.add('immich_container_start_timestamp_seconds',started,labels)
        metrics.add('immich_container_image_info',1,{**labels,'image':image,'version':version or 'not-labelled'})


def collect(config):
    started=time.time();result=Metrics(config['immich_host']);failed=[]
    def component(name, function):
        # A component commits its samples only after the entire read succeeds.
        temporary=Metrics(config['immich_host'])
        try:
            function(temporary)
            result.values.update(temporary.values)
            result.add('immich_collector_timestamp_seconds',time.time(),{'component':name})
            result.add('immich_collector_success',1,{'component':name})
        except Exception as exc:
            failed.append(name)
            result.add('immich_collector_success',0,{'component':name})
            print(name+' collection failed: '+type(exc).__name__,file=__import__('sys').stderr)
    component('inventory',lambda m:inventory(m,json.loads(run([
        'docker','exec',config.get('postgres_container','immich_postgres'),'psql','-XqAt',
        '-v','ON_ERROR_STOP=1','-U',config.get('database_user','postgres'),'-d',config.get('database','immich'),'-c',SQL
    ])),config.get('include_account_labels',False)))
    component('queues',lambda m:queue_metrics(m,json.loads(run([
        'docker','exec',config.get('redis_container','immich_redis'),'redis-cli','--raw','-e','EVAL',QUEUE_LUA,'0',
        config.get('queue_prefix','immich_bull'),*QUEUES
    ]))))
    component('backup',lambda m:status_metrics(m,Path(config['backup_state_directory'])))
    component('containers',lambda m:container_metrics(m,config))
    result.add('immich_collector_duration_seconds',time.time()-started)
    return result.render(),failed


def atomic_write(path, text):
    path=Path(path)
    with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,prefix='.'+path.name+'.',delete=False) as f:
        temporary=Path(f.name)
        try:
            f.write(text);f.flush();os.fsync(f.fileno());os.fchmod(f.fileno(),0o644)
            os.replace(temporary,path)
        finally:
            temporary.unlink(missing_ok=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    config=json.loads(Path(args.config).read_text())
    text,failed=collect(config)
    atomic_write(args.output,text)
    return 1 if failed else 0


if __name__=='__main__':
    raise SystemExit(main())
