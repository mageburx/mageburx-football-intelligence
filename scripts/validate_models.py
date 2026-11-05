#!/usr/bin/env python3
"""Three-way evaluation: training seasons / tuning season / untouched holdout.

2021/22–2023/24 train; 2024/25 validation chooses Poisson vs Dixon-Coles;
2025/26 final holdout. Per-fixture estimates use earlier dates only.
Partial seasons are never silently treated as held-out validation.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import math
from collections import defaultdict
from pathlib import Path

try:
    from scripts.build_model import (finished, goal_rates, score_probs, MARKET_LABELS, market_settles)
    from scripts.build_reliability import summary
except ModuleNotFoundError:
    from build_model import finished, goal_rates, score_probs, MARKET_LABELS, market_settles
    from build_reliability import summary

ROOT=Path(__file__).resolve().parents[1]
TRAIN=('2021-2022','2022-2023','2023-2024')
TUNE='2024-2025'
TEST='2025-2026'
METHODS=('poisson','dc')

def events_for(seasons, season):
    entries=seasons.get(season,{}).get('events',[])
    return sorted((x for x in entries if finished(x)),key=lambda e:(e['date'],str(e.get('id',''))))

def audit_league(seasons, quality):
    counts={year:len(events_for(seasons,year)) for year in (*TRAIN,TUNE,TEST)}
    gaps=[year for year in (*TRAIN,TUNE,TEST)
          if not quality.get('seasons',{}).get(year,{}).get('complete',False)]
    base={'split':{'train':list(TRAIN),'validation':TUNE,'holdout':TEST},
          'count':counts,'complete':not gaps,'incomplete_seasons':gaps}
    if gaps:
        return {**base,'status':'insufficient_historical_coverage',
                'warning':'No independent claim until all five seasons pass quality audit.',
                'markets':{}}
    chronological=[]
    for year in (*TRAIN,TUNE,TEST):
        chronological.extend(events_for(seasons,year))
    chronological.sort(key=lambda e:(e['date'],str(e.get('id',''))))
    validations=defaultdict(lambda:defaultdict(list))
    holdouts=defaultdict(lambda:defaultdict(list))
    for match in chronological:
        date=match['date']
        if not (f'{TUNE[:4]}-07-01'<=date<f'{int(TEST[:4])+1}-07-01'):
            continue
        stage='validation' if date<f'{TEST[:4]}-07-01' else 'holdout'
        before=[e for e in chronological if e['date']<date]
        rates=goal_rates(before,date,match['home'],match['away'])
        if rates is None:
            continue
        ps={method:score_probs(*rates,dc=(method=='dc')) for method in METHODS}
        target=validations if stage=='validation' else holdouts
        for key in MARKET_LABELS:
            observed=market_settles(match,key)
            prior=(1+sum(market_settles(e,key) for e in before))/(2+len(before))
            for method,values in ps.items():
                p=values['markets'].get(key)
                if key=='double_1x':
                    p=values['p'][0]+values['p'][1]
                elif key=='double_x2':
                    p=values['p'][1]+values['p'][2]
                elif key=='double_12':
                    p=values['p'][0]+values['p'][2]
                target[key][method].append((date,max(1e-9,min(1-1e-9,p)),observed,prior))
    result={}
    for market in MARKET_LABELS:
        validation_metrics={method:summary(validations[market][method]) for method in METHODS}
        if min(validation_metrics[m]['n'] for m in METHODS)<100:
            result[market]={'status':'validation_sample_too_small',
                            'validation':validation_metrics,'holdout':{}}
            continue
        best=min(METHODS,key=lambda m:validation_metrics[m]['brier'])
        holdout_metrics=summary(holdouts[market][best])
        # This is an honest test on a season not used for choosing a model.
        holdout_metrics['status']=(
            'insufficient_holdout' if holdout_metrics['n']<200 else
            'historical_signal_not_confirmed' if holdout_metrics['brier_gain_ci95'][0]<=0 else
            'historical_signal_to_replicate')
        result[market]={'chosen_on_validation':best,
                        'validation':validation_metrics,
                        'holdout':holdout_metrics,
                        'status':holdout_metrics['status']}
    return {**base,'status':'historical_holdout_completed',
            'markets':result,
            'warning':'Candidate models are selected only on 2024/25 and assessed on 2025/26; prospective proof and independent replication still missing. Live predictions do not automatically switch to these selections.'}

def build(history,quality):
    return {'schema':1,'generated_at':dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
            'protocol':'Three-way chronological split; fixed Poisson or fixed Dixon-Coles selected only using validation Brier; walk-forward retraining on prior completed fixtures',
            'note':'Historical holdout is not prospective validation; overlapping game outcomes and model design decisions limit statistical confidence.',
            'leagues':{lid:audit_league(history['leagues'][lid]['seasons'],quality['leagues'][lid])
                       for lid in ('pt','dk')}}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--history',type=Path,default=ROOT/'data'/'history.json')
    p.add_argument('--quality',type=Path,default=ROOT/'data'/'quality.json')
    p.add_argument('--output',type=Path,default=ROOT/'data'/'validation.json')
    args=p.parse_args()
    out=build(json.loads(args.history.read_text(encoding='utf8')),
              json.loads(args.quality.read_text(encoding='utf8')))
    args.output.write_text(json.dumps(out,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf8')
    print(json.dumps({lid:{'status':v['status'],'over2.5':v.get('markets',{}).get('over_2_5',{}).get('holdout',{})}
                      for lid,v in out['leagues'].items()},ensure_ascii=False))

if __name__=='__main__':
    main()
