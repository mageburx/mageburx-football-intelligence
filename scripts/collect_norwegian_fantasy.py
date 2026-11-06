#!/usr/bin/env python3
"""Research-only score/fixture reconciliation from a public Norwegian fan archive.

The CSV contains official Eliteserien Fantasy data; its code is MIT, but the
underlying fixtures/results are owned by the league/data providers. This
collector makes no claim of commercial rights and copies no player/stats data.
Stop on conflicts, respect a daily fetch window, preserve TheSportsDB IDs.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import io
import json
import re
import unicodedata
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
FILE=ROOT/'data'/'season.json'
SOURCE='https://raw.githubusercontent.com/TopMarx/eliteserien/main/data/2026/csv/fixtures.csv'
AGENT='MageburxFootballResearch/6.3 (public scores, non-commercial study)'
ALIASES={'hamkam':'Hamarkameratene','kfum oslo':'KFUM-Kameratene Oslo'}


def canonical(text):
    s=unicodedata.normalize('NFKD',str(text or ''))
    s=''.join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r'\s+',' ',re.sub(r'[^a-z0-9]+',' ',s.casefold())).strip()


def club(name):
    return ALIASES.get(canonical(name),str(name).strip())


def key(item):
    return (item.get('date'),canonical(club(item.get('home'))),
            canonical(club(item.get('away'))))


def numeric(value):
    if value in ('',None):return None
    try:
        n=int(value)
        return n if 0<=n<=25 else None
    except (ValueError,TypeError):return None


def download():
    req=urllib.request.Request(SOURCE,headers={'User-Agent':AGENT,'Accept':'text/csv'})
    with urllib.request.urlopen(req,timeout=20) as response:
        data=response.read(100_000)
        if response.status!=200 or len(data)>=100_000:raise ValueError('Unexpected Norwegian CSV payload')
        return data.decode('utf8-sig')


def parse(text,now):
    if now.tzinfo is None:raise ValueError('UTC aware time required')
    reader=csv.DictReader(io.StringIO(text))
    required={'fixture_id','gameweek','team_h_name','team_a_name','team_h_score',
              'team_a_score','kickoff_time','finished'}
    if not required.issubset(set(reader.fieldnames or ())):
        raise ValueError('Unrecognized fixture CSV schema')
    seen=set()
    events=[]
    for row in reader:
        stamp=str(row.get('kickoff_time') or '')
        try:
            instant=dt.datetime.fromisoformat(stamp.replace('Z','+00:00'))
            if instant.tzinfo is None or instant.year!=2026:continue
            local=instant.astimezone(ZoneInfo('Europe/Oslo')).date()
            if local.year!=2026:continue
        except (ValueError,TypeError):continue
        home,away=club(row.get('team_h_name')),club(row.get('team_a_name'))
        if not home or not away or canonical(home)==canonical(away):continue
        try:
            rnd=int(row.get('gameweek') or 0)
            if not 1<=rnd<=30:rnd=0
        except ValueError:rnd=0
        fid=str(row.get('fixture_id') or '').strip()
        if not fid.isdigit():continue
        h,a=numeric(row.get('team_h_score')),numeric(row.get('team_a_score'))
        # Prefer confirmed completed games, but exclude same-day results as a
        # conservative temporal guard, including any leaked future scores.
        finished=(str(row.get('finished'))=='True' and
                  local<now.astimezone(ZoneInfo('Europe/Oslo')).date() and
                  h is not None and a is not None)
        event={'id':'fantasy-no:2026:'+fid,
               'date':local.isoformat(),'utc':instant.isoformat(),
               'round':rnd,'home':home,'away':away,
               'finished':finished,'home_score':h if finished else None,
               'away_score':a if finished else None}
        matchkey=key(event)
        if matchkey in seen:raise ValueError('Repeated fixture in Norwegian source')
        seen.add(matchkey)
        events.append(event)
    if len(events)<100 or len(events)>300:
        raise ValueError('Unexpected Norwegian source coverage')
    teams={e['home'] for e in events}|{e['away'] for e in events}
    if len(teams)!=16:raise ValueError('Unexpected Norwegian team count')
    return events


def reconcile(season_path=FILE,fetcher=download,now=None,min_hours=22):
    now=now or dt.datetime.now(dt.timezone.utc)
    doc=json.loads(season_path.read_text(encoding='utf8'))
    league=doc.get('leagues',{}).get('no')
    if doc.get('schema')!=1 or not isinstance(league,dict) or league.get('source_season')!='2026':
        raise ValueError('Norwegian 2026 season not initialized')
    previous=league.get('fantasy_research',{}).get('checked_at')
    if previous:
        try:
            if (now-dt.datetime.fromisoformat(previous)).total_seconds()<min_hours*3600:
                return doc
        except (ValueError,TypeError):pass
    before=league.get('events',[])
    incoming=parse(fetcher(),now)
    bykey={key(e):e for e in before}
    added=confirmed=conflicts=updated=0
    for row in incoming:
        k=key(row)
        earlier=bykey.get(k)
        if earlier is not None:
            if earlier.get('finished') and row['finished']:
                if (earlier.get('home_score'),earlier.get('away_score'))!=(
                    row['home_score'],row['away_score']):
                    conflicts+=1
                    continue
                confirmed+=1
            elif row['finished'] and not earlier.get('finished'):
                earlier.update({'finished':True,'home_score':row['home_score'],
                                'away_score':row['away_score']})
                updated+=1
            continue
        before.append(row)
        bykey[k]=row
        added+=1
    before.sort(key=lambda e:(e['date'],str(e.get('utc') or ''),str(e.get('id'))))
    league['fantasy_research']={
        'source':'TopMarx/eliteserien public fixture export',
        'source_url':'https://github.com/TopMarx/eliteserien',
        'rights':'Source code MIT; underlying league/data provider rights not licensed for commercial reuse.',
        'checked_at':now.replace(microsecond=0).isoformat(),
        'source_matches':len(incoming),'added':added,'confirmed':confirmed,
        'updated_scores':updated,'conflicts':conflicts}
    league['coverage_note']='Research-only merge of public facts. Underlying official data rights require separate review.'
    # Source coverage does NOT certify the dataset / historical models.
    league['partial']=True
    doc['updated_at']=now.replace(microsecond=0).isoformat()
    season_path.write_text(json.dumps(doc,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf8')
    print('Norwegian research fixture reconciliation',
          json.dumps({'total':len(before),'played':sum(x.get('finished') is True for x in before),
                      'new':added,'updated':updated,'conflicts':conflicts},ensure_ascii=False))
    return doc


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--season',type=Path,default=FILE)
    args=p.parse_args()
    reconcile(args.season)
