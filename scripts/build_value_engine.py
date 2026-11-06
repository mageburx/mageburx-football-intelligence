#!/usr/bin/env python3
"""Value & Confidence Engine v5: two-stage fixed calibration and held-out audit.

2021/22–2023/24: initial history. 2024/25: calibrator fitted.
2025/26: untouched evaluation. Both forecast-generating stages use ONLY earlier
calendar dates for goal rates. No odds are sourced or invented.

Important: current live *goal* market probabilities are fixed Dixon-Coles, so
these calibrators apply to the same DC model. Live double-chance markets may
come from Poisson or an Elo ensemble: never apply the DC calibrator to those.
No profit or 'positive value bet' claim is made.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import math
from collections import defaultdict
from pathlib import Path

try:
    from scripts.build_model import MARKET_LABELS, finished, goal_rates, score_probs, market_settles
    from scripts.build_reliability import summary
except ModuleNotFoundError:
    from build_model import MARKET_LABELS, finished, goal_rates, score_probs, market_settles
    from build_reliability import summary

ROOT=Path(__file__).resolve().parents[1]
TRAIN=('2021-2022','2022-2023','2023-2024')
TUNE='2024-2025'
HOLDOUT='2025-2026'
MIN_VALIDATION=120
MIN_HOLDOUT=100
MIN_PROSPECTIVE=200
INTERCEPT_PENALTY=24.0
SLOPE_PENALTY=96.0

def clip(p):
    return max(1e-6,min(1-1e-6,float(p)))

def logit(p):
    p=clip(p)
    return math.log(p/(1-p))

def sigmoid(x):
    if x>=0:
        e=math.exp(-min(x,700))
        return 1/(1+e)
    e=math.exp(max(x,-700))
    return e/(1+e)

def adjusted(p, a, b):
    """Regression on log odds, fitted with fixed L2 regularisation."""
    return clip(sigmoid(a + b*logit(p)))

def fit_calibrator(observations):
    """Penalised binomial likelihood centred on the identity mapping.

    Input is a sequence of (raw_probability, binary_outcome). The slope is
    positive, bounded, and the regularisation is fixed before the holdout.
    """
    if len(observations)<MIN_VALIDATION:
        return None
    xy=[(logit(p),int(y)) for p,y in observations]
    a,b=0.0,1.0
    for _ in range(60):
        h00=INTERCEPT_PENALTY
        h01=0.0
        h11=SLOPE_PENALTY
        g0=INTERCEPT_PENALTY*a
        g1=SLOPE_PENALTY*(b-1)
        for x,y in xy:
            q=sigmoid(a+b*x)
            w=q*(1-q)
            g0+=q-y
            g1+=(q-y)*x
            h00+=w
            h01+=w*x
            h11+=w*x*x
        determinant=h00*h11-h01*h01
        if determinant<=1e-9:
            break
        da=(g0*h11-g1*h01)/determinant
        db=(g1*h00-g0*h01)/determinant
        # The fixed conservative parameter bounds prevent extreme distorted
        # prices when many fixtures have highly correlated outcomes.
        new_a=max(-1.0,min(1.0,a-da))
        new_b=max(0.35,min(1.65,b-db))
        if abs(new_a-a)+abs(new_b-b)<1e-8:
            a,b=new_a,new_b
            break
        a,b=new_a,new_b
    return {'intercept':round(a,6),'slope':round(b,6),
            'fit_n':len(observations),'source_model':'fixed_dixon_coles',
            'fit_season':TUNE,'regularization':{'intercept':INTERCEPT_PENALTY,'slope':SLOPE_PENALTY}}

def match_market_probs(events):
    """Reusable, deterministic fixed-DC walk-forward forecasts per match."""
    ordered=sorted((x for x in events if finished(x)),key=lambda e:(e['date'],str(e.get('id',''))))
    result=[]
    for match in ordered:
        date=match['date']
        if not (TUNE[:4]+'-07-01'<=date<str(int(HOLDOUT[:4])+1)+'-07-01'):
            continue
        before=[e for e in ordered if e['date']<date]
        rates=goal_rates(before,date,match['home'],match['away'])
        if rates is None:continue
        dc=score_probs(*rates,dc=True)
        m=dict(dc['markets'])
        m.update({'double_1x':dc['p'][0]+dc['p'][1],
                  'double_x2':dc['p'][1]+dc['p'][2],
                  'double_12':dc['p'][0]+dc['p'][2]})
        stage='validation' if date<HOLDOUT[:4]+'-07-01' else 'holdout'
        baseline_cache={}
        for key in MARKET_LABELS:
            if key not in m:continue
            # The historic base rate uses prior match dates only, not full
            # season totals. Compute once for each different market.
            prior=(1+sum(market_settles(e,key) for e in before))/(2+len(before))
            baseline_cache[key]=prior
        result.append((stage,match,m,baseline_cache))
    return result

def evaluate_league(seasons, quality):
    needed=(*TRAIN,TUNE,HOLDOUT)
    q=quality.get('seasons',{})
    missing=[year for year in needed if not q.get(year,{}).get('complete')]
    if missing:
        return {'status':'incomplete_historical_coverage','missing':missing,'markets':{},
                'message':'No calibration without five complete and audited seasons.'}
    events=[e for year in needed for e in seasons[year]['events']]
    forecasts=match_market_probs(events)
    grouped=defaultdict(lambda:defaultdict(list))
    for stage,e,markets,baseline in forecasts:
        for k in MARKET_LABELS:
            if k in markets:
                grouped[stage][k].append((e['date'],clip(markets[k]),market_settles(e,k),baseline[k]))
    metrics={}
    for key in MARKET_LABELS:
        train=grouped['validation'][key]
        holdout=grouped['holdout'][key]
        params=fit_calibrator([(p,y) for _,p,y,_ in train])
        raw_summary=summary(holdout)
        tune_summary=summary(train)
        entry={'source_model':'fixed_dixon_coles',
               'validation':{'n':len(train),'brier_raw':tune_summary.get('brier')},
               'holdout':{'raw':raw_summary,'calibrated':None},'params':params,
               'status':'experimental_only'}
        if params and holdout:
            calibrated=[(d,adjusted(p,params['intercept'],params['slope']),y,base)
                        for d,p,y,base in holdout]
            post=summary(calibrated)
            entry['holdout']['calibrated']=post
            gain=raw_summary['brier']-post['brier']
            entry['holdout']['brier_calibration_gain']=round(gain,5)
            entry['status']='research_heldout_sample_small' if len(holdout)<200 else 'research_holdout_available'
        elif not params:
            entry['status']='insufficient_validation_data'
        else:
            entry['status']='insufficient_holdout_data'
        metrics[key]=entry
    return {'status':'calibration_research_ready',
            'split':{'train':list(TRAIN),'fit':TUNE,'test':HOLDOUT},
            'validation_games':sum(1 for stage,_,_,_ in forecasts if stage=='validation'),
            'test_games':sum(1 for stage,_,_,_ in forecasts if stage=='holdout'),
            'markets':metrics,
            'warning':'Experimental adjustments were fitted on 2024/25, evaluated on 2025/26. Holdout performance is descriptive, not proof of an odds edge. Never recalibrate on the holdout.'}

def build(history,quality):
    return {'schema':1,'version':'5.0','generated_at':dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
            'protocol':'Fixed Dixon-Coles goal distribution; L2-regularised logit intercept/slope fit only on 2024/25; untouched 2025/26 holdout',
            'market_sources':{'goal_lines':'fixed_dixon_coles','btts':'fixed_dixon_coles',
                              'double_chance':'may_be_selected_1x2_model_not_dc'},
            'live_policy':'Calibrated experimental estimates only for fixed-DC goal markets. 1X2 / double chance are raw if live selected model differs. No automated betting.',
            'leagues':{lid:evaluate_league(history['leagues'][lid]['seasons'],quality['leagues'][lid]) for lid in ('pt','dk')},
            'guardrails':{'minimum_prospective_forecasts':MIN_PROSPECTIVE,'bookmaker_odds_source':'manual_only',
                          'validated_profitability':False,'automated_bets':False,
                          'disclosure':'Positive theoretical EV is not evidence of value; calibration uncertainty and bookmaker margin can erase it.'}}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--history',type=Path,default=ROOT/'data'/'history.json')
    p.add_argument('--quality',type=Path,default=ROOT/'data'/'quality.json')
    p.add_argument('--output',type=Path,default=ROOT/'data'/'value_engine.json')
    args=p.parse_args()
    result=build(json.loads(args.history.read_text(encoding='utf8')),
                 json.loads(args.quality.read_text(encoding='utf8')))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf8')
    print('Value Engine v5: '+json.dumps({lid:{'status':x['status'],'fit':x.get('validation_games',0),
                         'holdout':x.get('test_games',0),
                         'over_2_5':x.get('markets',{}).get('over_2_5',{}).get('holdout',{}).get('brier_calibration_gain')}
                         for lid,x in result['leagues'].items()},ensure_ascii=False))

if __name__=='__main__':
    main()
