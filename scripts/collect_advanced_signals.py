#!/usr/bin/env python3
"""Bounded opt-in research observations, NOT an xG or betting prediction model.

Records only a small set of match statistics with source attribution. Does not
rehost the original feed. Source compilation: Cornerflick CC BY 4.0; underlying
provider terms may restrict commercial bulk redistribution. No model changes.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'data'/'advanced_signals.json'
SOURCE='https://cornerflick.com'
FEEDS={
    'pt':'/football/leagues/primeira-liga/results/season.json',
    'dk':'/football/leagues/danish-superliga/results/season.json',
}
AGENT='MageburxFootballResearch/1.0 (+https://github.com/mageburx/mageburx-football-intelligence)'
FIELDS={'shots':('Shots','Total Shots'),
        'shots_on_target':('Shots on Target','Shots On Goal'),
        'xg':('Expected Goals','Expected Goals (xG)','xG')}
MIN_INTERVAL_HOURS=22
MAX_PER_LEAGUE=3


def fetch_json(url):
    parsed=urllib.parse.urlparse(url)
    if parsed.scheme!='https' or parsed.netloc!='cornerflick.com' or not parsed.path.startswith('/football/'):
        raise ValueError('Untrusted stats source URL')
    req=urllib.request.Request(url,headers={'User-Agent':AGENT,'Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=16) as resp:
        if resp.status!=200:raise RuntimeError(f'HTTP {resp.status}')
        if int(resp.headers.get('Content-Length') or 0)>2_000_000:raise ValueError('Dataset exceeds limit')
        return json.loads(resp.read(2_000_001))


def robots_allowed(url):
    req=urllib.request.Request(SOURCE+'/robots.txt',headers={'User-Agent':AGENT})
    with urllib.request.urlopen(req,timeout=10) as resp:
        content=resp.read(100_000).decode('utf-8','replace')
    if 'user-agent:' not in content.lower():
        raise RuntimeError('Could not confirm robots policy')
    robot=urllib.robotparser.RobotFileParser()
    robot.parse(content.splitlines())
    return robot.can_fetch(AGENT,url)


def numeric(value,maximum):
    if type(value) not in (int,float) or not math.isfinite(value):return None
    if not 0<=value<=maximum:return None
    return float(value)


def pair(stats,labels,maxval):
    found={str(v.get('label','')).casefold():v for v in stats if isinstance(v,dict)}
    for label in labels:
        value=found.get(label.casefold())
        if not isinstance(value,dict):continue
        a,b=numeric(value.get('home'),maxval),numeric(value.get('away'),maxval)
        if a is not None and b is not None:return [a,b]
    return None


def extract_match(match,raw,league,now):
    meta=raw.get('meta') or {}
    if meta.get('license')!='CC BY 4.0':raise ValueError('Per-match license not verified')
    stats=raw.get('statistics') or []
    if not isinstance(stats,list):raise ValueError('Invalid statistics structure')
    shots=pair(stats,FIELDS['shots'],100)
    sot=pair(stats,FIELDS['shots_on_target'],100)
    xg=pair(stats,FIELDS['xg'],15)
    if shots and sot and any(a>b for a,b in zip(sot,shots)):
        raise ValueError('Shots-on-target exceeds shots')
    if not (shots or sot or xg):return None
    kickoff=dt.datetime.fromisoformat(match['kickoff_at'].replace('Z','+00:00'))
    if kickoff.tzinfo is None or kickoff>=now:
        raise ValueError('Not a documented completed match')
    if match.get('status')!='finished':raise ValueError('Match not finished')
    return {
        'source_id':match['id'],'date':kickoff.date().isoformat(),'league':league,
        'home':match['home_team'],'away':match['away_team'],
        'shots':shots,'shots_on_target':sot,'xg':xg,
        'first_observed_at':now.replace(microsecond=0).isoformat(),
        'source_url':match['dataset_url'],
    }


def new_report():
    return {'schema':1,'source':{'name':'Cornerflick',
              'url':'https://cornerflick.com/data',
              'attribution':'Data by Cornerflick — cornerflick.com',
              'license':'CC BY 4.0 (published compilation)',
              'rights_note':'Third-party underlying facts may require permission for commercial bulk reuse.'},
            'updated_at':None,'leagues':{lid:{'records':[],'last_attempt_at':None,
                                            'status':'not_checked','available_matches':None,
                                            'added_last_run':0,'error':None} for lid in FEEDS},
            'policy':'Small research observations only. No wagering automation, commercial bulk distribution or live model effect.'}


def collect(path=OUTPUT,now=None,max_per_league=MAX_PER_LEAGUE,
            fetcher=fetch_json,allow=robots_allowed,sleep=time.sleep):
    now=now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:raise ValueError('UTC-aware datetime required')
    report=json.loads(path.read_text(encoding='utf8')) if path.exists() else new_report()
    for league,feed in FEEDS.items():
        group=report.setdefault('leagues',{}).setdefault(league,{'records':[]})
        group.setdefault('records',[])
        previous=group.get('last_attempt_at')
        if previous:
            try:
                elapsed=now-dt.datetime.fromisoformat(previous)
                if elapsed.total_seconds()<MIN_INTERVAL_HOURS*3600:
                    group['added_last_run']=0
                    continue
            except (ValueError,TypeError):
                pass
        group['last_attempt_at']=now.replace(microsecond=0).isoformat()
        group['added_last_run']=0
        group['error']=None
        try:
            listing_url=SOURCE+feed
            if not allow(listing_url):raise PermissionError('robots.txt denies season index')
            season=fetcher(listing_url)
            if (season.get('meta') or {}).get('license')!='CC BY 4.0':
                raise ValueError('Source license changed')
            matches=season.get('matches',[])
            if not isinstance(matches,list):raise ValueError('Invalid season data')
            group['available_matches']=len(matches)
            known={r['source_id'] for r in group['records']}
            candidates=sorted(
                (m for m in matches if isinstance(m,dict) and m.get('status')=='finished' and
                 m.get('id') and m.get('id') not in known),
                key=lambda x:x.get('kickoff_at',''),reverse=True)
            for match in candidates[:max(0,min(max_per_league,MAX_PER_LEAGUE))]:
                url=match.get('dataset_url','')
                target=urllib.parse.urlparse(url)
                if (target.scheme!='https' or target.netloc!='cornerflick.com' or
                    not target.path.startswith('/football/') or not target.path.endswith('/data.json')):
                    raise ValueError('Untrusted match dataset location')
                if not allow(url):raise PermissionError('robots.txt denies match dataset')
                sleep(1.5)
                raw=fetcher(url)
                row=extract_match(match,raw,league,now)
                if row is None:continue
                group['records'].append(row)
                known.add(row['source_id'])
                group['added_last_run']+=1
            group['status']='limited_sample' if group['records'] else 'no_valid_statistics'
        except (OSError,ValueError,TypeError,KeyError,RuntimeError,PermissionError,
                json.JSONDecodeError) as exc:
            group['status']='source_unavailable'
            group['error']=str(exc)[:180]
        group['records'].sort(key=lambda x:(x['date'],x['source_id']))
    report['updated_at']=now.replace(microsecond=0).isoformat()
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,ensure_ascii=False,separators=(',',':'))+'\n',
                    encoding='utf8')
    print('Advanced shots research:',
          json.dumps({k:{'observed':len(v['records']),'added':v['added_last_run'],
                         'status':v['status']} for k,v in report['leagues'].items()},
                     ensure_ascii=False),flush=True)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--output',type=Path,default=OUTPUT)
    p.add_argument('--max-per-league',type=int,default=MAX_PER_LEAGUE)
    args=p.parse_args()
    collect(args.output,max_per_league=args.max_per_league)
