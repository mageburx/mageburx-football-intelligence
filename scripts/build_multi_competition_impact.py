#!/usr/bin/env python3
"""Experimental backtest of cup/UEFA game load on league 1X2 forecasts.

Not a marketing lift study: sparse historical cross-competition coverage
causes EXPLICIT BLOCKING, not zero-filled proof of "no fatigue effect".
The train/selection/test split remains 2021–24 / 2024–25 / 2025–26.
Nothing in this file changes published win probabilities or betting advice.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import math
from collections import defaultdict
from pathlib import Path
try:
    from scripts.build_model import goal_rates, score_probs, finished
    from scripts.build_feature_impact import match_outcome,multi_metrics,gain_interval,clamp
    from scripts.collect_cross_competitions import canonical,normal
except ModuleNotFoundError:
    from build_model import goal_rates, score_probs, finished
    from build_feature_impact import match_outcome,multi_metrics,gain_interval,clamp
    from collect_cross_competitions import canonical,normal

ROOT=Path(__file__).resolve().parents[1]
HISTORY=ROOT/'data'/'history.json'
CROSS=ROOT/'data'/'cross_competitions.json'
QUALITY=ROOT/'data'/'quality.json'
OUTPUT=ROOT/'data'/'multi_competition_impact.json'
TRAIN=('2021-2022','2022-2023','2023-2024')
FIT='2024-2025'
TEST='2025-2026'
MIN_CROSS_MATCHES=20
MIN_AFFECTED_FIXTURES=30
MIN_TEAM_FRACTION=0.45
SELECT_THRESHOLD=.005
CANDIDATES={
  'baseline':(0,0),
  'all_competitions_rest':(.10,0),
  'rest_plus_cup_uefa_load':(.10,.06),
}

def date_year_season(date):
    year=int(date[:4])
    return f'{year}-{year+1}' if int(date[5:7])>=7 else f'{year-1}-{year}'

def norm_team(s):
    return normal(canonical(s))

def extra_games_before(cross,date,home,away,days=21):
    """Only historically completed fixtures before target kick-off date."""
    start=dt.date.fromisoformat(date)
    teams=(norm_team(home),norm_team(away))
    records={team:[] for team in teams}
    # Deduplicate DBU and secondary-source listings by normalized
    # date/home/away, not by provider ID.
    seen=set()
    for e in cross:
        if not e.get('finished') or e.get('date','')>=date:
            continue
        if e.get('competition_type') not in ('domestic_cup','european'):
            continue
        diff=(start-dt.date.fromisoformat(e['date'])).days
        if not (0<diff<=days):continue
        h,a=norm_team(e.get('home','')),norm_team(e.get('away',''))
        key=(e['date'],h,a)
        if key in seen:continue
        seen.add(key)
        for team in teams:
            if team in (h,a):records[team].append(e['date'])
    return records

def recent_context(before,cross,date,home,away):
    anchor=dt.date.fromisoformat(date)
    cross_games=extra_games_before(cross,date,home,away,21)
    result={}
    for t in (home,away):
        k=norm_team(t)
        prior_league=[e['date'] for e in before if
                      e['date']<date and k in (norm_team(e['home']),norm_team(e['away']))]
        extra=cross_games[k]
        last=max(prior_league+extra) if prior_league or extra else None
        rest=(anchor-dt.date.fromisoformat(last)).days if last else None
        result[k]={'rest':rest,
                   'additional_14':sum((anchor-dt.date.fromisoformat(d)).days<=14 for d in extra),
                   'additional_21':len(extra)}
    return result

def candidate_rates(rates,ctx,home,away,candidate):
    rest_weight,extra_weight=CANDIDATES[candidate]
    h,a=ctx[norm_team(home)],ctx[norm_team(away)]
    if h['rest'] is None or a['rest'] is None:
        rest_edge=0
    else:
        rest_edge=clamp((min(14,h['rest'])-min(14,a['rest']))/7)
    # More cup games for the home club should not be presumed to improve
    # its goal rate (positive edge when away played more).
    load_edge=clamp((a['additional_14']-h['additional_14'])/2)
    factor=clamp(rest_weight*rest_edge+extra_weight*load_edge,-.35,.35)
    return max(.15,min(4,rates[0]*math.exp(factor))),max(.15,min(4,rates[1]*math.exp(-factor)))

def source_coverage(events,cross,season):
    all_events=[e for e in events if finished(e) and date_year_season(e['date'])==season]
    clubs={norm_team(t) for e in all_events for t in (e['home'],e['away'])}
    cup=[e for e in cross if e.get('finished') and
         e.get('date','') and date_year_season(e['date'])==season and
         e.get('competition_type') in ('domestic_cup','european')]
    relevant=[e for e in cup if norm_team(e['home']) in clubs or norm_team(e['away']) in clubs]
    relevant_unique={ (e['date'],norm_team(e['home']),norm_team(e['away'])) for e in relevant }
    # Separate domestic cups from UEFA games for source-coverage diagnostics.
    # Counts are unique by match date and canonical teams, never source ID.
    def unique_of_type(kind):
        return {(e['date'],norm_team(e['home']),norm_team(e['away']))
                for e in relevant if e['competition_type']==kind}
    cup_unique=unique_of_type('domestic_cup')
    european_unique=unique_of_type('european')
    clubs_seen={k for e in relevant for k in (norm_team(e['home']),norm_team(e['away'])) if k in clubs}
    sufficient=len(relevant_unique)>=MIN_CROSS_MATCHES and (
        len(clubs_seen)/len(clubs)>=MIN_TEAM_FRACTION if clubs else False)
    return {'league_teams':len(clubs),'teams_with_additional_fixtures':len(clubs_seen),
            'known_cross_matches':len(relevant_unique),
            'known_domestic_cup_matches':len(cup_unique),
            'known_european_matches':len(european_unique),
            'adequate_minimum_sample':sufficient,
            'coverage_certified_complete':False}

def evaluate_league(seasons,quality,cross):
    needed=(*TRAIN,FIT,TEST)
    missing=[s for s in needed if not quality.get('seasons',{}).get(s,{}).get('complete')]
    if missing:return {'status':'blocked_incomplete_league_history','missing':missing}
    league=sorted((e for s in needed for e in seasons[s]['events'] if finished(e)),
                  key=lambda e:(e['date'],str(e.get('id',''))))
    coverage={s:source_coverage(league,cross,s) for s in (FIT,TEST)}
    if not all(v['adequate_minimum_sample'] for v in coverage.values()):
        return {'status':'blocked_sparse_cross_competition_history',
                'coverage':coverage,'models':{},'selected':None,
                'reason':'Cannot measure cup/UEFA lift until both validation and holdout have sufficient team-specific cup coverage.'}
    score={'fit':defaultdict(list),'holdout':defaultdict(list)}
    affected=defaultdict(int)
    for match in league:
        date=match['date']
        if not (FIT[:4]+'-07-01'<=date<str(int(TEST[:4])+1)+'-07-01'):continue
        stage='fit' if date<TEST[:4]+'-07-01' else 'holdout'
        before=[e for e in league if e['date']<date]
        rates=goal_rates(before,date,match['home'],match['away'])
        if rates is None:continue
        ctx=recent_context(before,cross,date,match['home'],match['away'])
        if any(v['additional_21']>0 for v in ctx.values()):affected[stage]+=1
        y=match_outcome(match)
        for name in CANDIDATES:
            x,y_rate=candidate_rates(rates,ctx,match['home'],match['away'],name)
            score[stage][name].append((date,score_probs(x,y_rate,dc=True)['p'],y))
    if affected['fit']<MIN_AFFECTED_FIXTURES or affected['holdout']<MIN_AFFECTED_FIXTURES:
        return {'status':'blocked_insufficient_exposed_fixtures',
                'coverage':coverage,'affected':dict(affected),
                'reason':'Not enough league fixtures with a known preceding cup/European match.'}
    fit={n:multi_metrics(score['fit'][n]) for n in CANDIDATES}
    selection=min(CANDIDATES,key=lambda n:fit[n]['brier'])
    if fit['baseline']['brier']-fit[selection]['brier']<SELECT_THRESHOLD:
        selection='baseline'
    models={}
    for n in CANDIDATES:
        models[n]={'fit':fit[n],'holdout':multi_metrics(score['holdout'][n]),
                   'holdout_gain_ci95':gain_interval(score['holdout']['baseline'],score['holdout'][n])}
    base=models['baseline']['holdout']
    chosen=models[selection]['holdout']
    diff=round(base['brier']-chosen['brier'],5)
    ci=models[selection]['holdout_gain_ci95']
    return {'status':'inconclusive_historical_experiment' if (
             selection=='baseline' or ci[0]<=0 or chosen['n']<200) else
             'historical_lift_not_yet_prospective',
            'coverage':coverage,'affected':dict(affected),
            'selected':selection,'selected_holdout_gain':diff,'selected_ci95':ci,
            'models':models,
            'warning':'Even above the coverage threshold, historical cup data are partial; the observed improvement may be biased. No live model changes.'}

def build(history,quality,cross):
    return {'schema':1,'version':'5.3-experimental',
            'generated_at':dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
            'method':'Calendar-year/date bounded pre-match rest, predeclared fixed fatigue coefficients; selection 2024/25, untouched 2025/26.',
            'policy':'Do not apply to live predictions or infer betting profitability.',
            'minimum_coverage':{'known_cross_fixtures_per_season':MIN_CROSS_MATCHES,
                                'fraction_of_league_teams':MIN_TEAM_FRACTION,
                                'league_games_exposed_each_test_period':MIN_AFFECTED_FIXTURES},
            'leagues':{lid:evaluate_league(history['leagues'][lid]['seasons'],
                           quality['leagues'][lid],cross.get('events',[]))
                       for lid in ('pt','dk')},
            'caveat':'Cups and UEFA coverage remains partial; no conclusion from non-significant results or missing fixtures.'}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--history',type=Path,default=HISTORY)
    p.add_argument('--quality',type=Path,default=QUALITY)
    p.add_argument('--cross',type=Path,default=CROSS)
    p.add_argument('--output',type=Path,default=OUTPUT)
    args=p.parse_args()
    d=build(json.loads(args.history.read_text(encoding='utf8')),
            json.loads(args.quality.read_text(encoding='utf8')),
            json.loads(args.cross.read_text(encoding='utf8')))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(d,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf8')
    print('Cross competition experiment: '+json.dumps({
        lid:{'status':x['status'],'selected':x.get('selected'),
             'coverage':x.get('coverage')} for lid,x in d['leagues'].items()},ensure_ascii=False))

if __name__=='__main__':
    main()
