#!/usr/bin/env python3
"""Reconstruct lost Dutch source-ID lineage without rewriting signed forecasts.

The two 2026/27 sources sometimes assign different fixture dates and IDs to
the same oriented match. Earlier snapshots lost superseded-ID metadata after
an hourly source refresh. Match ONLY a unique same-season home/away pairing;
the link is provenance, never permission to move a prediction or settlement.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from collections import defaultdict
from pathlib import Path

try:
    from scripts.collect_openfootball_nl import canonical, club
    from scripts.audit_expansion_1x2 import digest, timestamp
except ModuleNotFoundError:
    from collect_openfootball_nl import canonical, club
    from audit_expansion_1x2 import digest, timestamp

ROOT=Path(__file__).resolve().parents[1]
SEASON=ROOT/'data'/'season.json'
LEDGER=ROOT/'data'/'expansion_1x2_ledger.json'
MAX_DATE_SHIFT_DAYS=120


def oriented(home,away):
    return canonical(club(home)),canonical(club(away))


def recover(season,ledger,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        raise ValueError('Recovery requires timezone-aware timestamp')
    if season.get('schema')!=1 or season.get('season')!='2026-2027':
        raise ValueError('Unexpected season document')
    if ledger.get('schema')!=1:
        raise ValueError('Unexpected prediction ledger')
    nl=season.get('leagues',{}).get('nl')
    if not isinstance(nl,dict):
        raise ValueError('Missing Eredivisie')
    events=[e for e in nl.get('events',[]) if isinstance(e,dict) and e.get('id')]
    by_id={str(e['id']):e for e in events}
    by_pair=defaultdict(list)
    for e in events:
        by_pair[oriented(e.get('home'),e.get('away'))].append(e)
    archive=nl.setdefault('openfootball',{})
    saved={str(x['id']):x for x in archive.get('superseded',[])
           if isinstance(x,dict) and x.get('id') and x.get('replacement_id')}
    changed=unresolved=ambiguous=conflicting=bad_signature=0
    predictions=[p for p in ledger.get('predictions',[])
                 if isinstance(p,dict) and p.get('league')=='nl']
    for pred in predictions:
        pid=str(pred.get('match_id') or '')
        key=f'nl:{season["season"]}:{pid}'
        if not pid or pred.get('key')!=key:
            unresolved+=1
            continue
        if pid in by_id:
            continue
        if pred.get('sha256')!=digest(pred):
            bad_signature+=1
            continue
        issued=timestamp(pred.get('issued_at'))
        try:
            before=dt.date.fromisoformat(str(pred.get('date')))
        except ValueError:
            unresolved+=1
            continue
        if issued is None or issued.date()>=before:
            unresolved+=1
            continue
        pair=oriented(pred.get('home'),pred.get('away'))
        matches=by_pair.get(pair,[])
        if len(matches)!=1:
            unresolved+=1
            ambiguous+=int(len(matches)>1)
            continue
        fixture=matches[0]
        try:
            replacement_date=dt.date.fromisoformat(str(fixture.get('date')))
        except ValueError:
            unresolved+=1
            continue
        if abs((replacement_date-before).days)>MAX_DATE_SHIFT_DAYS:
            unresolved+=1
            continue
        if pid in saved:
            if saved[pid].get('replacement_id')!=str(fixture['id']):
                conflicting+=1
            continue
        saved[pid]={
            'id':pid,'replacement_id':str(fixture['id']),
            'old_date':str(pred['date']),
            'replacement_date':str(fixture['date']),
            'home':str(pred.get('home') or ''),
            'away':str(pred.get('away') or ''),
            'reason':'signed_forecast_on_alternative_source_calendar',
            'matched_by':'unique_oriented_pair_2026_2027',
            'settlement_transfer_allowed':False,
        }
        changed+=1
    archive['superseded']=sorted(saved.values(),key=lambda item:str(item['id']))
    old_report=archive.get('forecast_id_reconciliation',{})
    status={
        'source':'signed_prospective_1x2_ledger',
        'recovered_total':sum(1 for p in predictions if str(p.get('match_id')) in saved),
        'newly_recovered':changed,
        'missing_without_safe_match':unresolved+conflicting+bad_signature,
        'ambiguous_match':ambiguous,
        'mapping_conflicts':conflicting,
        'invalid_signature':bad_signature,
        'policy':'Provenance only. Never reassign a signed prediction, never settle on replacement ID.',
    }
    archive['forecast_id_reconciliation']=status
    print('NL signed fixture provenance',json.dumps(status,ensure_ascii=False))
    return season,status


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--season',type=Path,default=SEASON)
    p.add_argument('--ledger',type=Path,default=LEDGER)
    args=p.parse_args()
    s=json.loads(args.season.read_text(encoding='utf8'))
    ledger=json.loads(args.ledger.read_text(encoding='utf8'))
    original=json.dumps(ledger,sort_keys=True,ensure_ascii=False)
    result,report=recover(s,ledger)
    if original!=json.dumps(ledger,sort_keys=True,ensure_ascii=False):
        raise RuntimeError('Recovery mutated signed predictions')
    args.season.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n',
                           encoding='utf8')
    if report['missing_without_safe_match']:
        print('Some orphan IDs require manual review; no automatic settlement was made.',
              flush=True)


if __name__=='__main__':
    main()
