#!/usr/bin/env python3
"""Research-only pre-match signal from already observed shots on target.

Does not affect published Poisson/Dixon-Coles probabilities. No historical
performance claim is possible without independently time-stamped feature data
and an out-of-sample test period.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
from pathlib import Path

try:
    from scripts.collect_cross_competitions import canonical,normal
except ModuleNotFoundError:
    from collect_cross_competitions import canonical,normal

ROOT=Path(__file__).resolve().parents[1]
INPUT=ROOT/'data'/'advanced_signals.json'
SEASON=ROOT/'data'/'season.json'
OUTPUT=ROOT/'data'/'shots_research.json'
ALIASES={'aarhus':'agf aarhus','ac horsens':'horsens'}


def team_key(name):
    initial=normal(canonical(name))
    return ALIASES.get(initial,initial)


def timeline(recs,team,target_date,now):
    choices=[]
    for r in recs:
        if r.get('date','')>=target_date:continue
        try:
            observed=dt.datetime.fromisoformat(r.get('first_observed_at',''))
            if observed.tzinfo is None or observed>now:continue
            age=(dt.date.fromisoformat(target_date)-dt.date.fromisoformat(r['date'])).days
            if age>90:continue
        except (ValueError,TypeError,KeyError):continue
        vals=r.get('shots_on_target')
        if not isinstance(vals,list) or len(vals)!=2 or any(type(x) not in (int,float) for x in vals):
            continue
        home,away=team_key(r.get('home','')),team_key(r.get('away',''))
        if team==home:choices.append((r['date'],float(vals[0]),float(vals[1])))
        elif team==away:choices.append((r['date'],float(vals[1]),float(vals[0])))
    return sorted(choices,key=lambda x:x[0],reverse=True)[:5]


def build(signals,season,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    today=now.date().isoformat()
    result={'schema':1,'generated_at':now.replace(microsecond=0).isoformat(),
            'status':'research_only_no_proven_lift',
            'method':'Rolling five previous recorded games within 90 days, strictly before target match. Shot-on-target pressure is descriptive, not a probability.',
            'production_model_changed':False,'historical_backtest_validated':False,
            'source_attribution':'Data by Cornerflick — cornerflick.com',
            'leagues':{}}
    for lid in ('pt','dk'):
        source=signals.get('leagues',{}).get(lid,{})
        rows=source.get('records',[])
        usable=[r for r in rows if isinstance(r,dict)]
        summary={'sample_matches':len(usable),
                 'shots_recorded':sum(r.get('shots') is not None for r in usable),
                 'shots_on_target_recorded':sum(r.get('shots_on_target') is not None for r in usable),
                 'xg_recorded':sum(r.get('xg') is not None for r in usable),
                 'source_status':source.get('status','not_checked'),
                 'source_error':source.get('error'),
                 'readiness':'insufficient_historical_coverage',
                 'candidates':[]}
        fixtures=season.get('leagues',{}).get(lid,{}).get('events',[])
        for match in fixtures:
            if match.get('finished') or match.get('date','')<=today:continue
            h=timeline(usable,team_key(match.get('home','')),match['date'],now)
            a=timeline(usable,team_key(match.get('away','')),match['date'],now)
            ready=len(h)>=3 and len(a)>=3
            def average(v,i):
                return round(sum(x[i] for x in v)/len(v),2) if v else None
            home_for,home_against=average(h,1),average(h,2)
            away_for,away_against=average(a,1),average(a,2)
            home_pressure=round((home_for+away_against)/2,2) if ready else None
            away_pressure=round((away_for+home_against)/2,2) if ready else None
            summary['candidates'].append({
                'match_id':str(match.get('id','')),'date':match['date'],
                'home':match.get('home'),'away':match.get('away'),
                'recent_samples_home':len(h),'recent_samples_away':len(a),
                'home_sot_for_avg':home_for,'away_sot_for_avg':away_for,
                'pressure_home':home_pressure,'pressure_away':away_pressure,
                'status':'observational_signal_only' if ready else 'insufficient_sample',
                'adjusts_probability':False})
        summary['candidates']=summary['candidates'][:40]
        result['leagues'][lid]=summary
    result['warning']='No xG is inferred from shots; absent xG is unknown. Data rights and pre-match timestamps must be verified before commercial/automated model use. No 2024/25-2025/26 shot history to validate a prediction lift.'
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--observations',type=Path,default=INPUT)
    p.add_argument('--season',type=Path,default=SEASON)
    p.add_argument('--output',type=Path,default=OUTPUT)
    args=p.parse_args()
    signals=json.loads(args.observations.read_text(encoding='utf8')) if args.observations.exists() else {}
    season=json.loads(args.season.read_text(encoding='utf8'))
    report=build(signals,season)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf8')
    print('Shots research:',json.dumps({k:{'samples':v['sample_matches'],
                                          'xg':v['xg_recorded'],
                                          'sot':v['shots_on_target_recorded']}
            for k,v in report['leagues'].items()}),flush=True)


if __name__=='__main__':
    main()
