#!/usr/bin/env python3
"""Read-only operational centre for signed prospective 1X2 forecasts.

Never settles or changes a prediction: settlement eligibility is established
only by the existing signed ledger and independently verified final fixture.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from collections import Counter
from pathlib import Path

try:
    from scripts.audit_expansion_1x2 import LEAGUES, digest, timestamp
    from scripts.match_status import verified_event, normalize_status, LIVE_STATUSES
except ModuleNotFoundError:
    from audit_expansion_1x2 import LEAGUES, digest, timestamp
    from match_status import verified_event, normalize_status, LIVE_STATUSES

ROOT=Path(__file__).resolve().parents[1]
NAMES={'pt':'Liga Portugal','dk':'Superliga','nl':'Eredivisie',
       'dk2':'1. Division','no':'Eliteserien'}
STATES=('future','in_progress','unconfirmed','awaiting_settlement',
        'validated','review','superseded')

def is_valid_prediction(p,now,duplicates):
    key=p.get('key')
    issued=timestamp(p.get('issued_at'))
    generated=timestamp(p.get('model_generated_at'))
    try:
        fixture_date=dt.date.fromisoformat(str(p.get('date')))
    except (ValueError,TypeError):
        return False,'invalid_forecast_date'
    if duplicates[key]!=1:return False,'duplicate_signed_id'
    if p.get('sha256')!=digest(p):return False,'invalid_signed_hash'
    if (issued is None or generated is None or
        generated>issued or generated>now or issued>now or
        issued.date()>=fixture_date):
        return False,'invalid_prematch_chronology'
    probs=p.get('probabilities_1x2')
    if (not isinstance(probs,list) or len(probs)!=3 or
        any(type(v) not in (int,float) or not math.isfinite(v) or v<0 or v>1 for v in probs)
        or abs(sum(probs)-1)>0.0001):
        return False,'invalid_probabilities'
    return True,None

def build(ledger,season,audit,health=None,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:raise ValueError('Timezone-aware now is required')
    now=now.astimezone(dt.timezone.utc)
    if ledger.get('schema')!=1 or audit.get('schema')!=1:
        raise ValueError('Invalid signed ledger or 1X2 audit schema')
    season_id=str(season.get('season') or '')
    if not season_id:raise ValueError('Missing season ID')
    index={}
    replaced={}
    for lid in LEAGUES:
        info=season.get('leagues',{}).get(lid,{})
        for match in info.get('events',[]):
            if match.get('id'):index[f'{lid}:{season_id}:{match["id"]}']=match
        if lid=='nl':
            for item in info.get('openfootball',{}).get('superseded',[]):
                if item.get('id') and item.get('replacement_id'):
                    replaced[f'{lid}:{season_id}:{item["id"]}']=str(item['replacement_id'])
    predictions=ledger.get('predictions',[])
    settlements=ledger.get('settlements',[])
    pkeys=Counter(p.get('key') for p in predictions)
    skeys=Counter(x.get('key') for x in settlements)
    settled={x.get('key'):x for x in settlements}
    counts=Counter()
    per_league={lid:{'name':NAMES[lid],'total':0,**{s:0 for s in STATES}} for lid in LEAGUES}
    records=[]
    today=now.date().isoformat()
    for p in predictions:
        lid=p.get('league')
        if lid not in per_league:continue
        key=p.get('key')
        fixture=index.get(key)
        settlement=settled.get(key)
        valid,reason=is_valid_prediction(p,now,pkeys)
        next_id=replaced.get(key)
        if not valid:
            status='review'
        elif next_id:
            status='superseded'
            reason='replaced_source_id_no_transfer'
        elif not fixture:
            status='review'
            reason='fixture_id_missing'
        elif fixture.get('date')!=p.get('date'):
            status='review'
            reason='rescheduled_identity_requires_review'
        elif settlement is not None:
            ok=(skeys[key]==1 and settlement.get('verified_final') is True and
                verified_event(fixture) and settlement.get('date')==p.get('date') and
                (settlement.get('home_score'),settlement.get('away_score'))==
                (fixture.get('home_score'),fixture.get('away_score')))
            if ok:
                status='validated'
                reason='verified_final_settlement'
            else:
                status='review'
                reason='settlement_not_verified_or_conflicting'
        elif verified_event(fixture):
            status='awaiting_settlement'
            reason='verified_final_without_signed_settlement'
        elif normalize_status(fixture.get('match_status')) in LIVE_STATUSES and fixture.get('date')==today:
            status='in_progress'
            reason='source_snapshot_in_play_not_live_confirmed'
        elif fixture.get('date','')<today:
            status='unconfirmed'
            reason='past_due_without_verified_final'
        elif fixture.get('date')==today:
            status='unconfirmed'
            reason='today_status_not_verified'
        else:
            status='future'
            reason='future_fixture'
        counts[status]+=1
        per_league[lid]['total']+=1
        per_league[lid][status]+=1
        records.append({
            'key':str(key),'league':lid,'home':str(p.get('home') or ''),
            'away':str(p.get('away') or ''),'original_date':str(p.get('date') or ''),
            'current_date':str(fixture.get('date') or '') if fixture else None,
            'issued_at':p.get('issued_at'),'model':p.get('model'),
            'status':status,'reason':reason,
            'match_status':fixture.get('match_status') if fixture else None,
            'replacement_id':next_id,
            'score':{'home':settlement['home_score'],'away':settlement['away_score']}
                if status=='validated' else None,
        })
    # Never silently ignore inconsistent audit totals.
    audited_issued=sum(int(v.get('issued',0)) for v in audit.get('leagues',{}).values())
    if audited_issued!=len(records):
        raise ValueError(f'Audit/ledger count mismatch: {audited_issued} != {len(records)}')
    audited_valid=sum(int(v.get('settled_valid',0)) for v in audit.get('leagues',{}).values())
    if counts['validated']!=audited_valid:
        raise ValueError(f'Validated count differs from signed audit: {counts["validated"]} != {audited_valid}')
    if sum(counts.values())!=len(records):
        raise AssertionError('Status counts do not reconcile')
    records.sort(key=lambda r:(STATES.index(r['status']),r['original_date'],r['league'],r['key']))
    h=health if isinstance(health,dict) else {}
    general={'active_settlements':int(h.get('states',{}).get('settled',0)),
             'integrity_alerts':int(h.get('issue_count',0)),
             'quarantined':len([])}  # generic ledger quarantine is read separately
    return {'schema':1,'generated_at':now.replace(microsecond=0).isoformat(),
            'source_generated_at':season.get('updated_at'),
            'method':'Only original signed prospective 1X2 predictions and the same provider fixture ID',
            'status':'requires_review' if counts['review'] or general['integrity_alerts'] else 'monitoring',
            'total':len(records),'active_ids':len(records)-counts['superseded'],
            'counts':{k:counts[k] for k in STATES},
            'leagues':per_league,'general_ledger':general,
            'brier':{lid:{'n':int(audit.get('leagues',{}).get(lid,{}).get('settled_valid',0)),
                'brier':audit.get('leagues',{}).get(lid,{}).get('brier'),
                'log_loss':audit.get('leagues',{}).get(lid,{}).get('log_loss')}
                for lid in LEAGUES},
            'records':records,
            'note':'Snapshot status may be delayed. Superseded IDs remain signed and are never migrated/settled. No odds, no profitability claims.'}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--ledger',type=Path,default=ROOT/'data'/'expansion_1x2_ledger.json')
    p.add_argument('--season',type=Path,default=ROOT/'data'/'season.json')
    p.add_argument('--audit',type=Path,default=ROOT/'data'/'expansion_1x2_audit.json')
    p.add_argument('--health',type=Path,default=ROOT/'data'/'ledger_health.json')
    p.add_argument('--general-ledger',type=Path,default=ROOT/'data'/'ledger.json')
    p.add_argument('--output',type=Path,default=ROOT/'data'/'validation_center.json')
    args=p.parse_args()
    read=lambda path:json.loads(path.read_text(encoding='utf8'))
    data=build(read(args.ledger),read(args.season),read(args.audit),
               read(args.health) if args.health.exists() else None)
    if args.general_ledger.exists():
        general=read(args.general_ledger)
        data['general_ledger']['quarantined']=len(general.get('quarantined_settlements',[]))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf8')
    print('Validation Center:',json.dumps({'total':data['total'],'counts':data['counts'],
      'general_ledger':data['general_ledger']},ensure_ascii=False))

if __name__=='__main__':
    main()
