#!/usr/bin/env python3
"""Feature Impact Lab v5.1 — pre-match contextual variables, never future information.

The goal is predictive *incremental value* (not causation). Only full-time
league results are available historically: 'rest' means time since prior
*LEAGUE* match, not true all-competition physical recovery. Elo-adjusted
surprise form uses each past match's PRE-match Elo, grouped by date.

Three fixed, predeclared contextual candidates are compared with unchanged
Dixon-Coles on 2024/25; one selected there is evaluated untouched on 2025/26.
Live forecasts are NEVER modified by this research script.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import math
from collections import defaultdict
from pathlib import Path
try:
    from scripts.build_model import (goal_rates, score_probs, finished, normalise,
                                     HOME_ELO, ELO_K, match_key)
except ModuleNotFoundError:
    from build_model import (goal_rates, score_probs, finished, normalise,
                             HOME_ELO, ELO_K, match_key)

ROOT=Path(__file__).resolve().parents[1]
TRAIN=('2021-2022','2022-2023','2023-2024')
FIT='2024-2025'
HOLDOUT='2025-2026'
SPLIT=(*TRAIN,FIT,HOLDOUT)
REST_WEIGHT=0.10
FORM_WEIGHT=0.18
CHOOSE_MIN_BRIER_GAIN=0.005
CANDIDATES={
    'baseline': (0,0),
    'rest': (REST_WEIGHT,0),
    'strength_adjusted_form': (0,FORM_WEIGHT),
    'rest_plus_form': (REST_WEIGHT,FORM_WEIGHT),
}

def match_outcome(e):
    return 0 if e['home_score']>e['away_score'] else 1 if e['home_score']==e['away_score'] else 2

def outcome_points(e,team):
    if e['home_score']==e['away_score']:return 1
    return 3 if (e['home']==team)==(e['home_score']>e['away_score']) else 0

def clamp(value, lo=-1, hi=1):
    return max(lo,min(hi,value))

def elo_surprises(all_events):
    """Surprise points for each completed event computed BEFORE that date.

    Elo states update in batches so results on the same calendar day never
    influence each other's expectations. Uses no bookmaker or xG data.
    """
    events=sorted((e for e in all_events if finished(e)),
                  key=lambda e:(e['date'],str(e.get('id',''))))
    days=defaultdict(list)
    for e in events:days[e['date']].append(e)
    ratings=defaultdict(lambda:1500.0)
    mapped={}
    for day in sorted(days):
        delta=defaultdict(float)
        for e in days[day]:
            home,away=e['home'],e['away']
            expected=1/(1+10**(-(ratings[home]+HOME_ELO-ratings[away])/400))
            draw=0.26 # fixed, not trained on holdout
            xh=3*(1-draw)*expected+draw
            xa=3*(1-draw)*(1-expected)+draw
            mapped[match_key(e)]=( (outcome_points(e,home)-xh)/3,
                                     (outcome_points(e,away)-xa)/3 )
            actual=1 if e['home_score']>e['away_score'] else (.5 if e['home_score']==e['away_score'] else 0)
            delta[home]+=ELO_K*(actual-expected)
            delta[away]-=ELO_K*(actual-expected)
        for team,change in delta.items():ratings[team]+=change
    return mapped

def features(before,date,home,away,pre_match_surprises):
    """Only league results strictly earlier than date; neutral if unavailable."""
    target=dt.date.fromisoformat(date)
    team_games={}
    for team in (home,away):
        games=sorted((e for e in before if e['date']<date and team in (e['home'],e['away'])),
                     key=lambda e:(e['date'],str(e.get('id',''))))
        team_games[team]=games
    gaps={}
    for team,games in team_games.items():
        if not games:gaps[team]=None
        else:
            gap=(target-dt.date.fromisoformat(games[-1]['date'])).days
            gaps[team]=gap if 1<=gap<=60 else None
    rest_edge=0.0
    rest_covered=all(gaps[x] is not None for x in (home,away))
    if rest_covered:
        rest_edge=clamp((min(14,gaps[home])-min(14,gaps[away]))/7.0)
    def form(team):
        games=team_games[team][-5:]
        if len(games)<3:return None
        vals=[]
        for event in games:
            value=pre_match_surprises.get(match_key(event))
            if value is None:continue
            vals.append(value[0] if event['home']==team else value[1])
        return sum(vals)/len(vals) if len(vals)>=3 else None
    hf,af=form(home),form(away)
    form_covered=hf is not None and af is not None
    form_edge=clamp(hf-af) if form_covered else 0.0
    def density(team):
        return sum(0 < (target-dt.date.fromisoformat(e['date'])).days <= 14
                   for e in team_games[team])
    return {'rest_days_home':gaps[home],'rest_days_away':gaps[away],
            'rest_edge':round(rest_edge,6),'rest_available':rest_covered,
            'form_edge':round(form_edge,6),'form_available':form_covered,
            'league_matches_last14_home':density(home),
            'league_matches_last14_away':density(away)}

def predict_rates(lh,la,vector,candidate):
    rest_weight,form_weight=CANDIDATES[candidate]
    factor=clamp(rest_weight*vector['rest_edge']+form_weight*vector['form_edge'],-0.4,0.4)
    return (max(.15,min(4,lh*math.exp(factor))),
            max(.15,min(4,la*math.exp(-factor))))

def multiclass_brier(p,y):
    return sum((p[i]-(1 if i==y else 0))**2 for i in range(3))

def multi_metrics(rows):
    n=len(rows)
    if not n:return {'n':0}
    return {'n':n,
            'brier':round(sum(multiclass_brier(p,y) for _,p,y in rows)/n,5),
            'log_loss':round(-sum(math.log(max(1e-9,p[y])) for _,p,y in rows)/n,5)}

def gain_interval(reference,variant):
    """Normal approximate paired CI; fixture dependence can underestimate risk."""
    if len(reference)!=len(variant) or not reference:return None
    delta=[multiclass_brier(p0,y)-multiclass_brier(p1,y)
           for (_,p0,y),(_,p1,_) in zip(reference,variant)]
    n=len(delta)
    mean=sum(delta)/n
    var=sum((x-mean)**2 for x in delta)/(n-1) if n>1 else 0
    margin=1.96*math.sqrt(var/n)
    return [round(mean-margin,5),round(mean+margin,5)]

def evaluate_league(seasons,quality):
    missing=[year for year in SPLIT if not quality.get('seasons',{}).get(year,{}).get('complete')]
    if missing:return {'status':'blocked_incomplete_history','missing':missing}
    hist=sorted((e for season in SPLIT for e in seasons[season]['events'] if finished(e)),
                key=lambda e:(e['date'],str(e.get('id',''))))
    surprise=elo_surprises(hist)
    score={'fit':defaultdict(list),'holdout':defaultdict(list)}
    coverage={stage:{'rest':0,'form':0,'n':0} for stage in ('fit','holdout')}
    for match in hist:
        date=match['date']
        if not (FIT[:4]+'-07-01'<=date<str(int(HOLDOUT[:4])+1)+'-07-01'):continue
        stage='fit' if date<HOLDOUT[:4]+'-07-01' else 'holdout'
        before=[e for e in hist if e['date']<date]
        rates=goal_rates(before,date,match['home'],match['away'])
        if rates is None:continue
        vector=features(before,date,match['home'],match['away'],surprise)
        coverage[stage]['n']+=1
        coverage[stage]['rest']+=int(vector['rest_available'])
        coverage[stage]['form']+=int(vector['form_available'])
        for variant in CANDIDATES:
            lh,la=predict_rates(*rates,vector,variant)
            probs=score_probs(lh,la,dc=True)['p']
            score[stage][variant].append((date,probs,match_outcome(match)))
    fit={k:multi_metrics(v) for k,v in score['fit'].items()}
    if min(x.get('n',0) for x in fit.values())<100:
        return {'status':'insufficient_validation_samples','validation':fit}
    candidate=min(CANDIDATES, key=lambda k:fit[k]['brier'])
    if fit['baseline']['brier']-fit[candidate]['brier']<CHOOSE_MIN_BRIER_GAIN:
        candidate='baseline'
    results={}
    for k in CANDIDATES:
        results[k]={'fit':fit[k],'holdout':multi_metrics(score['holdout'][k]),
                    'holdout_brier_gain_ci95':gain_interval(score['holdout']['baseline'],
                                                            score['holdout'][k])}
    selected=results[candidate]
    baseline=results['baseline']['holdout']
    chosen=selected['holdout']
    gain=round(baseline['brier']-chosen['brier'],5)
    ci=selected['holdout_brier_gain_ci95']
    status='no_measured_advantage'
    if candidate!='baseline' and gain>0 and ci and ci[0]>0 and chosen['n']>=200:
        status='historical_lift_requires_prospective_replication'
    elif candidate!='baseline' and gain>0:
        status='inconclusive_historical_lift'
    elif candidate!='baseline':
        status='feature_model_worse_on_holdout'
    return {'status':status,'selected_on_2024_25':candidate,
            'selected_holdout_brier_gain':gain,
            'selected_holdout_ci95':ci,
            'feature_coverage':coverage,'variants':results,
            'warnings':['Includes league fixtures only; rest does not include cup/European games.',
                        'Opponent-strength form is computed from historical pre-match Elo.',
                        'This is predictive association, not causal impact.',
                        'Candidate chosen only on 2024/25; 2025/26 kept untouched.',
                        'No live forecast is changed automatically.']}

def build(history,quality):
    return {'schema':1,'version':'5.1-experimental',
            'generated_at':dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
            'protocol':'Four predeclared fixed-parameter Dixon-Coles variants; fit-season selection 2024/25; untouched 2025/26 holdout; multiclass 1X2 Brier & Log Loss.',
            'factors':['days_since_last_league_match','league_match_density_14_days',
                       'five_match_strength_adjusted_surprise_points'],
            'excluded_untested':['confirmed_injuries','actual_lineup','xg','travel','weather'],
            'leagues':{lid:evaluate_league(history['leagues'][lid]['seasons'],quality['leagues'][lid])
                       for lid in ('pt','dk')},
            'policy':'Research only; do not use for betting recommendations without independent and prospective validation.'}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--history',type=Path,default=ROOT/'data'/'history.json')
    parser.add_argument('--quality',type=Path,default=ROOT/'data'/'quality.json')
    parser.add_argument('--output',type=Path,default=ROOT/'data'/'feature_impact.json')
    args=parser.parse_args()
    data=build(json.loads(args.history.read_text(encoding='utf8')),
               json.loads(args.quality.read_text(encoding='utf8')))
    args.output.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf8')
    print(json.dumps({lid:{'status':result['status'],
                           'chosen':result.get('selected_on_2024_25'),
                           'gain':result.get('selected_holdout_brier_gain')}
                      for lid,result in data['leagues'].items()},ensure_ascii=False))

if __name__=='__main__':
    main()
