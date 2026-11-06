#!/usr/bin/env python3
"""Measure observed European fixture coverage. Never equate queried rounds with completeness."""
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
EUROPEAN=('uefa_cl','uefa_el','uefa_ecl')
SEASONS=('2024-2025','2025-2026','2026-2027')
# Search envelope only; never an official UEFA fixture count.
TRIAL_ROUNDS=tuple(range(1,11))


def season_of(date):
    d=dt.date.fromisoformat(date)
    year=d.year if d.month>=7 else d.year-1
    return f'{year}-{year+1}'


def build(cross,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    groups={}
    conflicts=[]
    by_identity={}
    for e in cross.get('events',[]):
        key=e.get('competition_id')
        if key not in EUROPEAN:continue
        try:season=season_of(e['date'])
        except (ValueError,KeyError,TypeError):
            conflicts.append({'type':'invalid_event_date','id':e.get('id')})
            continue
        if season not in SEASONS:continue
        identity=(key,season,e['date'],normal(canonical(e.get('home',''))),
                  normal(canonical(e.get('away',''))))
        if not identity[3] or not identity[4] or identity[3]==identity[4]:
            conflicts.append({'type':'invalid_teams','id':e.get('id')})
            continue
        previous=by_identity.get(identity)
        if previous:
            if previous.get('finished') and e.get('finished') and (
                previous.get('home_score'),previous.get('away_score'))!=(
                e.get('home_score'),e.get('away_score')):
                conflicts.append({'type':'conflicting_duplicate_score','id':e.get('id')})
            continue
        by_identity[identity]=e
    for season in SEASONS:
        for key in EUROPEAN:
            relevant=[e for (comp,year,*_),e in by_identity.items() if comp==key and year==season]
            meta=cross.get('competitions',{}).get(f'{key}:{season}',{})
            checked=sorted(set(meta.get('checked_rounds',[])))
            unknown=[r for r in TRIAL_ROUNDS if r not in checked]
            finished=sum(e.get('finished') is True for e in relevant)
            pending=len(relevant)-finished
            groups[f'{key}:{season}']={
                'competition':key,'season':season,
                'observed_matches':len(relevant),'observed_completed':finished,
                'observed_unfinished':pending,
                'rounds_queried_with_results':checked,
                'unqueried_rounds_in_trial_window':unknown,
                'status':'partial_not_certified',
                'note':'Counts reflect only recorded events; the 1-10 round window is a collector setting, not the full official tournament.'
            }
    return {'schema':1,'generated_at':now.replace(microsecond=0).isoformat(),
            'status':'partial_not_certified',
            'leagues':groups,'duplicate_or_invalid_event_count':len(conflicts),
            'issues':conflicts[:40],'source_conflict_count':len(cross.get('conflicts',[])),
            'warning':'UEFA qualifiers, knockouts, postponed fixtures and missing sources may not be covered. This is a lower bound, NOT a full-history certificate.'}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--cross',type=Path,default=ROOT/'data'/'cross_competitions.json')
    ap.add_argument('--output',type=Path,default=ROOT/'data'/'european_coverage.json')
    args=ap.parse_args()
    report=build(json.loads(args.cross.read_text(encoding='utf-8')))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    print('UEFA historical coverage:',json.dumps({
        k:{'matches':v['observed_matches'],'unchecked_rounds':len(v['unqueried_rounds_in_trial_window'])}
        for k,v in report['leagues'].items()},ensure_ascii=False))


if __name__=='__main__':
    main()
