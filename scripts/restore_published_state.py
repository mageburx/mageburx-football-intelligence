#!/usr/bin/env python3
"""Continuity of published history/forecast snapshots when branch is protected.

GitHub Pages is NOT immutable storage; this is an explicitly best-effort
restore, plus a 90-day artifact backup in GitHub Actions.
"""
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE='https://mageburx.github.io/mageburx-football-intelligence/data/'

def get_json(name):
    url=BASE+name+'?t='+str(int(dt.datetime.now(dt.timezone.utc).timestamp()))
    req=urllib.request.Request(url,headers={'User-Agent':'FootballIntelligence/4.0','Cache-Control':'no-cache'})
    with urllib.request.urlopen(req,timeout=15) as response:
        if response.status != 200:
            raise ValueError('Estado publicado não disponível')
        return json.loads(response.read(4_000_000).decode('utf-8'))

def merge_history(local,remote):
    if remote.get('schema')!=1 or not isinstance(remote.get('leagues'),dict):
        raise ValueError('Histórico remoto inválido')
    for lid in ('pt','dk'):
        base=local['leagues'][lid]['seasons']
        incoming=remote.get('leagues',{}).get(lid,{}).get('seasons',{})
        for season,entry in incoming.items():
            if season not in local.get('requested',[]) or not isinstance(entry,dict):continue
            before=base.get(season,{})
            events={e['id']:e for e in before.get('events',[]) if isinstance(e,dict) and e.get('id')}
            for e in entry.get('events',[]):
                if isinstance(e,dict) and e.get('id') and e.get('date') and e.get('home') and e.get('away'):
                    events.setdefault(e['id'],e)
            if not events:continue
            rounds=sorted(set(before.get('fetched_rounds',[])+entry.get('fetched_rounds',[])))
            expected=max(int(before.get('expected_games') or 0),int(entry.get('expected_games') or 0))
            base[season]={'events':sorted(events.values(),key=lambda e:(e['date'],e['id'])),
                          'actual_games':len(events),'expected_games':expected,
                          'complete':bool((before.get('complete') or entry.get('complete')) and
                                           len(events)>=expected and (not rounds or len(rounds)==32)),
                          'verified_from':before.get('verified_from') or entry.get('verified_from'),
                          'fetched_rounds':rounds}
    return local

def merge_ledger(local,remote):
    if remote.get('schema')!=1 or not isinstance(remote.get('predictions'),list):
        raise ValueError('Registo publicado inválido')
    for field in ('predictions','settlements'):
        existing={x['key']:x for x in local.get(field,[]) if isinstance(x,dict) and x.get('key')}
        for item in remote.get(field,[]):
            if isinstance(item,dict) and item.get('key') and item['key'] not in existing:
                existing[item['key']]=item
        local[field]=list(existing.values())
    return local

def restore(root=ROOT, fetch=get_json):
    for name in ('history.json','ledger.json'):
        path=root/'data'/name
        if name=='history.json' and not path.exists():continue
        local=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {
            'schema':1,'predictions':[],'settlements':[]}
        try:
            remote=fetch(name)
            data=merge_history(local,remote) if name=='history.json' else merge_ledger(local,remote)
            path.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
            print('Estado recuperado:',name,flush=True)
        except Exception as exc:
            print('AVISO: estado anterior não recuperável:',name,str(exc)[:120],flush=True)

if __name__=='__main__':
    restore()
