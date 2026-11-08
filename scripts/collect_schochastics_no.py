#!/usr/bin/env python3
"""Schochastics historical Norway candidate archive, isolated from live fixtures.

ODC-BY licensed source. Zero changes to current season, scores, predictions or
settlements. Import only explicitly scored, 90-minute top-division matches.
A full 240-match season is accepted only after calendar/team-count audit.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import io
import json
import urllib.request
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FILE=ROOT/'data'/'schochastics_history.json'
URL='https://raw.githubusercontent.com/schochastics/football-data/master/data/results/games.parquet'
LICENSE='ODC-BY-1.0'
YEARS=(2021,2022)
MAX_BYTES=19_000_000
EXPECTED_MATCHES=240
EXPECTED_TEAMS=16

def read_parquet_bytes():
    request=urllib.request.Request(URL,headers={'User-Agent':'MageburxFootballResearch/9.0 (ODC-BY research archive)'})
    with urllib.request.urlopen(request,timeout=45) as response:
        if response.status!=200:raise RuntimeError('Unexpected football archive status')
        content=response.read(MAX_BYTES+1)
        if len(content)>MAX_BYTES:raise ValueError('Unexpected football archive size')
        return content

def prepare_rows(raw):
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError('pyarrow unavailable: cannot parse parquet; do not invent results') from exc
    cols=('home','away','date','gh','ga','full_time','competition','level')
    table=pq.read_table(io.BytesIO(raw),columns=cols)
    if table.num_rows<100_000:raise ValueError('Unexpectedly small football dataset')
    # Only project the needed columns, never persist or republish the full dataset.
    return table.select(cols).to_pylist()

def date_of(value):
    if isinstance(value,dt.datetime):return value.date()
    if isinstance(value,dt.date):return value
    try:return dt.date.fromisoformat(str(value)[:10])
    except (TypeError,ValueError):return None

def build(rows,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:raise ValueError('Timestamp needs timezone')
    out={'schema':1,'generated_at':now.astimezone(dt.timezone.utc).isoformat(),
         'source_repository':'https://github.com/schochastics/football-data',
         'source_url':URL,'license':LICENSE,
         'credit':'Thomas Schoch / schochastics football-data; Open Data Commons Attribution',
         'data_scope':'Historical research, separate from current-season and 1X2 forecast ledgers',
         'status':'audited','seasons':{}}
    matched={year:[] for year in YEARS}
    for r in rows:
        if not isinstance(r,dict):continue
        day=date_of(r.get('date'))
        if not day or day.year not in matched:continue
        # Source codebook calls national top-tier competition "Norway"; do
        # not use lower tiers, cup fixtures, international matches or playoffs.
        if str(r.get('competition') or '').strip().casefold()!='norway':continue
        if str(r.get('level') or '').strip().casefold()!='national':continue
        if str(r.get('full_time') or '').strip().upper()!='F':continue
        home,away=(str(r.get(x) or '').strip() for x in ('home','away'))
        gh,ga=r.get('gh'),r.get('ga')
        if (not home or not away or home==away or type(gh) is not int or
            type(ga) is not int or not 0<=gh<=25 or not 0<=ga<=25):
            continue
        key=f'no:{day.year}:{day}:{home.casefold()}:{away.casefold()}'
        matched[day.year].append({'id':'odc:'+hashlib.sha256(key.encode()).hexdigest()[:19],
                                 'date':day.isoformat(),'home':home,'away':away,
                                 'home_score':gh,'away_score':ga,'match_status':'FT',
                                 'result_source':'Schochastics ODC-BY historical candidate'})
    for year,events in matched.items():
        unique={(x['date'],x['home'].casefold(),x['away'].casefold()) for x in events}
        clubs=Counter()
        for e in events:clubs[e['home']]+=1;clubs[e['away']]+=1
        count_ok=len(events)==EXPECTED_MATCHES
        teams_ok=len(clubs)==EXPECTED_TEAMS and all(n==30 for n in clubs.values())
        # A format-complete archive is still only source-certified, not
        # cross-confirmed and never a signed-forecast settlement input.
        complete=count_ok and teams_ok and len(unique)==len(events)
        events.sort(key=lambda e:(e['date'],e['id']))
        out['seasons'][str(year)]={'source':'Schochastics ODC-BY results parquet',
            'source_url':URL,'license':LICENSE,
            'season':str(year),'expected_games':EXPECTED_MATCHES,
            'actual_games':len(events),'complete':complete,
            'status':'source_complete_single_source' if complete else 'source_partial_or_unverified',
            'team_count':len(clubs),'duplicate_pairs':len(events)-len(unique),
            'per_club_appearances_ok':teams_ok,
            'events':events}
    return out

def refresh(existing=None,fetcher=read_parquet_bytes,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    existing=existing or {}
    if existing.get('schema')==1 and all(
        existing.get('seasons',{}).get(str(y),{}).get('complete') is True for y in YEARS):
        return existing,{'status':'cached_complete','requests':0}
    last=existing.get('last_attempt_at')
    if last:
        try:
            when=dt.datetime.fromisoformat(last.replace('Z','+00:00'))
            if when.tzinfo and (now-when).total_seconds()<7*24*3600:
                return existing,{'status':'cached_attempt','requests':0}
        except (ValueError,TypeError):pass
    try:
        payload=fetcher()
        report=build(prepare_rows(payload),now)
        report['source_sha256']=hashlib.sha256(payload).hexdigest()
        report['last_attempt_at']=now.isoformat()
        return report,{'status':'audited','requests':1,'seasons':{
            y:{'count':x['actual_games'],'complete':x['complete']}
            for y,x in report['seasons'].items()}}
    except (ValueError,OSError,RuntimeError,TimeoutError) as exc:
        previous=json.loads(json.dumps(existing)) if existing else {'schema':1,'seasons':{}}
        previous.update({'last_attempt_at':now.isoformat(),'status':'source_unavailable',
                         'last_error':type(exc).__name__+': '+str(exc)[:160],
                         'source_url':URL,'license':LICENSE})
        return previous,{'status':'source_unavailable','requests':1,'error':type(exc).__name__}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output',type=Path,default=FILE)
    args=p.parse_args()
    previous=json.loads(args.output.read_text(encoding='utf8')) if args.output.exists() else None
    report,status=refresh(previous)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf8')
    print('Schochastics ODC-BY audit:',json.dumps(status,ensure_ascii=False),flush=True)
    print('No current fixture or signed forecast changed.',flush=True)

if __name__=='__main__':
    main()
