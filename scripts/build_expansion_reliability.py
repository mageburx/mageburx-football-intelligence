#!/usr/bin/env python3
"""Per-league evidence, with correct distinction between historical and live.

NL: fixed-code historical season holdout only if earlier seasons completed.
DK2/NO: exploratory current-season chronological replay only (no independent
holdout). Prospective forecasts counted but never retroactively fabricated.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import math
from pathlib import Path
try:
    from scripts.build_model import finished, goal_rates, score_probs, usable, MIN_TRAIN
except ModuleNotFoundError:
    from build_model import finished, goal_rates, score_probs, usable, MIN_TRAIN

try:
    from scripts.record_expansion_1x2 import summary as prospective_1x2_summary
except ModuleNotFoundError:
    from record_expansion_1x2 import summary as prospective_1x2_summary

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/'data'/'expansion_reliability.json'
LEAGUES=('nl','dk2','no')


def outcome(e):
    return 0 if e['home_score']>e['away_score'] else 1 if e['home_score']==e['away_score'] else 2


def metrics(train,test,mode):
    train=usable(train)
    test=usable(test)
    errors=[]
    for match in test:
        if not finished(match):continue
        before=[e for e in train if finished(e) and e['date']<match['date']]
        before += [e for e in test if finished(e) and e['date']<match['date']]
        rates=goal_rates(before,match['date'],match['home'],match['away'])
        if rates is None:continue
        p=score_probs(*rates,dc=True)['p']
        y=outcome(match)
        frequency=[1.,1.,1.]
        for prev in before:
            frequency[outcome(prev)]+=1
        base=[x/sum(frequency) for x in frequency]
        model_brier=sum((v-(i==y))**2 for i,v in enumerate(p))
        baseline_brier=sum((v-(i==y))**2 for i,v in enumerate(base))
        errors.append((model_brier,baseline_brier,
                       -math.log(max(1e-9,p[y])),
                       -math.log(max(1e-9,base[y]))))
    n=len(errors)
    if not n:return {'n':0,'status':'insufficient_completed_prior_matches',
                     'brier':None,'baseline_brier':None,'log_loss':None,
                     'baseline_log_loss':None,'brier_gain_ci95':None}
    avg=lambda i:sum(r[i] for r in errors)/n
    gains=[r[1]-r[0] for r in errors]
    gain=sum(gains)/n
    sample_variance=sum((v-gain)**2 for v in gains)/(n-1) if n>1 else 0
    margin=1.96*math.sqrt(sample_variance/n)
    return {'n':n,'status':('historical_holdout_exploratory' if mode=='heldout'
                          else 'current_season_walk_forward_not_independent'),
            'brier':round(avg(0),4),'baseline_brier':round(avg(1),4),
            'brier_gain':round(gain,5),
            'brier_gain_ci95':[round(gain-margin,5),round(gain+margin,5)],
            'log_loss':round(avg(2),4),'baseline_log_loss':round(avg(3),4),
            'warning':'Indicadores estatísticos, sem odds reais nem prova de rentabilidade.'}


def nl_holdout(archive):
    years=sorted((k,v) for k,v in archive.get('seasons',{}).items() if
                 isinstance(v,dict) and v.get('complete') is True)
    for name,holdout in reversed(years):
        prior=[e for yr,item in years if yr<name for e in item['events']]
        if len(prior)<150:continue
        value=metrics(prior,holdout['events'],'heldout')
        return {'season':name,'prior_seasons':[yr for yr,_ in years if yr<name],
                'source':'OpenFootball CC0; results from archived, verified full seasons',
                'metrics':value}
    return {'season':None,'prior_seasons':[],
            'source':'OpenFootball CC0 (partial historical archive)',
            'metrics':None}


def build(season,archive,ledger=None,now=None,one_x_two_ledger=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    ledger=ledger or {}
    one_x_two_ledger=one_x_two_ledger or {}
    today=now.date().isoformat()
    counts={lid:{'issued':0,'settled':0} for lid in LEAGUES}
    done={x['key'] for x in ledger.get('settlements',[]) if isinstance(x,dict) and x.get('key')}
    for p in ledger.get('predictions',[]):
        lid=p.get('league')
        if lid not in counts:continue
        counts[lid]['issued']+=1
        if p.get('key') in done:counts[lid]['settled']+=1
    dutch=nl_holdout(archive)
    report={'schema':1,'generated_at':now.replace(microsecond=0).isoformat(),
            'source_status':'historical_CC0_plus_TheSportsDB',
            'explainer':'Retrospective walk-forward is NOT prospective betting evidence.',
            'leagues':{}}
    for lid in LEAGUES:
        info=season.get('leagues',{}).get(lid,{})
        played=[e for e in info.get('events',[]) if e.get('date','')<today and finished(e)]
        upcoming=sum(e.get('date','')>today and not e.get('finished') for e in info.get('events',[]))
        current=metrics([],played,'current')
        backtest=dutch['metrics'] if lid=='nl' else None
        sample=backtest or current
        ready=bool(backtest and backtest['n']>=100)
        report['leagues'][lid]={
            'name':info.get('name',lid),'season':info.get('source_season','unknown'),
            'collected':len(info.get('events',[])),'completed':len(played),
            'upcoming':upcoming,'partial':bool(info.get('partial',True)),
            'verified_rounds':len(info.get('collection',{}).get('verified_rounds',[])),
            'retrospective_current':current,
            'holdout':dutch if lid=='nl' else None,
            'best_available_1x2':sample,
            'prospective':counts[lid],
            'prospective_1x2':prospective_1x2_summary(one_x_two_ledger,lid),
            'quality':('historical_holdout_available_not_proof_of_profit' if ready else
                       'insufficient_independent_holdout'),
            'note':('O teste histórico NL usa apenas épocas completas anteriores, com parâmetros fixos.'
                    if lid=='nl' else
                    'Teste cronológico da época corrente não substitui avaliação independente noutra época.'),
        }
    return report


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--season',type=Path,default=ROOT/'data'/'season.json')
    p.add_argument('--archive',type=Path,default=ROOT/'data'/'nl_history.json')
    p.add_argument('--ledger',type=Path,default=ROOT/'data'/'ledger.json')
    p.add_argument('--one-x-two-ledger',type=Path,default=ROOT/'data'/'expansion_1x2_ledger.json')
    p.add_argument('--output',type=Path,default=PATH)
    args=p.parse_args()
    load=lambda x:json.loads(x.read_text(encoding='utf8')) if x.exists() else {}
    result=build(load(args.season),load(args.archive),load(args.ledger),
                 one_x_two_ledger=load(args.one_x_two_ledger))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf8')
    print('Expansion reliability:',json.dumps({lid:{'completed':x['completed'],
             'current_test_n':x['retrospective_current']['n'],
             'historical_test_n':x['best_available_1x2']['n'],
             'quality':x['quality']} for lid,x in result['leagues'].items()},ensure_ascii=False))


if __name__=='__main__':
    main()
