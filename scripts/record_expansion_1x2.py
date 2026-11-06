#!/usr/bin/env python3
"""Freeze and settle genuinely forward-looking 1X2 predictions by league.

The general-purpose market ledger predates 1X2 storage; DO NOT retrospectively
attach 1X2 values to its older predictions. This separate ledger initially covered NL/DK2/NO and now covers PT/DK too,
only on matches strictly after each forecast's original recording date. No odds, no ROI claims.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/'data'/'expansion_1x2_ledger.json'
LEAGUES=('pt','dk','nl','dk2','no')


def parse_datetime(value):
    try:
        item=dt.datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return item.astimezone(dt.timezone.utc) if item.tzinfo else None
    except (TypeError,ValueError):return None


def forecast(p):
    if not isinstance(p,dict):return None
    values=[p.get(x) for x in ('p1','px','p2')]
    if any(type(x) not in (float,int) or not math.isfinite(x) or
           x<0 or x>1 for x in values):return None
    z=sum(values)
    if not 0.97<z<1.03:return None
    return [round(x/z,7) for x in values]


def expected_key(lid,season,e):
    return f'{lid}:{season}:{e["id"]}'


def run(season,model,existing=None,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:raise ValueError('Aware UTC now required')
    now=now.astimezone(dt.timezone.utc)
    today=now.date().isoformat()
    db=existing if existing is not None else {
        'schema':1,'method':'Frozen 1X2 pre-match forecasts','predictions':[],
        'settlements':[]}
    if db.get('schema')!=1:raise ValueError('Unknown ledger schema')
    saved={x['key'] for x in db['predictions']}
    settled={x['key'] for x in db['settlements']}
    generated=parse_datetime(model.get('generated_at'))
    can_issue=generated is not None and dt.timedelta()<=now-generated<=dt.timedelta(hours=48)
    for lid in LEAGUES:
        fixtures=season.get('leagues',{}).get(lid,{}).get('events',[])
        predictions=model.get('leagues',{}).get(lid,{}).get('predictions',{})
        for event in fixtures:
            eid=str(event.get('id') or '')
            if not eid or not event.get('date'):continue
            key=expected_key(lid,season.get('season','unknown'),event)
            finished=event.get('finished') is True and (
                type(event.get('home_score')) is int and
                type(event.get('away_score')) is int)
            if key in saved:
                if (key not in settled and finished and event['date']<today):
                    db['settlements'].append({
                        'key':key,'date':event['date'],
                        'home_score':event['home_score'],'away_score':event['away_score'],
                        'resolved_at':now.replace(microsecond=0).isoformat()})
                    settled.add(key)
                continue
            if not can_issue or finished or event['date']<=today:continue
            p=predictions.get(eid)
            one_x_two=forecast(p)
            if one_x_two is None:continue
            entry={
                'key':key,'league':lid,'match_id':eid,
                'issued_at':now.replace(microsecond=0).isoformat(),
                'model_generated_at':generated.replace(microsecond=0).isoformat(),
                'model':str(p.get('model') or 'unknown'),
                'date':event['date'],'home':event.get('home'),'away':event.get('away'),
                'probabilities_1x2':one_x_two,
                'warning':'Research only; no betting odds or verified financial edge.'}
            entry['sha256']=hashlib.sha256(
                json.dumps(entry,sort_keys=True,ensure_ascii=False).encode('utf8')).hexdigest()
            db['predictions'].append(entry)
            saved.add(key)
    return db


def summary(db,lid):
    predictions=[p for p in db.get('predictions',[]) if p.get('league')==lid]
    settlements={s['key']:s for s in db.get('settlements',[]) if s.get('key')}
    scored=[]
    for p in predictions:
        result=settlements.get(p['key'])
        if result is None:continue
        if type(result.get('home_score')) is not int or type(result.get('away_score')) is not int:continue
        if p.get('date')!=result.get('date'):continue
        issued=parse_datetime(p.get('issued_at'))
        try:
            cutoff=dt.datetime.fromisoformat(result['date']+'T00:00:00+00:00')
        except ValueError:continue
        if issued is None or issued>=cutoff:continue
        v=p.get('probabilities_1x2')
        if not isinstance(v,list) or len(v)!=3 or any(
            type(x) not in (int,float) or not math.isfinite(x) for x in v):continue
        y=0 if result['home_score']>result['away_score'] else (
            1 if result['home_score']==result['away_score'] else 2)
        scored.append((sum((a-(1 if i==y else 0))**2 for i,a in enumerate(v)),
                       -math.log(max(1e-9,v[y]))))
    n=len(scored)
    return {'issued':len(predictions),'settled':n,'pending':len(predictions)-n,
            'brier':round(sum(x for x,_ in scored)/n,5) if n else None,
            'log_loss':round(sum(x for _,x in scored)/n,5) if n else None,
            'status':'preliminary_only' if 0<n<100 else (
                'review_after_100' if n>=100 else 'awaiting_results'),
            'note':'No retroactive probability reconstruction. Even 100 results do not demonstrate financial profitability.'}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--season',type=Path,default=ROOT/'data'/'season.json')
    p.add_argument('--model',type=Path,default=ROOT/'data'/'model.json')
    p.add_argument('--output',type=Path,default=PATH)
    args=p.parse_args()
    load=lambda path:json.loads(path.read_text(encoding='utf8'))
    old=load(args.output) if args.output.exists() else None
    db=run(load(args.season),load(args.model),old)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(db,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf8')
    print('Prospective 1X2',json.dumps({lid:summary(db,lid) for lid in LEAGUES},
                                    ensure_ascii=False))


if __name__=='__main__':
    main()
