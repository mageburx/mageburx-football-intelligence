#!/usr/bin/env python3
"""Audit genuinely saved pre-match 1X2 predictions; never fabricate ROI.

Only the first signed prediction for each stable fixture key is used for
coverage. Flag corrupt files, duplicate predictions, changed fixture dates,
results with insufficient provider evidence, or unsafe pre-match chronology.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
LEAGUES=('nl','dk2','no')


def timestamp(value):
    try:
        d=dt.datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return d.astimezone(dt.timezone.utc) if d.tzinfo else None
    except (TypeError,ValueError):
        return None


def digest(record):
    data={k:v for k,v in record.items() if k!='sha256'}
    return hashlib.sha256(json.dumps(data,sort_keys=True,
        ensure_ascii=False).encode('utf8')).hexdigest()


def calculate(ledger,season,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:raise ValueError('Audit requires aware timestamp')
    today=now.date().isoformat()
    if ledger.get('schema')!=1:raise ValueError('Unrecognized prospective 1X2 ledger')
    current=season.get('season','unknown')
    index={}
    for lid in LEAGUES:
        info=season.get('leagues',{}).get(lid,{})
        for item in info.get('events',[]):
            fid=str(item.get('id') or '')
            if fid:index[f'{lid}:{current}:{fid}']=item
    predictions=ledger.get('predictions',[])
    settlements=ledger.get('settlements',[])
    pred_keys=Counter(x.get('key') for x in predictions)
    sett_keys=Counter(x.get('key') for x in settlements)
    resolved={x.get('key'):x for x in settlements}
    warnings=[]
    per={lid:{'issued':0,'settled':0,'awaiting_result':0,'future':0,
              'today':0,'past_due':0,'fixture_missing':0,
              'rescheduled':0,'invalid':0,'settled_valid':0,
              'brier':None,'log_loss':None,
              'status':'awaiting_results'} for lid in LEAGUES}
    scored={lid:[] for lid in LEAGUES}
    def warn(lid,code,key):
        warnings.append({'league':lid,'code':code,'key':str(key)})
    for p in predictions:
        lid=p.get('league')
        if lid not in per:continue
        c=per[lid]
        c['issued']+=1
        key=p.get('key')
        issued=timestamp(p.get('issued_at'))
        generated=timestamp(p.get('model_generated_at'))
        valid=True
        if pred_keys[key]!=1:
            warn(lid,'duplicate_prediction',key);valid=False
        if p.get('sha256')!=digest(p):
            warn(lid,'hash_mismatch',key);valid=False
        if (issued is None or generated is None or generated>issued
            or generated>now or issued>now):
            warn(lid,'invalid_issuance_time',key);valid=False
        try:
            date=dt.date.fromisoformat(str(p.get('date')))
            if issued is None or issued.date()>=date:
                warn(lid,'not_strictly_prematch',key);valid=False
        except (ValueError,TypeError):
            warn(lid,'invalid_match_date',key);valid=False
        probs=p.get('probabilities_1x2')
        if (not isinstance(probs,list) or len(probs)!=3 or
            any(type(v) not in (int,float) or not math.isfinite(v)
                or v<0 or v>1 for v in probs) or
            abs(sum(probs)-1)>0.0001):
            warn(lid,'invalid_probabilities',key);valid=False
        fixture=index.get(key)
        if fixture is None:
            c['fixture_missing']+=1
            warn(lid,'fixture_not_in_current_snapshot',key)
            # Older seasons may be absent: no retroactive settlement inferred.
        elif fixture.get('date')!=p.get('date'):
            c['rescheduled']+=1
            warn(lid,'fixture_date_changed',key)
        result=resolved.get(key)
        if result is not None:
            c['settled']+=1
            if sett_keys[key]!=1:
                warn(lid,'duplicate_settlement',key);valid=False
            if fixture and fixture.get('finished') is True and (
                fixture.get('home_score'),fixture.get('away_score'))!=(
                result.get('home_score'),result.get('away_score')):
                warn(lid,'settlement_score_conflict',key);valid=False
            if result.get('date')!=p.get('date'):
                warn(lid,'settlement_date_drift',key);valid=False
            hs,aws=result.get('home_score'),result.get('away_score')
            if type(hs) is not int or type(aws) is not int or not(0<=hs<30 and 0<=aws<30):
                warn(lid,'invalid_final_score',key);valid=False
            if fixture is None:
                valid=False
            if valid:
                y=0 if hs>aws else 1 if hs==aws else 2
                scored[lid].append((
                    sum((v-(i==y))**2 for i,v in enumerate(probs)),
                    -math.log(max(1e-9,probs[y]))))
                c['settled_valid']+=1
            else:c['invalid']+=1
        elif fixture and fixture.get('finished') is True:
            c['awaiting_result']+=1
        elif fixture and fixture.get('date','')>today:
            c['future']+=1
        elif fixture and fixture.get('date')==today:
            c['today']+=1
        elif fixture:
            c['past_due']+=1
        if not valid and result is None:c['invalid']+=1
    for s in settlements:
        key=s.get('key')
        if key not in pred_keys:
            warn('unknown','orphan_settlement',key)
    for lid,c in per.items():
        records=scored[lid]
        n=len(records)
        if n:
            c['brier']=round(sum(x for x,_ in records)/n,5)
            c['log_loss']=round(sum(x for _,x in records)/n,5)
            c['status']='preliminary_only' if n<100 else 'sample_ready_for_review'
        if c['invalid']>0:c['status']='requires_data_review'
        elif c['rescheduled']>0 or c['fixture_missing']>0:
            c['status']='schedule_change_review'
        elif c['past_due']>0:c['status']='past_due_unconfirmed'
        elif c['awaiting_result']>0:c['status']='awaiting_settlement'
    return {'schema':1,'generated_at':now.replace(microsecond=0).isoformat(),
            'status':'requires_review' if warnings else 'monitoring',
            'leagues':per,'warnings':warnings[:150],
            'warning_count':len(warnings),
            'note':'Only signed pre-match 1X2 records; no reconstructed historical tips, no odds, no ROI.'}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--ledger',type=Path,default=ROOT/'data'/'expansion_1x2_ledger.json')
    p.add_argument('--season',type=Path,default=ROOT/'data'/'season.json')
    p.add_argument('--output',type=Path,default=ROOT/'data'/'expansion_1x2_audit.json')
    args=p.parse_args()
    ledger=json.loads(args.ledger.read_text(encoding='utf8'))
    season=json.loads(args.season.read_text(encoding='utf8'))
    result=calculate(ledger,season)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf8')
    print('1X2 integrity',json.dumps({'status':result['status'],
      'warnings':result['warning_count'],
      'leagues':{k:{name:v[name] for name in ('issued','settled','future','rescheduled','invalid','brier')}
                 for k,v in result['leagues'].items()}},ensure_ascii=False))


if __name__=='__main__':
    main()
