#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Read-only USB soak sampling; retains only diagnostic fields, never credentials.

Run after flashing/acceptance. Uses the existing status and power commands.
An unplugged board is a coverage gap, not a successful sample or measured
battery runtime. Battery reports can be retrieved when USB is connected again.
"""
import argparse
import contextlib
import fcntl
import json
import os
from pathlib import Path
import signal
import statistics
import time

POWER_KEYS=('boot','uptime','battery_boots','started','running','secs','battery_pct',
            'battery_mv','screen_off','resting','slept','sleeps','busy','heap')
STOP=False

def safe_power(value):
    return {k:value[k] for k in POWER_KEYS if k in value} if isinstance(value,dict) else None

def collect(serial_number,firmware):
    # Imported only for device work, allowing offline report tests without USB.
    import ports
    from chat import Board
    from power import ask
    sample={'at':time.time()}
    try:
        try:
            port=ports.find('s3-18',serial_number)
        except ports.NotFound:
            return {**sample,'ok':False,'reason':'usb_absent'}
        if not port:
            return {**sample,'ok':False,'reason':'usb_absent'}
        with Board(port) as board:
            status=board.status(timeout=4)
            if not status:return {**sample,'ok':False,'reason':'no_status'}
            device=status.get('device',{})
            if device.get('fw')!=firmware:
                return {**sample,'ok':False,'reason':'firmware_changed'}
            power,saved=ask(board,'power')
            if not isinstance(power,dict) or not isinstance(power.get('uptime'),(int,float)):
                return {**sample,'ok':False,'reason':'no_power_report'}
            sample.update(ok=True,fw=firmware,board=status.get('board'),
                wifi=device.get('wifi',{}).get('state'),muse=device.get('hatch',{}).get('state'),
                link=device.get('link',{}).get('state'),battery=device.get('battery'),
                settings={k:device.get(k) for k in ('volume','speaker','mic_gain','brightness','sleep')},
                power=safe_power(power),saved_battery=safe_power(saved))
            # Timestamp at receipt, after command latency, for uptime comparisons.
            sample['at']=time.time()
            return sample
    except Exception as exc:
        # BoardError may contain private console text: record only its class.
        return {**sample,'ok':False,'reason':'read_error','error_type':type(exc).__name__}

def summarize(samples,meta,now):
    good=[s for s in samples if s.get('ok')]
    gaps=0;covered=0.0;restarts=[];previous=None;free=[];largest=[];offline=0;saved_sessions=0
    for s in samples:
        if not s.get('ok'):
            gaps+=1;previous=None;continue
        p=s['power'];h=p.get('heap',{})
        if isinstance(h.get('free'),(int,float)):free.append(h['free'])
        if isinstance(h.get('largest'),(int,float)):largest.append(h['largest'])
        # Saved means configured but not currently tested. The firmware also
        # uses it after its intentional idle close; it is not an outage by
        # itself, and it does not prove a new conversation will succeed.
        if s.get('muse')=='Saved':saved_sessions+=1
        if s.get('wifi')!='connected' or s.get('muse') not in ('Connected','Saved') or s.get('link')!='Online':offline+=1
        if previous:
            dt=s['at']-previous['at'];du=p['uptime']-previous['power']['uptime']
            if dt>0 and dt<=meta['interval_seconds']*2.5:
                if du<0 or abs(du-dt)>30:
                    restarts.append({'at':s['at'],'reason':p.get('boot'),'uptime':p['uptime']})
                else:covered+=dt
        previous=s
    # Across disconnects, a changed boot epoch is evidence of a possible restart;
    # it is separate from continuously observed restart detection.
    possible=[]
    indexed=[(i,s) for i,s in enumerate(samples) if s.get('ok')]
    for (ai,a),(bi,b) in zip(indexed,indexed[1:]):
        dt=b['at']-a['at'];du=b['power']['uptime']-a['power']['uptime']
        if (bi>ai+1 or dt>meta['interval_seconds']*2.5) and (du<0 or abs(du-dt)>30):
            possible.append({'at':b['at'],'reason':b['power'].get('boot')})
    elapsed=max(0,min(now,meta['end_at'])-meta['start_at'])
    stale=not samples or now-samples[-1]['at']>meta['interval_seconds']*2.5
    return {'summary_schema':2,'started_at':meta['start_at'],'ends_at':meta['end_at'],'window_complete':now>=meta['end_at'],
        'samples':len(samples),'successful_samples':len(good),'unavailable_samples':gaps,
        'elapsed_seconds':round(elapsed),'observed_seconds':round(covered),
        'coverage_fraction':round(min(1,covered/elapsed),4) if elapsed else 0,
        'restart_events':restarts,'possible_restarts_across_gaps':possible,
        'connection_not_online_samples':offline,'muse_saved_samples':saved_sessions,'stale':stale,
        'internal_heap_min_sampled':min(free) if free else None,
        'largest_block_min_sampled':min(largest) if largest else None,
        'internal_heap_first5_median':statistics.median(free[:5]) if free else None,
        'internal_heap_last5_median':statistics.median(free[-5:]) if free else None,
        'last_sample':samples[-1] if samples else None,
        'scope':'USB status/uptime/connection/memory observation; no automatic audio, touch or battery-endurance pass'}

def write_json(path,value):
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(value,indent=2)+'\n');temporary.chmod(0o600);temporary.replace(path)

def load_samples(path):
    if not path.exists():return []
    out=[]
    for line in path.read_text().splitlines():
        try:out.append(json.loads(line))
        except json.JSONDecodeError:continue # incomplete final line after host power loss
    return out

@contextlib.contextmanager
def exclusive(path):
    with path.open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=('run','sample','summary'))
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--serial');parser.add_argument('--firmware')
    parser.add_argument('--hours',type=float,default=24)
    parser.add_argument('--interval',type=int,default=60)
    a=parser.parse_args();os.umask(0o077)
    root=a.out.resolve()
    if a.operation=='summary':
        meta=json.loads((root/'run.json').read_text());s=summarize(load_samples(root/'samples.jsonl'),meta,time.time())
        print(json.dumps(s,indent=2));return
    if not 0<a.hours<=168 or not 10<=a.interval<=3600:parser.error('Invalid observation window or interval')
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    with exclusive(root/'run.lock'):
        if (root/'run.json').exists():
            meta=json.loads((root/'run.json').read_text())
            if a.serial and meta['serial']!=a.serial:parser.error('Existing run belongs to a different board')
            if a.firmware and meta['firmware']!=a.firmware:parser.error('Existing run belongs to different firmware')
        else:
            if not a.serial or not a.firmware:parser.error('New runs need --serial and --firmware')
            now=time.time();meta={'serial':a.serial,'firmware':a.firmware,'start_at':now,'end_at':now+a.hours*3600,'interval_seconds':a.interval}
            write_json(root/'run.json',meta)
        def stop(*_):
            global STOP
            STOP=True
        signal.signal(signal.SIGINT,stop);signal.signal(signal.SIGTERM,stop)
        print('Diagnostic sampling started; only status and power are queried.',flush=True)
        while not STOP and time.time()<meta['end_at']:
            sample=collect(meta['serial'],meta['firmware'])
            with (root/'samples.jsonl').open('a') as out:out.write(json.dumps(sample)+'\n');out.flush()
            report=summarize(load_samples(root/'samples.jsonl'),meta,time.time());write_json(root/'summary.json',report)
            print(json.dumps({'samples':report['samples'],'ok':sample['ok'],'reason':sample.get('reason'),
                              'uptime':(sample.get('power') or {}).get('uptime')}),flush=True)
            if a.operation=='sample' or sample.get('reason')=='firmware_changed':break
            end=min(time.time()+meta['interval_seconds'],meta['end_at'])
            while not STOP and time.time()<end:time.sleep(max(0,min(1,end-time.time())))
        report=summarize(load_samples(root/'samples.jsonl'),meta,time.time());write_json(root/'summary.json',report)
        print('Observation window ended.' if report['window_complete'] else 'Sampler stopped; measurements retained.',flush=True)

if __name__=='__main__':main()
