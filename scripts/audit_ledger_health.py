#!/usr/bin/env python3
"""Audit real pre-match forecasts without fabricating outcomes or profitability."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def fingerprint(prediction):
    original={k:v for k,v in prediction.items() if k!='sha256'}
    blob=json.dumps(original,sort_keys=True,ensure_ascii=False).encode('utf-8')
    return hashlib.sha256(blob).hexdigest()


def build(ledger,season,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    today=now.date().isoformat()
    season_name=season.get('season','unknown')
    indexed={}
    for lid,info in season.get('leagues',{}).items():
        for event in info.get('events',[]):
            fid=str(event.get('id') or '')
            if fid:
                indexed[f'{lid}:{season_name}:{fid}']=event

    predictions=ledger.get('predictions',[])
    settlements=ledger.get('settlements',[])
    pkeys=Counter(p.get('key') for p in predictions)
    skeys=Counter(s.get('key') for s in settlements)
    settlement_by_key={s.get('key'):s for s in settlements}
    counts=Counter()
    warnings=[]
    def warn(code,key):
        warnings.append({'code':code,'key':str(key)})
    for s in settlements:
        key=s.get('key')
        if pkeys.get(key,0)==0:warn('orphan_settlement',key)
        if skeys[key]>1:warn('duplicate_settlement',key)
        hs,aws=s.get('home_score'),s.get('away_score')
        if (type(hs) is not int or type(aws) is not int or hs<0 or aws<0):
            warn('invalid_settlement_score',key)
    for p in predictions:
        key=p.get('key')
        if pkeys[key]>1:warn('duplicate_prediction',key)
        if p.get('sha256') != fingerprint(p):warn('prediction_hash_mismatch',key)
        try:
            issued=dt.datetime.fromisoformat(p.get('issued_at',''))
            forecast_date=dt.date.fromisoformat(p.get('date',''))
            if issued.tzinfo is None or issued.astimezone(dt.timezone.utc).date() >= forecast_date:
                warn('unverifiable_prematch_timestamp',key)
        except (ValueError,TypeError):
            warn('unverifiable_prematch_timestamp',key)
        if not p.get('markets') or any(
            type(prob) not in (int,float) or not math.isfinite(prob) or not 0<=prob<=1
            for prob in p.get('markets',{}).values()):
            warn('invalid_forecast_probability',key)
        event=indexed.get(key)
        if key in settlement_by_key:
            counts['settled']+=1
            settlement=settlement_by_key[key]
            if event and event.get('finished') and (
                settlement.get('home_score')!=event.get('home_score') or
                settlement.get('away_score')!=event.get('away_score')):
                warn('settlement_conflicts_with_provider',key)
            continue
        if not event:
            counts['fixture_unavailable']+=1
        elif event.get('finished') is True:
            counts['finished_awaiting_settlement']+=1
        elif event.get('date','')>today:
            counts['future']+=1
        elif event.get('date')==today:
            counts['today']+=1
        else:
            counts['past_due_missing_result']+=1
        if event and event.get('date')!=p.get('date'):
            counts['fixture_date_changed']+=1
    stats={k:counts[k] for k in ('settled','future','today','past_due_missing_result',
                                'finished_awaiting_settlement','fixture_unavailable','fixture_date_changed')}
    return {'schema':1,'generated_at':now.replace(microsecond=0).isoformat(),
            'status':'requires_review' if warnings or stats['finished_awaiting_settlement'] else 'monitoring',
            'total_predictions':len(predictions),'total_settlements':len(settlements),
            'states':stats,'issue_count':len(warnings),'issues':warnings[:40],
            'note':'Zero settled is expected before the first forecasted games finish. Missing results are not losses; provider status must be confirmed. No betting ROI is inferred.'}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--ledger',type=Path,default=ROOT/'data'/'ledger.json')
    ap.add_argument('--season',type=Path,default=ROOT/'data'/'season.json')
    ap.add_argument('--output',type=Path,default=ROOT/'data'/'ledger_health.json')
    args=ap.parse_args()
    report=build(json.loads(args.ledger.read_text(encoding='utf-8')),
                 json.loads(args.season.read_text(encoding='utf-8')))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    print('Forecast ledger health:',json.dumps({'status':report['status'],'states':report['states'],
                                                'issue_count':report['issue_count']},ensure_ascii=False))
    if report['issue_count']:
        print('WARNING: forecast ledger audit found issues; inspect ledger_health.json',flush=True)


if __name__=='__main__':
    main()
