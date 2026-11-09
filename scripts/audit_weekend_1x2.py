#!/usr/bin/env python3
"""Audit the latest weekend of genuinely signed prospective 1X2 predictions.

This report NEVER settles or changes forecasts. Only existing verified signed
settlements enter score comparisons; independently confirmed FT without an
associated settlement is displayed but explicitly excluded from metrics.
"""
from __future__ import annotations
import datetime as dt
import math
from collections import Counter

try:
    from scripts.build_validation_center import is_valid_prediction
    from scripts.match_status import verified_event
except ModuleNotFoundError:
    from build_validation_center import is_valid_prediction
    from match_status import verified_event

LEAGUES=('pt','dk','nl','dk2','no')
STATES=('validated','confirmed_pending','unverified','postponed',
        'rescheduled','superseded','review')

def weekend_days(now):
    date=now.date()
    # On Mon-Fri summarize the weekend that just finished; Sat/Sun
    # show a provisional current-weekend report.
    if date.weekday()==5:
        saturday=date
    elif date.weekday()==6:
        saturday=date-dt.timedelta(days=1)
    else:
        saturday=date-dt.timedelta(days=date.weekday()+2)
    return saturday,saturday+dt.timedelta(days=1)

def build(ledger,season,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:raise ValueError('Timezone-aware time required')
    now=now.astimezone(dt.timezone.utc)
    if ledger.get('schema')!=1 or season.get('schema')!=1:
        raise ValueError('Malformed signed forecast or season')
    sat,sun=weekend_days(now)
    period={sat.isoformat(),sun.isoformat()}
    source_season=str(season.get('season') or '')
    by_key={}
    replaced=set()
    for lid in LEAGUES:
        lg=season.get('leagues',{}).get(lid,{})
        for e in lg.get('events',[]):
            if e.get('id'):
                by_key[f'{lid}:{source_season}:{e["id"]}']=e
        if lid=='nl':
            for e in lg.get('openfootball',{}).get('superseded',[]):
                if e.get('id'):
                    replaced.add(f'{lid}:{source_season}:{e["id"]}')
    signed=ledger.get('predictions',[])
    settlements=ledger.get('settlements',[])
    pred_keys=Counter(e.get('key') for e in signed)
    settle_keys=Counter(e.get('key') for e in settlements)
    settle_map={e.get('key'):e for e in settlements}
    totals=Counter()
    leagues={lid:{'total':0,**{state:0 for state in STATES},
                  'scored':0,'top_pick_correct':0} for lid in LEAGUES}
    brier=[];loss=[];hits=[]
    records=[]
    for p in signed:
        if p.get('date') not in period or p.get('league') not in LEAGUES:
            continue
        lid=p['league'];key=p.get('key')
        fixture=by_key.get(key)
        settlement=settle_map.get(key)
        ok,reason=is_valid_prediction(p,now,pred_keys)
        if not ok:
            state='review'
        elif key in replaced:
            state='superseded';reason='original_id_superseded'
        elif not fixture or (fixture.get('home'),fixture.get('away'))!=(
            p.get('home'),p.get('away')):
            state='review';reason='fixture_missing_or_changed'
        elif fixture.get('date')!=p.get('date'):
            state='rescheduled';reason='fixture_date_changed'
        elif settlement is not None:
            good=(settle_keys[key]==1 and verified_event(fixture) and
                  settlement.get('verified_final') is True and
                  settlement.get('date')==p.get('date') and
                  (settlement.get('home_score'),settlement.get('away_score'))==(
                  fixture.get('home_score'),fixture.get('away_score')))
            state='validated' if good else 'review'
            reason='verified_signed_settlement' if good else 'settlement_disagreement'
        elif verified_event(fixture):
            state='confirmed_pending';reason='verified_ft_not_yet_settled'
        elif str(fixture.get('match_status') or '').upper() in (
              'PST','POSTPONED','CANC','CANCELLED','ABD','ABANDONED'):
            state='postponed';reason='source_postponed_or_cancelled'
        else:
            state='unverified';reason='no_validated_final_result'
        score=None;tip=None;correct=None;value=None
        if state=='validated':
            score=[settlement['home_score'],settlement['away_score']]
            winner=0 if score[0]>score[1] else 1 if score[0]==score[1] else 2
            probs=p['probabilities_1x2']
            b=sum((v-(1 if i==winner else 0))**2 for i,v in enumerate(probs))
            ll=-math.log(max(probs[winner],1e-9))
            top=max(range(3),key=lambda i:probs[i])
            correct=top==winner
            value=round(b,5)
            brier.append(b);loss.append(ll);hits.append(correct)
            tip=['1','X','2'][top]
            leagues[lid]['scored']+=1
            leagues[lid]['top_pick_correct']+=int(correct)
        totals[state]+=1
        leagues[lid]['total']+=1;leagues[lid][state]+=1
        if tip is None:
            probs=p.get('probabilities_1x2',[])
            if isinstance(probs,list) and len(probs)==3:
                tip=['1','X','2'][max(range(3),key=lambda i:probs[i])]
        records.append({'key':str(key),'league':lid,'date':p['date'],
                        'current_date':fixture.get('date') if fixture else None,
                        'home':p.get('home'),'away':p.get('away'),
                        'issued_at':p.get('issued_at'),
                        'state':state,'reason':reason,
                        'tip':tip,'probabilities_1x2':p.get('probabilities_1x2'),
                        'score':score,'correct':correct,'brier':value,
                        'result_source':fixture.get('result_source') if fixture and
                        state in ('validated','confirmed_pending') else None})
    records.sort(key=lambda x:(x['date'],x['league'],x['key']))
    n=len(brier)
    return {'schema':1,'generated_at':now.replace(microsecond=0).isoformat(),
            'start_date':sat.isoformat(),'end_date':sun.isoformat(),
            'complete_weekend':now.date()>sun,
            'status':'provisional_insufficient_sample' if n<30 else
                     'descriptive_only_not_proven_profitable',
            'total':len(records),'counts':{state:totals[state] for state in STATES},
            'leagues':leagues,
            'metrics':{'n':n,'top_pick_correct':sum(hits),
                'accuracy':round(sum(hits)/n,5) if n else None,
                'brier':round(sum(brier)/n,5) if n else None,
                'uniform_brier':round(2/3,5) if n else None,
                'log_loss':round(sum(loss)/n,5) if n else None,
                'uniform_log_loss':round(math.log(3),5) if n else None},
            'records':records,
            'note':'Signed prospective forecasts only. No reconstructed tips, no ROI, unverified results are never counted. Uniform baseline is 1/3 each outcome, not bookmaker odds.'}
