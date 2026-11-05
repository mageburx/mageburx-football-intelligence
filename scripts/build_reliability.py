#!/usr/bin/env python3
"""Reliability audit, with untouched historical holdout and prospective ledger.

Retrospective walk-forward predictions are NOT real archived pre-match tips;
the prospective ledger is a separate append-only prediction record.
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
except ModuleNotFoundError:  # python scripts/build_reliability.py
    from build_model import MARKET_LABELS, finished, goal_rates, score_probs, market_settles

ROOT = Path(__file__).resolve().parents[1]
SEASONS = ('2021-2022', '2022-2023', '2023-2024', '2024-2025', '2025-2026')

def summary(records):
    """Each record: (date, forecast_probability, observed_binary, prior_baseline)."""
    n = len(records)
    if not n:
        return {'n': 0, 'status': 'insuficiente', 'calibration_bins': [], 'monthly': []}
    errors = [(p-y)**2 for _, p, y, _ in records]
    base_errors = [(base-y)**2 for _, p, y, base in records]
    delta = [b-e for b, e in zip(base_errors, errors)]
    mean_model = sum(errors)/n
    mean_base = sum(base_errors)/n
    advantage = sum(delta)/n
    sample_variance = sum((x-advantage)**2 for x in delta)/(n-1) if n > 1 else 0.0
    margin = 1.96*math.sqrt(sample_variance/n)
    confidence = [round(advantage-margin, 5), round(advantage+margin, 5)]
    logloss = -sum(y*math.log(p)+(1-y)*math.log1p(-p) for _,p,y,_ in records)/n
    bins = []
    for i in range(5):
        observations = [(p,y) for _,p,y,_ in records if i/5<=p<(i+1)/5 or (i==4 and p==1)]
        if observations:
            bins.append({'range':f'{20*i}-{20*(i+1)}%', 'n':len(observations),
                         'mean_prediction':round(sum(p for p,_ in observations)/len(observations),4),
                         'observed_frequency':round(sum(y for _,y in observations)/len(observations),4)})
    ece=sum(b['n']/n*abs(b['mean_prediction']-b['observed_frequency']) for b in bins)
    months = defaultdict(list)
    for date, p, y, base in records:
        months[date[:7]].append((p-y)**2)
    monthly=[{'month':date,'n':len(v),'brier':round(sum(v)/len(v),4)}
             for date,v in sorted(months.items())]
    return {'n':n,'brier':round(mean_model,4),'baseline_brier':round(mean_base,4),
            'brier_skill':round(1-mean_model/mean_base,4) if mean_base>0 else None,
            'brier_gain_ci95':confidence,'log_loss':round(logloss,4),
            'ece':round(ece,4),'calibration_bins':bins,'monthly':monthly,
            'observed_frequency':round(sum(y for _,_,y,_ in records)/n,4)}

def historical_holdout(seasons):
    """Reserve one late season, train only on earlier seasons, never same-day."""
    sets=[]
    for name in SEASONS:
        item=seasons.get(name)
        if not item:continue
        matches=sorted([e for e in item.get('events',[]) if finished(e)],key=lambda e:(e['date'],str(e.get('id'))))
        sets.append((name, matches, bool(item.get('complete')), int(item.get('expected_games') or 0)))
    candidates=[]
    for i,(name,events,complete,expected) in enumerate(sets):
        train=sum(len(s[1]) for s in sets[:i])
        if train>=150 and len(events)>=150:
            candidates.append((i,name,events,complete,expected))
    if not candidates:
        return None, []
    # Use the most recent adequately covered season; this is retrospective
    # held-out testing of fixed code, never selection or calibration on that holdout.
    i,name,events,complete,expected=candidates[-1]
    past=[e for _,season_events,_,_ in sets[:i] for e in season_events]
    return {'season':name,'games':len(events),'complete':complete,'expected_games':expected,
            'training_seasons':[x[0] for x in sets[:i]],
            'train_games':len(past)}, past+events

def audit_league(seasons):
    selected, all_events=historical_holdout(seasons)
    coverage={name:{'games':len(item.get('events',[])),
                    'complete':bool(item.get('complete')),
                    'expected':item.get('expected_games')} for name,item in sorted(seasons.items())
              if name in SEASONS}
    if selected is None:
        return {'coverage':coverage,'holdout':None,'metrics':{},'warning':'Sem épocas anteriores suficientes para testar outra época.'}
    holdout=selected['season']
    holdout_games=[e for e in all_events if e['date'][:4]==holdout[:4] and e['date']>=holdout[:4]+'-07-01' and e['date']<(str(int(holdout[:4])+1))+'-07-01']
    # The date boundary, not a mutable season label, identifies the test set.
    # Deduplicate source records by season/id.
    holdout_games=sorted(holdout_games,key=lambda e:(e['date'],str(e.get('id'))))
    records=defaultdict(list)
    for event in holdout_games:
        before=[e for e in all_events if e['date']<event['date']]
        rates=goal_rates(before,event['date'],event['home'],event['away'])
        if rates is None:
            continue
        fixed=score_probs(*rates,dc=True)
        markets=dict(fixed['markets'])
        markets.update({'double_1x':fixed['p'][0]+fixed['p'][1],
                        'double_x2':fixed['p'][1]+fixed['p'][2],
                        'double_12':fixed['p'][0]+fixed['p'][2]})
        for key in MARKET_LABELS:
            if key not in markets:continue
            prob=min(1-1e-9,max(1e-9,markets[key]))
            observed=market_settles(event,key)
            prev=[market_settles(p,key) for p in before]
            baseline=(1+sum(prev))/(2+len(prev))
            records[key].append((event['date'],prob,observed,baseline))
    result={}
    for key in MARKET_LABELS:
        m=summary(records[key])
        if not selected['complete']:
            status='historico_parcial'
        elif m['n']<100:
            status='amostra_insuficiente'
        elif m['n']<200:
            status='preliminar'
        elif m['brier_gain_ci95'][1]<0:
            status='pior_que_referencia'
        elif m['brier_gain_ci95'][0]>0:
            status='sinal_historico_a_confirmar'
        else:
            status='inconclusivo'
        m['status']=status
        result[key]=m
    return {'coverage':coverage,'holdout':selected,'metrics':result,
            'warning':'Backtesting retrospetivo, não previsões realmente guardadas antes dos jogos. O modelo fixo não foi calibrado neste período; os parâmetros históricos não são evidência de lucro.'}

def prospective_audit(ledger):
    predictions=ledger.get('predictions',[])
    settlements={p['key']:p for p in ledger.get('settlements',[])}
    grouped=defaultdict(lambda:defaultdict(list))
    for prediction in predictions:
        event=settlements.get(prediction['key'])
        if not event:continue
        for market, probability in prediction.get('markets',{}).items():
            if market not in MARKET_LABELS or not isinstance(probability,(int,float)):continue
            y=market_settles(event,market)
            # Ledger forecasts are pre-match; no fake baseline or backfill.
            grouped[prediction['league']][market].append((event['date'],max(1e-9,min(1-1e-9,probability)),y,.5))
    result={}
    for lid,markets in grouped.items():
        result[lid]={k:summary(records) for k,records in markets.items()}
    return {'logged':len(predictions),'settled':len(settlements),
            'metrics':result,'warning':'Só previsões guardadas com antecedência. A referência de 50% no ledger é apenas ilustrativa; não se atribui skill prospetivo.'}

def build(history, ledger=None):
    return {'schema':1,
            'generated_at':dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
            'method':'Dixon–Coles com parâmetros fixos; teste cronológico numa época reservada; referência causal; CI95 normal aproximado de diferença Brier',
            'source':history.get('source',{}),
            'history':{lid:audit_league(info.get('seasons',{})) for lid,info in history.get('leagues',{}).items()},
            'prospective':prospective_audit(ledger or {}),
            'note':'Fiabilidade estatística não equivale a vantagem monetária. xG e odds reais não foram utilizados.'}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--history',type=Path,default=ROOT/'data'/'history.json')
    p.add_argument('--ledger',type=Path,default=ROOT/'data'/'ledger.json')
    p.add_argument('--output',type=Path,default=ROOT/'data'/'reliability.json')
    args=p.parse_args()
    data=json.loads(args.history.read_text(encoding='utf-8'))
    ledger=json.loads(args.ledger.read_text(encoding='utf-8')) if args.ledger.exists() else {}
    result=build(data,ledger)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    print('Reliability:',json.dumps({lid:{'holdout':v['holdout'],'n_over_25':v['metrics'].get('over_2_5',{}).get('n',0)}
                                   for lid,v in result['history'].items()},ensure_ascii=False))

if __name__=='__main__':
    main()
