#!/usr/bin/env python3
"""Build the portable Immich dashboard; render with a deployment's Prometheus UID."""
import argparse,json
from pathlib import Path


def build(ds='${DS_PROMETHEUS}'):
    datasource={'type':'prometheus','uid':ds};panels=[];y=0;pid=0
    def row(title):
        nonlocal y,pid
        pid+=1;panels.append({'id':pid,'type':'row','title':title,'collapsed':False,'gridPos':{'x':0,'y':y,'w':24,'h':1},'panels':[]});y+=1
    def panel(title,expr,unit='locale',kind='stat',w=6,h=4,x=0,description='',legend='',mappings=None):
        nonlocal y,pid
        pid+=1
        exprs=expr if isinstance(expr,list) else [(expr,legend)]
        p={'id':pid,'type':kind,'title':title,'description':description,'datasource':datasource,
          'gridPos':{'x':x,'y':y,'w':w,'h':h},'targets':[{'refId':chr(65+i),'expr':q,'legendFormat':l,'datasource':datasource,'instant':kind in ('stat','bargauge'),'range':kind not in ('stat','bargauge')} for i,(q,l) in enumerate(exprs)],
          'fieldConfig':{'defaults':{'unit':unit,'noValue':'Unavailable / stale','color':{'mode':'palette-classic'},'thresholds':{'mode':'absolute','steps':[{'color':'green','value':None}]},'mappings':mappings or []},'overrides':[]},
          'options':{'reduceOptions':{'calcs':['lastNotNull'],'fields':'','values':False},'orientation':'auto','textMode':'auto','colorMode':'value','graphMode':'area','justifyMode':'auto','legend':{'displayMode':'table','placement':'bottom','calcs':['lastNotNull']},'tooltip':{'mode':'multi','sort':'desc'}}}
        panels.append(p)
        if x+w>=24:y+=h
        return p
    def gate(q,c='inventory'):
        return '('+q+') and on(immich_host) (immich_collector_success{immich_host=~"$host",component="'+c+'"} == 1) and on(immich_host) (time()-immich_collector_timestamp_seconds{immich_host=~"$host",component="'+c+'"}<180)'
    def inv(name):return gate('immich_inventory_'+name+'{immich_host=~"$host"}')
    def total(metric,selector='',by='immich_host',component='inventory'):
        return gate('sum by('+by+') ('+metric+'{immich_host=~"$host"'+(','+selector if selector else '')+'})',component)
    row('Library • current inventory')
    for i,(t,q,u) in enumerate([
        ('Active accounts',inv('users'),'locale'),('Photos',total('immich_inventory_assets','media_type="IMAGE",state="active"'),'locale'),
        ('Videos',total('immich_inventory_assets','media_type="VIDEO",state="active"'),'locale'),('Original media size',total('immich_inventory_original_bytes','state="active"'),'bytes')]):panel(t,q,u,x=i*6)
    for i,(t,n,u) in enumerate([('Unique content','unique_originals','locale'),('Unique logical size','unique_bytes','bytes'),('Albums','albums','locale'),('People / shared identities','people','locale')]):panel(t,inv(n),u,x=i*6,description='Unique size is based on checksum and metadata; this is not physical disk usage.' if n=='unique_bytes' else '')
    for i,(t,n) in enumerate([('GIFs','gifs'),('Detected faces','faces'),('External library assets','external_assets'),('Active public links','shared_links')]):panel(t,inv(n),x=i*6)
    row('Inventory trends • history since collection began')
    panel('Photo and video inventory',total('immich_inventory_assets','state="active"','immich_host,media_type'),'locale',kind='timeseries',w=12,h=8,legend='{{media_type}}',description='Actual sampled inventory. History starts when this collector was enabled; no reconstructed historical counts.')
    panel('Original size by media type',total('immich_inventory_original_bytes','state="active"','immich_host,media_type'),'bytes',kind='timeseries',w=12,h=8,x=12,legend='{{media_type}}')
    panel('Original references and unique content',[(total('immich_inventory_assets','state="active"'),'All active references'),(inv('unique_originals'),'Unique content')],'locale',kind='timeseries',w=12,h=8,description='References count ownership records. Unique content groups checksums. Sharing access does not add an ownership record.')
    panel('Original size and unique logical size',[(total('immich_inventory_original_bytes','state="active"'),'All active references'),(inv('unique_bytes'),'Unique logical bytes')],'bytes',kind='timeseries',w=12,h=8,x=12,description='Logical sizes from known original metadata; not physical NAS consumption.')
    panel('Inventory by account',total('immich_account_assets','state="active"','immich_host,account'),'locale',kind='timeseries',w=12,h=8,legend='{{account}}')
    panel('Original size by account over time',total('immich_account_original_bytes','state="active"','immich_host,account'),'bytes',kind='timeseries',w=12,h=8,x=12,legend='{{account}}')
    row('Recent additions • indexed in Immich, not capture date')
    for i,(t,media,window,u,metric) in enumerate([
        ('Photos added · 24h','IMAGE','24h','locale','immich_recent_assets'),
        ('Videos added · 24h','VIDEO','24h','locale','immich_recent_assets'),
        ('Original size added · 24h',None,'24h','bytes','immich_recent_bytes'),
        ('Originals added · 7d',None,'7d','locale','immich_recent_assets')]):
        panel(t,total(metric,'window="'+window+'"'+(',media_type="'+media+'"' if media else '')),u,x=i*6,description='Based on Immich asset creation time. Includes imports/discovery; this is not the photo capture date or a reliable device-upload timestamp.')
    panel('Additions over time · rolling 24h',total('immich_recent_assets','window="24h"','immich_host,media_type'),kind='timeseries',w=12,h=7,legend='{{media_type}}')
    panel('Added size by account · last 7d',total('immich_account_recent_bytes','window="7d"','immich_host,account'),unit='bytes',kind='bargauge',w=12,h=7,x=12,legend='{{account}}',description='Accounts with known originals and no additions show zero. Original size is based on available file-size metadata.')
    row('Accounts • active originals')
    panel('Photos and videos by account',total('immich_account_assets','state="active"','immich_host,account,media_type'),kind='bargauge',w=12,h=7,legend='{{account}} · {{media_type}}',description='Optional account labels must be enabled in the private collector config. Counts are per account; shared access does not create another original.')
    panel('Original size by account',total('immich_account_original_bytes','state="active"','immich_host,account'),unit='bytes',kind='bargauge',w=12,h=7,x=12,legend='{{account}}',description='Sum of known original byte sizes, including duplicate content owned by different accounts.')
    row('Processing • all queues')
    for i,(t,s) in enumerate([('Active jobs','active'),('Waiting jobs','waiting|prioritized|delayed|waiting_children'),('Retained failed jobs','failed'),('Paused queues',None)]):
        q=total('immich_queue_jobs','state=~"'+s+'"',component='queues') if s else total('immich_queue_paused',component='queues')
        panel(t,q,x=i*6,description='Retained failed/completed jobs are current queue records, not lifetime counters. Zero means a successful empty queue read.')
    panel('Jobs by queue and state',total('immich_queue_jobs','state!="completed"','immich_host,queue,state','queues'),kind='timeseries',w=24,h=8,legend='{{queue}} · {{state}}')
    row('Data quality and trash')
    for i,(t,q) in enumerate([('Missing metadata extraction',inv('missing_metadata')),('Missing previews',inv('missing_preview')),('Originals with unknown size',total('immich_inventory_missing_size','state="active"')),('Trashed originals',total('immich_inventory_assets','state="trashed"'))]):panel(t,q,x=i*6)
    for i,(t,q,u) in enumerate([
        ('External libraries',inv('external_libraries'),'locale'),('Unexpired session records',inv('sessions'),'locale'),
        ('Trashed original size',total('immich_inventory_original_bytes','state="trashed"'),'bytes'),
        ('Duplicate content references','('+total('immich_inventory_assets','state="active"')+') - on(immich_host) ('+inv('unique_originals')+')','locale')]):panel(t,q,u,x=i*6)
    row('Database • read-only operational statistics')
    for i,(t,n,u) in enumerate([('Database size','database_bytes','bytes'),('Database connections','database_connections','locale'),('Database deadlocks since statistics reset','database_deadlocks','locale'),('Size added · 7d',None,'bytes')]):
        panel(t,inv(n) if n else total('immich_recent_bytes','window="7d"'),u,x=i*6)
    row('Protection • native backup and cloud coverage')
    state_map=[{'type':'value','options':{'-1':{'text':'Unknown','color':'gray'},'0':{'text':'Failed','color':'red'},'1':{'text':'Success','color':'green'},'2':{'text':'Running','color':'blue'},'3':{'text':'Deferred','color':'yellow'}}}]
    panel('Workflow state',gate('immich_backup_workflow_state{immich_host=~"$host"}','backup'),w=12,h=5,legend='{{component}}',mappings=state_map,description='Deferred means waiting for a prerequisite or coordination lock. It is not a completed capture or failure. Last success remains independent.')
    panel('Time since last successful workflow',gate('time()-immich_backup_last_success_timestamp_seconds{immich_host=~"$host"}','backup'),unit='s',w=12,h=5,x=12,legend='{{component}}')
    for i,(t,m,u) in enumerate([('Cloud verified originals','cloud_verified_unique_files','locale'),('Cloud pending originals','cloud_pending_files','locale'),('Export errors','export_errors','locale'),('Dropbox free','dropbox_free_bytes','bytes')]):panel(t,gate('immich_'+m+'{immich_host=~"$host"}','backup'),u,x=i*6)
    for i,(t,q,u) in enumerate([('Current export covered in Dropbox',gate('immich_cloud_current_source_verified{immich_host=~"$host"}','backup'),'locale'),('Cloud verification age',gate('time()-immich_cloud_verification_timestamp_seconds{immich_host=~"$host"}','backup'),'s'),('Native health issues',gate('immich_backup_health_issues{immich_host=~"$host"}','backup'),'locale'),('Native health check age',gate('time()-immich_backup_health_timestamp_seconds{immich_host=~"$host"}','backup'),'s')]):panel(t,q,u,x=i*6)
    row('Containers • recorded Docker state')
    health_map=[{'type':'value','options':{'-1':{'text':'No health check','color':'gray'},'0':{'text':'Unhealthy','color':'red'},'1':{'text':'Healthy','color':'green'},'2':{'text':'Starting','color':'yellow'}}}]
    panel('Container running',gate('immich_container_running{immich_host=~"$host"}','containers'),w=12,h=5,legend='{{service}}',mappings=[{'type':'value','options':{'0':{'text':'Stopped','color':'red'},'1':{'text':'Running','color':'green'}}}])
    panel('Container health',gate('immich_container_health{immich_host=~"$host"}','containers'),w=12,h=5,x=12,legend='{{service}}',mappings=health_map)
    panel('Container uptime',gate('time()-immich_container_start_timestamp_seconds{immich_host=~"$host"}','containers'),'s',w=12,h=5,legend='{{service}}')
    panel('Container restart count',gate('immich_container_restarts{immich_host=~"$host"}','containers'),w=12,h=5,x=12,legend='{{service}}',description='Docker restart counter for this container, not lifetime service failures; recreating a container resets the count.')
    row('Runtime • API and workers')
    sel='job="immich",instance=~"${host}:809[12]"'
    panel('Metrics endpoint availability','up{'+sel+'}',w=6,legend='{{instance}}')
    panel('Process CPU · sum of user and system','sum by(instance) (rate(process_cpu_time_total{'+sel+'}[$__rate_interval]))','percentunit',w=9,x=6,legend='{{instance}}',description='CPU seconds per second; 100% equals one fully used core.')
    panel('Process resident memory','process_memory_usage{'+sel+'}','bytes',w=9,x=15,legend='{{instance}}')
    panel('Repository operations / second','sum by(instance) (rate(label_replace({__name__=~"immich_.*_repository_.*_duration_count",'+sel+'},"operation","$1","__name__","(.+)")[5m:30s]))','ops',kind='timeseries',w=12,h=7,legend='{{instance}}',description='Instrumented repository calls, not HTTP requests.')
    panel('Mean repository operation latency','sum by(instance) (rate(label_replace({__name__=~"immich_.*_repository_.*_duration_sum",'+sel+'},"operation","$1","__name__","(.+)")[5m:30s])) / sum by(instance) (rate(label_replace({__name__=~"immich_.*_repository_.*_duration_count",'+sel+'},"operation","$1","__name__","(.+)")[5m:30s]))','ms',kind='timeseries',w=12,h=7,x=12,legend='{{instance}}',description='Native durations are milliseconds. No observations means no latency sample; no artificial zero is inserted.')
    panel('Successful jobs / second · 5m','sum by(operation) (rate(label_replace({__name__=~"immich_jobs_.+_success_total",'+sel+'},"operation","$1","__name__","immich_jobs_(.+)_success_total")[5m:30s]))','ops',kind='timeseries',w=12,h=7,legend='{{operation}}')
    panel('Failed jobs · rolling hour','sum by(operation) (increase(label_replace({__name__=~"immich_jobs_.+_failed_total",'+sel+'},"operation","$1","__name__","immich_jobs_(.+)_failed_total")[1h:30s]))','locale',kind='timeseries',w=12,h=7,x=12,legend='{{operation}}',description='Native failure counters, independently of the retained failed queue records. A counter must have observations to show a value.')
    row('Host and storage')
    node='job="node-exporters",instance=~"${host}:9100"'
    panel('Host CPU busy','1-avg by(instance)(rate(node_cpu_seconds_total{'+node+',mode="idle"}[$__rate_interval]))','percentunit',w=6)
    panel('Host memory used','1-node_memory_MemAvailable_bytes{'+node+'}/node_memory_MemTotal_bytes{'+node+'}','percentunit',w=6,x=6)
    panel('Swap used','node_memory_SwapTotal_bytes{'+node+'}-node_memory_SwapFree_bytes{'+node+'}','bytes',w=6,x=12)
    panel('Host uptime','time()-node_boot_time_seconds{'+node+'}','s',w=6,x=18)
    fs=node+',fstype=~"ext4|xfs|nfs|nfs4"'
    panel('Filesystem free space','node_filesystem_avail_bytes{'+fs+'}','bytes',kind='bargauge',w=12,h=7,legend='{{mountpoint}}',description='NAS mounts may share the same underlying pool; do not sum their capacity.')
    panel('Filesystem used','1-node_filesystem_avail_bytes{'+fs+'}/node_filesystem_size_bytes{'+fs+'}','percentunit',kind='bargauge',w=12,h=7,x=12,legend='{{mountpoint}}')
    # All must still be restricted to hosts with this collector, not the entire node fleet.
    node_membership=' and on(instance) label_replace(immich_collector_success{immich_host=~"$host",component="inventory"},"instance","$1:9100","immich_host","(.+)")'
    host_row=False
    for p in panels:
        if p.get('type')=='row':host_row=p['title']=='Host and storage'
        elif host_row:
            for t in p.get('targets',[]):t['expr']='('+t['expr']+')'+node_membership
    panel('Host network throughput',[
        ('sum by(instance)(rate(node_network_receive_bytes_total{'+node+',device!~"lo|veth.*|docker.*|br-.*"}[$__rate_interval]))'+node_membership,'Receive'),
        ('sum by(instance)(rate(node_network_transmit_bytes_total{'+node+',device!~"lo|veth.*|docker.*|br-.*"}[$__rate_interval]))'+node_membership,'Transmit')],'Bps',kind='timeseries',w=12,h=7)
    panel('Local disk throughput',[
        ('sum by(instance)(rate(node_disk_read_bytes_total{'+node+',device=~"sd.*|vd.*|nvme.*"}[$__rate_interval]))'+node_membership,'Read'),
        ('sum by(instance)(rate(node_disk_written_bytes_total{'+node+',device=~"sd.*|vd.*|nvme.*"}[$__rate_interval]))'+node_membership,'Write')],'Bps',kind='timeseries',w=12,h=7,x=12)
    row('Observability • collection health')
    panel('Collector component success','immich_collector_success{immich_host=~"$host"}',w=12,h=4,legend='{{component}}')
    panel('Time since successful component read','time()-immich_collector_timestamp_seconds{immich_host=~"$host"}','s',w=12,h=4,x=12,legend='{{component}}')
    pid+=1;panels.append({'id':pid,'type':'text','title':'What these numbers mean','gridPos':{'x':0,'y':y,'w':24,'h':5},'options':{'mode':'markdown','content':'Inventory and queue reads run every minute. Inventory, jobs and backup panels hide values after a component failure or 3 minutes without a successful read. Collection health stays visible. Native HTTP request metrics are not emitted by the tested Immich version, so repository operations are labelled separately. Counts include active originals; trash is separate. Logical content size is not NAS disk usage. Account labels are private and opt-in. Backup history and verification timestamps are reported as recorded; this dashboard does not run backups or mutate media.'}})
    for p in panels:
        if p.get('type')=='timeseries' and p.get('title') in ('Photo and video inventory','Original size by media type','Original references and unique content','Original size and unique logical size','Inventory by account','Original size by account over time'):
            p['fieldConfig']['defaults']['min']=0
            if p['fieldConfig']['defaults']['unit']=='locale':p['fieldConfig']['defaults']['decimals']=0
        if p.get('title')=='Unexpired session records':p['description']='Stored session records with no explicit expiry or an expiry in the future. This is not the number of people currently online.'
        if p.get('title')=='Missing previews':p['description']='Active assets without an asset_file preview record. Format support and processing state affect this count; it alone does not establish a media or backup error.'
        if p.get('title') in ('Repository operations / second','Mean repository operation latency','Successful jobs / second · 5m','Failed jobs · rolling hour'):
            p['fieldConfig']['defaults']['noValue']='No observations in this interval'
        if p.get('title')=='Metrics endpoint availability':
            p['fieldConfig']['defaults']['mappings']=[{'type':'value','options':{'0':{'text':'Down','color':'red'},'1':{'text':'Up','color':'green'}}}]
    return {'uid':'immich-kdnlab-001','title':'Immich','schemaVersion':41,'version':1,'editable':True,'tags':['immich','reviewed','media','backup'],'timezone':'browser','refresh':'30s','time':{'from':'now-3h','to':'now'},'panels':panels,'templating':{'list':[{'name':'host','label':'Immich host','type':'query','datasource':datasource,'definition':'label_values(immich_collector_success, immich_host)','query':{'query':'label_values(immich_collector_success, immich_host)','refId':'host'},'refresh':1,'includeAll':True,'allValue':'.*','multi':False,'current':{'text':'All','value':'$__all'},'options':[]}]},'__inputs':[{'name':'DS_PROMETHEUS','label':'Prometheus','type':'datasource','pluginId':'prometheus','pluginName':'Prometheus'}]}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--datasource',default='${DS_PROMETHEUS}');p.add_argument('--output',default='services/Immich.json');a=p.parse_args()
    Path(a.output).write_text(json.dumps(build(a.datasource),indent=2)+'\n')
