#!/usr/bin/env python3
"""Deterministic, evidence-based QA for five seasons per league.

A season is complete only when the declared source count is present and
integrity checks pass. This report does not rewrite match results or invent
missing fixtures. Strict mode blocks publication if allegedly complete input
fails checks, while honest partial seasons remain allowed and prominently shown.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
YEARS = tuple(f'{y}-{y+1}' for y in range(2021, 2026))
EXPECTED = {'pt':306,'dk':192}

def audit_season(lid, year, raw):
    events=raw.get('events', [])
    diagnostics=[]
    missing=[]
    id_counts=Counter()
    fixtures=Counter()
    team_day=defaultdict(list)
    team_matches=Counter()
    scores=Counter()
    begin=dt.date(int(year[:4]),7,1)
    end=dt.date(int(year[:4])+1,7,1)
    for i,e in enumerate(events):
        if not isinstance(e,dict):
            diagnostics.append(f'Event {i}: invalid record')
            continue
        eid=str(e.get('id') or '')
        home=str(e.get('home') or '').strip()
        away=str(e.get('away') or '').strip()
        if not eid or not home or not away or home==away:
            diagnostics.append(f'Event {i}: invalid id or team')
            continue
        id_counts[eid]+=1
        try:
            date=dt.date.fromisoformat(str(e.get('date')))
            if not (begin<=date<end):
                diagnostics.append(f'Event {eid}: date outside season')
                continue
        except ValueError:
            diagnostics.append(f'Event {eid}: invalid ISO date')
            continue
        hs=e.get('home_score');aus=e.get('away_score')
        if not isinstance(hs,int) or isinstance(hs,bool) or not isinstance(aus,int) or isinstance(aus,bool) or not (0<=hs<=30 and 0<=aus<=30):
            diagnostics.append(f'Event {eid}: invalid final score')
            continue
        if e.get('finished') is not True:
            diagnostics.append(f'Event {eid}: no verified finished flag')
            continue
        fixtures[(date.isoformat(),home,away)]+=1
        team_day[(date.isoformat(),home)].append(eid)
        team_day[(date.isoformat(),away)].append(eid)
        team_matches[home]+=1
        team_matches[away]+=1
        scores[(home,away)]+=1
    duplicate_ids=[id for id,n in id_counts.items() if n>1]
    duplicate_fixtures=[k for k,n in fixtures.items() if n>1]
    double_booked=[f'{day}:{team}' for (day,team),ids in team_day.items() if len(set(ids))>1]
    if duplicate_ids:diagnostics.append(f'{len(duplicate_ids)} duplicated match IDs')
    if duplicate_fixtures:diagnostics.append(f'{len(duplicate_fixtures)} duplicate dated fixtures')
    if double_booked:diagnostics.append(f'{len(double_booked)} teams playing twice on same day')
    declared_expected=int(raw.get('expected_games') or EXPECTED[lid])
    floor=EXPECTED[lid]
    expected=max(declared_expected,floor)
    # A known additional European playoff can make Danish totals 193 rather
    # than 192; keep expected from the provider instead of fabricating it.
    valid=len(events)-sum(1 for x in diagnostics if x.startswith('Event '))
    complete=(len(events)>=expected and not diagnostics and len(fixtures)==len(events)
              and (lid!='pt' or
                   (len(team_matches)==18 and all(n==34 for n in team_matches.values()))))
    if not complete:
        if len(events)<expected:
            missing.append(f'{expected-len(events)} results still absent (according to expected count)')
        if lid=='pt' and len(team_matches)!=18:
            missing.append('unexpected number of distinct teams')
        if lid=='pt' and any(n!=34 for n in team_matches.values()):
            missing.append('team schedule does not have 34 matches per club')
    prior_complete=raw.get('complete') is True
    return {'season':year,'matches':len(events),'expected':expected,
            'valid_matches':valid,'team_count':len(team_matches),
            'complete':complete,'previously_marked_complete':prior_complete,
            'integrity_ok':not diagnostics,'diagnostics':diagnostics[:30],
            'coverage':round(min(1,len(events)/expected),4),
            'notes':missing,'source':raw.get('verified_from','unspecified')}

def audit(data):
    result={'schema':1,'generated_at':dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
            'leagues':{},'all_complete':True,'critical_errors':[]}
    for lid in ('pt','dk'):
        seasons=data.get('leagues',{}).get(lid,{}).get('seasons',{})
        entries={}
        for year in YEARS:
            raw=seasons.get(year,{'events':[],'expected_games':EXPECTED[lid],'complete':False})
            entry=audit_season(lid,year,raw)
            entries[year]=entry
            if not entry['complete']:result['all_complete']=False
            if raw.get('complete') and not entry['complete'] and entry['integrity_ok'] is False:
                result['critical_errors'].append(f'{lid} {year}: advertised complete but integrity failed')
        result['leagues'][lid]={'seasons':entries,
                               'complete_count':sum(1 for v in entries.values() if v['complete']),
                               'total_matches':sum(v['matches'] for v in entries.values())}
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--input',type=Path,default=ROOT/'data'/'history.json')
    p.add_argument('--output',type=Path,default=ROOT/'data'/'quality.json')
    p.add_argument('--strict',action='store_true')
    args=p.parse_args()
    result=audit(json.loads(args.input.read_text(encoding='utf-8')))
    args.output.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    print(json.dumps({lid:{'complete':v['complete_count'],
                           'total_matches':v['total_matches']} for lid,v in result['leagues'].items()}))
    if args.strict and result['critical_errors']:
        raise RuntimeError('Historical integrity failed: '+str(result['critical_errors']))
    return result

if __name__=='__main__':
    main()
