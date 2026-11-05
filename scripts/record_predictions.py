#!/usr/bin/env python3
"""Append-only forecast ledger: record only genuinely future fixtures.

Never rewrite an existing forecast or settlement. Git history provides audit
visibility but is NOT cryptographic immutability against repository owners.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def write_ledger(season,model,path,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    today=now.date().isoformat()
    ledger=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'schema':1,'predictions':[],'settlements':[]}
    old={x['key'] for x in ledger['predictions']}
    resolved={x['key'] for x in ledger['settlements']}
    added=settled=0
    for lid,info in season.get('leagues',{}).items():
        forecasts=model.get('leagues',{}).get(lid,{}).get('predictions',{})
        for event in info.get('events',[]):
            fid=str(event.get('id') or '')
            if not fid:continue
            key=f'{lid}:{season.get("season","unknown")}:{fid}'
            if event.get('finished') is True and isinstance(event.get('home_score'),int) and isinstance(event.get('away_score'),int):
                if key in old and key not in resolved:
                    ledger['settlements'].append({'key':key,'resolved_at':now.replace(microsecond=0).isoformat(),
                                                  'date':event['date'],'home_score':event['home_score'],
                                                  'away_score':event['away_score']})
                    settled+=1
                    resolved.add(key)
                continue
            # Strictly future calendar date, not same-day or backfilled output.
            if event.get('date','')<=today or key in old or fid not in forecasts:
                continue
            p=forecasts[fid]
            m={k:float(v) for k,v in p.get('markets',{}).items() if isinstance(v,(float,int))}
            if not m:continue
            entry={'key':key,'league':lid,'issued_at':now.replace(microsecond=0).isoformat(),
                   'date':event['date'],'home':event['home'],'away':event['away'],
                   'model':p.get('model'),'markets':m}
            digest=hashlib.sha256(json.dumps(entry,sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest()
            entry['sha256']=digest
            ledger['predictions'].append(entry)
            old.add(key)
            added+=1
    if added or settled or not path.exists():
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(ledger,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    print(f'Ledger: {len(ledger["predictions"])} previsões, {len(ledger["settlements"])} resolvidas; novas {added}, resolvidas {settled}')
    return ledger

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--season',type=Path,default=ROOT/'data'/'season.json')
    p.add_argument('--model',type=Path,default=ROOT/'data'/'model.json')
    p.add_argument('--output',type=Path,default=ROOT/'data'/'ledger.json')
    args=p.parse_args()
    write_ledger(json.loads(args.season.read_text(encoding='utf-8')),
                 json.loads(args.model.read_text(encoding='utf-8')),args.output)

if __name__=='__main__':
    main()
