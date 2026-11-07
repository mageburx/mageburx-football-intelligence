#!/usr/bin/env python3
"""Licensed CC0 historical snapshots for Denmark 1. Division and Eliteserien.

Upstream is an explicit, bounded, audited allowlist of OpenFootball Europe
football.txt files. Archives are research-only; no mutation of current fixtures,
model, frozen forecasts, settlement ledger, or previous historical seasons.
Incomplete source seasons remain incomplete even if their header says 240/192.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'data'/'expanded_history.json'
BASE='https://raw.githubusercontent.com/openfootball/europe/master/'
LICENSE='CC0-1.0'
# GitHub-listed files (7 Nov 2026). Never derive paths from user input.
SOURCES={
    'dk2':{
        '2024-2025':('denmark/2024-25_dk2.txt',192,12,32),
    },
    'no':{
        '2023':('norway/2023_no1.txt',240,16,30),
        '2024':('norway/2024_no1.txt',240,16,30),
        '2025':('norway/2025_no1.txt',240,16,30),
    },
}
EXPECTED={
    'dk2':tuple(f'{y}-{y+1}' for y in range(2021,2026)),
    'no':tuple(str(y) for y in range(2021,2026)),
}
MONTHS={k:i for i,k in enumerate(
    ('Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'),1)}
DAY_RE=re.compile(r'^\s*(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+'
                  r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+'
                  r'(\d{1,2})(?:\s+(\d{4}))?\s*$')
ROUND_RE=re.compile(r'^\s*▪\s*(?:(.+?),\s*)?Matchday\s+(\d+)\s*$')
GAME_RE=re.compile(
    r'^\s*(?:(?:\d{1,2}:\d{2})\s+)?(?P<home>.+?)\s+v\s+'
    r'(?P<away>.+?)\s+(?P<hs>\d{1,2})-(?P<as>\d{1,2})'
    r'(?:\s+\((?:\d{1,2})-(?:\d{1,2})\))?\s*$'
)
HEADER_RE=re.compile(r'(?m)^#\s*Matches\s+(\d+)\s*$')

def fetch_file(path):
    allowed={x[0] for country in SOURCES.values() for x in country.values()}
    if path not in allowed:raise ValueError('Unapproved CC0 archive path')
    request=urllib.request.Request(BASE+path,headers={
        'User-Agent':'MageburxFootballResearch/8.0 (OpenFootball CC0 historical archive)',
        'Accept':'text/plain'})
    with urllib.request.urlopen(request,timeout=25) as response:
        if response.status!=200:raise RuntimeError('Unexpected historical source HTTP status')
        raw=response.read(135_000)
        if len(raw)>=135_000:raise ValueError('Unexpected CC0 text size')
        return raw.decode('utf-8-sig')

def parse_archive(raw,lid,season,fetched_at):
    if lid not in SOURCES or season not in SOURCES[lid]:
        raise ValueError('Unapproved league/season combination')
    path,reference,teams_expected,each_expected=SOURCES[lid][season]
    title=raw.lstrip('\ufeff').splitlines()[0].strip() if raw.strip() else ''
    if lid=='no':
        if title!=f'= Norway Eliteserien {season}':
            raise ValueError('Wrong Norwegian league or season title')
    elif title!=f'= Denmark 1. Division {season.replace("-", "/")}':
        raise ValueError('Wrong Danish competition or season title')
    header=HEADER_RE.search(raw)
    if not header or int(header.group(1))!=reference:
        raise ValueError('Unexpected match count in upstream season header')
    year=int(season[:4])
    current_date=None
    round_number=None
    stage='regular'
    records=[]
    ignored_scored_lines=[]
    for line in raw.splitlines()[1:]:
        m=ROUND_RE.match(line)
        if m:
            stage=(m.group(1) or 'regular').strip()
            round_number=int(m.group(2))
            continue
        m=DAY_RE.match(line)
        if m:
            month=MONTHS[m.group(1)]
            calendar_year=int(m.group(3)) if m.group(3) else (
                year + (1 if lid=='dk2' and month<7 else 0))
            try:
                current_date=dt.date(calendar_year,month,int(m.group(2)))
            except ValueError:
                current_date=None
            continue
        if ' v ' not in line:continue
        game=GAME_RE.match(line)
        if not game:
            if re.search(r'\s\d{1,2}-\d{1,2}(?:\s|$)',line):
                ignored_scored_lines.append(line.strip()[:115])
            continue
        if current_date is None or round_number is None:
            raise ValueError('Scored fixture without proven date and round')
        home=game.group('home').strip()
        away=game.group('away').strip()
        hs,ags=int(game.group('hs')),int(game.group('as'))
        if (not home or not away or home==away or not 0<=hs<=25 or not 0<=ags<=25):
            raise ValueError('Invalid fixture score or teams')
        if lid=='no':
            if current_date.year!=year:raise ValueError('Out-of-season Norwegian date')
        elif not dt.date(year,7,1)<=current_date<=dt.date(year+1,6,30):
            raise ValueError('Out-of-season Danish date')
        key=f'{lid}:{season}:{current_date.isoformat()}:{home}:{away}'
        records.append({'id':'cc0:'+hashlib.sha256(key.encode('utf-8')).hexdigest()[:18],
                        'date':current_date.isoformat(),'round':round_number,
                        'stage':stage,'home':home,'away':away,'home_score':hs,
                        'away_score':ags,'finished':True,
                        'result_verified':True,'match_status':'FT',
                        'result_source':'OpenFootball Europe CC0 fixture text'})
    if ignored_scored_lines:
        # Fail closed: a changed source layout cannot silently look complete.
        raise ValueError(f'Unparsed scored lines: {len(ignored_scored_lines)}')
    if not records:raise ValueError('No completed results in upstream CC0 archive')
    unique={(e['date'],e['home'].casefold(),e['away'].casefold()) for e in records}
    if len(unique)!=len(records):raise ValueError('Duplicate dated fixture in archive')
    clubs=Counter()
    for e in records:
        clubs[e['home']]+=1;clubs[e['away']]+=1
    if len(records)>reference:raise ValueError('More results than official format reference')
    if len(clubs)>teams_expected:raise ValueError('Unexpected number of clubs')
    # Reaching the count alone is not enough for a season to be complete.
    complete=(len(records)==reference and len(clubs)==teams_expected and
              all(v==each_expected for v in clubs.values()))
    if len(records)==reference and not complete:
        raise ValueError('Source count reached but team/appearance audit failed')
    records.sort(key=lambda e:(e['date'],e['id']))
    return {'schema':1,'season':season,'source':'OpenFootball Europe football.txt',
            'source_url':BASE+path,'license':LICENSE,
            'fetched_at':fetched_at,'source_sha256':hashlib.sha256(raw.encode('utf-8')).hexdigest(),
            'expected_games':reference,'actual_games':len(records),
            'expected_teams':teams_expected,'actual_teams':len(clubs),
            'complete':complete,
            'status':'source_complete' if complete else 'source_partial',
            'events':records}

def refresh(previous=None,reader=fetch_file,now=None,force=False):
    now=now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:raise ValueError('Timezone-aware UTC timestamp required')
    previous=previous or {'schema':1,'leagues':{}}
    if previous.get('schema')!=1:raise ValueError('Invalid expanded-history schema')
    out=json.loads(json.dumps(previous))  # deep copy and retain prior successful imports
    out.setdefault('leagues',{})
    out['schema']=1
    out['license']=LICENSE
    out['source_repository']='https://github.com/openfootball/europe'
    out['updated_at']=now.replace(microsecond=0).isoformat()
    summary={}
    for lid,seasons in SOURCES.items():
        store=out['leagues'].setdefault(lid,{'seasons':{}})
        available=store.setdefault('seasons',{})
        summary[lid]={'downloaded':0,'cached':0,'errors':0,'complete':0}
        for season,(path,reference,_,_) in seasons.items():
            old=available.get(season)
            if isinstance(old,dict) and old.get('complete') and not force:
                summary[lid]['cached']+=1
                continue
            last=old.get('last_attempt_at') if isinstance(old,dict) else None
            if last and not force:
                try:
                    checked=dt.datetime.fromisoformat(last)
                    if checked.tzinfo and (now-checked).total_seconds()<7*24*3600:
                        summary[lid]['cached']+=1
                        continue
                except (ValueError,TypeError):pass
            fetched_at=now.replace(microsecond=0).isoformat()
            try:
                item=parse_archive(reader(path),lid,season,fetched_at)
                item['last_attempt_at']=fetched_at
                available[season]=item
                summary[lid]['downloaded']+=1
            except (OSError,RuntimeError,ValueError,UnicodeError,TimeoutError,
                    urllib.error.URLError) as exc:
                summary[lid]['errors']+=1
                if old and isinstance(old,dict):
                    old['last_attempt_at']=fetched_at
                    old['last_error']=str(exc)[:170]
                else:
                    available[season]={'schema':1,'season':season,'status':'unavailable',
                                       'source_url':BASE+path,'license':LICENSE,
                                       'events':[],'expected_games':reference,
                                       'actual_games':0,'complete':False,
                                       'last_attempt_at':fetched_at,
                                       'last_error':str(exc)[:170]}
        summary[lid]['complete']=sum(x.get('complete') is True for x in available.values()
                                      if isinstance(x,dict))
    return out,summary

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output',type=Path,default=OUTPUT)
    args=p.parse_args()
    previous=json.loads(args.output.read_text(encoding='utf-8')) if args.output.exists() else None
    result,summary=refresh(previous)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n',
                           encoding='utf-8')
    print('CC0 Expanded History:',json.dumps(summary,ensure_ascii=False),flush=True)
    print('Historical archive is isolated from current-season model and signed ledger.',flush=True)

if __name__=='__main__':
    main()
