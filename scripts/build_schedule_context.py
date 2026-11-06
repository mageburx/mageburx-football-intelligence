#!/usr/bin/env python3
"""Known-fixture schedule context without fabricated complete cup coverage.

Includes completed league, domestic-cup and UEFA fixtures dated strictly
before each target game. Counts are a *lower bound* while cross-competition
sources remain partial. Data sourced from another tournament is NEVER
passed into league goal-rate fitting or Elo model updates.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
from collections import Counter
from pathlib import Path
try:
    from scripts.collect_cross_competitions import canonical, normal
except ModuleNotFoundError:
    from collect_cross_competitions import canonical, normal

ROOT=Path(__file__).resolve().parents[1]
CROSS=ROOT/'data'/'cross_competitions.json'
SEASON=ROOT/'data'/'season.json'
OUT=ROOT/'data'/'schedule_context.json'

def same_team(a,b):
    return normal(canonical(a))==normal(canonical(b))

def context(target,league_events,cross_events,asof=None):
    """Every known earlier fixture, never same-day or future results."""
    target_date=target.get('date')
    when=dt.date.fromisoformat(target_date)
    event_pool=[]
    for e in league_events:
        if not e.get('finished') or not e.get('date') or e['date']>=target_date:
            continue
        event_pool.append({**e,'competition':'Liga','competition_type':'league'})
    for e in cross_events:
        if not e.get('finished') or not e.get('date') or e['date']>=target_date:
            continue
        event_pool.append(e)
    out={}
    for position in ('home','away'):
        team=target[position]
        matches=[e for e in event_pool if same_team(e.get('home',''),team) or
                 same_team(e.get('away',''),team)]
        # Avoid duplicate events on same team/date/opponent; never fabricate missing
        # fixtures; a conflict from different competitions must be audited.
        unique={}
        for e in matches:
            opponent=e['away'] if same_team(e['home'],team) else e['home']
            key=(e['date'],normal(canonical(opponent)))
            existing=unique.get(key)
            if not existing or (existing.get('competition_type')!='league' and
                                e.get('competition_type')=='league'):
                unique[key]=e
        ordered=sorted(unique.values(),key=lambda e:(e['date'],str(e.get('id',''))),reverse=True)
        prior=ordered[0] if ordered else None
        rest=(when-dt.date.fromisoformat(prior['date'])).days if prior else None
        counts={}
        for n in (7,14,21):
            counts[str(n)]=sum(0<(when-dt.date.fromisoformat(e['date'])).days<=n for e in ordered)
        out[position]={
            'team':team,'last_known_match_date':prior['date'] if prior else None,
            'last_known_competition':prior.get('competition') if prior else None,
            'days_since_last_known_match':rest if rest and rest>0 else None,
            'matches_last_7':counts['7'],'matches_last_14':counts['14'],
            'matches_last_21':counts['21'],
            'cup_europe_last_21':sum(e.get('competition_type')!='league' and
                0<(when-dt.date.fromisoformat(e['date'])).days<=21 for e in ordered),
            'last_known_fixture_count':len(ordered),
        }
    out['partial_coverage']=True
    out['note']='Lower bound: some cup/UEFA fixtures not yet collected; true rest may be shorter.'
    return out

def build(season,cross,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    merged=[]
    for e in cross.get('events',[]):
        if e.get('competition_type') not in ('domestic_cup','european'):
            continue
        merged.append(e)
    leagues={}
    for lid,info in season.get('leagues',{}).items():
        league_events=info.get('events',[])
        items={}
        for e in league_events:
            if e.get('finished') or not e.get('date') or e['date']<now.date().isoformat():
                continue
            items[str(e['id'])]=context(e,league_events,merged)
        leagues[lid]={'fixtures':items,'count':len(items)}
    coverage=Counter(e.get('competition_id') for e in merged if e.get('finished'))
    return {'schema':1,'version':'5.2','generated_at':now.isoformat(),
            'status':'partial_cross_competition_coverage',
            'covered_competitions':dict(coverage),
            'cross_events_total':len(merged),'cross_events_completed':sum(e.get('finished') for e in merged),
            'leagues':leagues,'disclaimer':'Known fixture counts are lower bounds, not certified complete schedules. Same-day results excluded. No prediction changes.'}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output',type=Path,default=OUT)
    args=p.parse_args()
    league=json.loads(SEASON.read_text(encoding='utf-8'))
    crosses=json.loads(CROSS.read_text(encoding='utf-8'))
    result=build(league,crosses)
    args.output.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    print('Cross-fixture context',json.dumps({x:r['count'] for x,r in result['leagues'].items()},
                                           ensure_ascii=False))

if __name__=='__main__':
    main()
