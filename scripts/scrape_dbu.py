#!/usr/bin/env python3
"""Optional, robots-aware HTML collector for public DBU Superliga historical fixtures.

Only collect public competition-fixture tables. No account, browser automation,
cookies, CAPTCHA bypass, or redistributing third-party page contents.
DBU may return a temporary error page; never treat it as an empty season.

New match results are reconciled against TheSportsDB/OpenFootball by
(date, canonical home, canonical away); conflicting scores are quarantined.
"""
from __future__ import annotations
import argparse
import datetime as dt
from html.parser import HTMLParser
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

try:
    from scripts.reconcile_danish_history import canonical
except ModuleNotFoundError:
    from reconcile_danish_history import canonical

ROOT=Path(__file__).resolve().parents[1]
HISTORY=ROOT/'data'/'history.json'
REPORT=ROOT/'data'/'scrape_report.json'
AGENT='MageburxFootballResearch/1.0 (+https://github.com/mageburx/mageburx-football-intelligence)'
ROOT_URL='https://www.dbu.dk'
POOLS={
    '2021-2022': [('regular',359736),('championship',380908),('relegation',380909)],
    '2022-2023': [('regular',387486),('championship',409107),('relegation',409108)],
    '2025-2026': [('regular',473806),('championship',498492),('relegation',498493)],
}
ALIASES={
    'F.C. København':'FC København', 'F.C København':'FC København',
    'FC København':'FC København', 'OB':'Odense BK', 'AaB':'Aalborg BK',
    'AGF':'Aarhus GF', 'Sønderjyske Fodbold':'SønderjyskE',
    'FC Fredericia':'FC Fredericia', 'Vejle Boldklub':'Vejle BK',
    'Viborg':'Viborg FF',
}

class TableRows(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows=[]
        self.current=None
        self.cell=None
        self.ignore=0
    def handle_starttag(self,tag,attrs):
        if tag=='tr':
            self.current=[]
        elif tag in ('td','th') and self.current is not None:
            self.cell=[]
        elif tag in ('script','style'):
            self.ignore+=1
        elif tag=='img' and self.cell is not None:
            alt=dict(attrs).get('alt','').strip()
            if alt and alt.lower() not in ('logo','', 'hold'):self.cell.append(alt)
    def handle_endtag(self,tag):
        if tag in ('script','style'):
            self.ignore=max(0,self.ignore-1)
        elif tag in ('td','th') and self.cell is not None and self.current is not None:
            self.current.append(re.sub(r'\s+',' ',' '.join(self.cell)).strip())
            self.cell=None
        elif tag=='tr' and self.current is not None:
            if self.current:self.rows.append(self.current)
            self.current=None
    def handle_data(self,data):
        if self.cell is not None and not self.ignore:
            text=data.strip()
            if text:self.cell.append(text)

def normal_team(text):
    text=re.sub(r'\s+',' ',text).strip()
    for prefix in ('Image ',):
        if text.startswith(prefix):text=text[len(prefix):]
    if text in ALIASES:return ALIASES[text]
    return canonical(text)

def parse_page(html,season,stage,pool,url):
    if 'Midlertidigt utilgængelig' in html or 'Der er ekstraordinært travlt' in html:
        raise ValueError('DBU temporarily unavailable')
    if 'Kampnr' not in html and 'Kampprogram' not in html:
        raise ValueError('Unrecognized DBU page structure')
    p=TableRows()
    p.feed(html)
    output=[]
    for row in p.rows:
        joined=' '.join(row)
        if not re.search(r'\b\d{6,8}\b',joined):continue
        match_id=next((x for x in row if re.fullmatch(r'\d{6,8}',x)),None)
        if not match_id:continue
        date_i=next((i for i,x in enumerate(row) if re.search(r'\b(\d{2})-(\d{2})\s+(\d{4})\b',x)),None)
        if date_i is None:continue
        date_str=row[date_i]
        dm=re.search(r'\b(\d{2})-(\d{2})\s+(\d{4})\b',date_str)
        year,month,day=int(dm.group(3)),int(dm.group(2)),int(dm.group(1))
        try:
            date=dt.date(year,month,day).isoformat()
        except ValueError:
            continue
        if not (int(season[:4])<=year<=int(season[:4])+1):continue
        # Official DBU table: match no., date, time, home, away, venue,
        # broadcaster, final score. Some tables have an initial blank cell.
        # Require a plausible time cell to avoid confusing a summary table.
        home_i=date_i+2
        away_i=date_i+3
        if len(row)<=away_i:continue
        home,away=normal_team(row[home_i]),normal_team(row[away_i])
        score_matches=[re.fullmatch(r'(\d{1,2})\s*-\s*(\d{1,2})',c) for c in row]
        scores=[m for m in score_matches if m is not None]
        if not scores:continue
        hs,ags=map(int,scores[-1].groups())
        if home==away or not home or not away or hs>30 or ags>30:continue
        output.append({'id':f'dbu:{match_id}','date':date,'home':home,'away':away,
                       'home_score':hs,'away_score':ags,'finished':True,
                       'stage':stage,'source_url':url,'verified_from':'DBU official fixtures',
                       'dbu_pool':pool,'dbu_match_id':match_id})
    if not output:
        raise ValueError('No completed matches parsed; source layout may have changed')
    unique={e['id']:e for e in output}
    if len(unique)!=len(output):
        raise ValueError('Duplicate official match ID on page')
    return list(unique.values())

def fetch_allowed(url,reader=None):
    """Fail closed when robots cannot be checked, or source blocks automation."""
    from urllib.robotparser import RobotFileParser
    robots_url=ROOT_URL+'/robots.txt'
    if reader is None:
        def reader(u):
            with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':AGENT}),timeout=18) as r:
                if r.status!=200:raise RuntimeError('Non-200 response')
                return r.read(2_000_000).decode('utf-8','replace')
    rp=RobotFileParser()
    try:
        robots=reader(robots_url)
        if 'User-agent:' not in robots and 'user-agent:' not in robots.lower():
            raise RuntimeError('Invalid robots.txt')
        rp.parse(robots.splitlines())
    except Exception as exc:
        raise RuntimeError('Cannot verify DBU robots; no scraping performed') from exc
    if not rp.can_fetch(AGENT,url):
        raise PermissionError('DBU robots.txt prohibits this route')
    return reader(url)

def merge_matches(history,season,results):
    stored=history['leagues']['dk']['seasons'].setdefault(season,{
        'events':[],'expected_games':193,'complete':False,'actual_games':0,
        'verified_from':'Official Danish DBU fixtures'})
    existing=stored['events']
    by_key={(e['date'],normal_team(e['home']),normal_team(e['away'])):e for e in existing
            if e.get('stage')!='european_playoff'}
    imported,confirmed=0,0
    conflicts=[]
    for event in results:
        key=(event['date'],event['home'],event['away'])
        seen=by_key.get(key)
        if seen:
            if (seen['home_score'],seen['away_score'])!=(event['home_score'],event['away_score']):
                conflicts.append({'date':event['date'],'home':event['home'],'away':event['away'],
                                  'existing':[seen['home_score'],seen['away_score']],
                                  'official':[event['home_score'],event['away_score']],
                                  'source_url':event['source_url']})
                continue
            sources=seen.setdefault('verified_sources',[])
            if event['source_url'] not in sources:sources.append(event['source_url'])
            confirmed+=1
            continue
        # Never use DBU's score for European playoff without manual regulation-time check.
        existing.append(event)
        by_key[key]=event
        imported+=1
    existing.sort(key=lambda e:(e['date'],str(e.get('id',''))))
    stored['actual_games']=len(existing)
    # Only a separate audit + full 193-game count may mark the season complete.
    stored['complete']=bool(len(existing)==193 and not conflicts)
    return {'new':imported,'confirmed':confirmed,'conflicts':conflicts,'total':len(existing)}

def collect(path=HISTORY,report_path=REPORT,max_pages=2,pause=7.0,
            getter=fetch_allowed,now=None):
    history=json.loads(path.read_text(encoding='utf-8'))
    now=now or dt.datetime.now(dt.timezone.utc)
    log={'schema':1,'generated_at':now.isoformat(),'source':'DBU Denmark',
         'attempts':[],'conflicts':[],'imported':0,'confirmed':0,'status':'no_sources'}
    plans=[]
    # Prioritize near-complete seasons and uncollected stages across each run.
    for season,stages in POOLS.items():
        if history['leagues']['dk']['seasons'].get(season,{}).get('complete'):continue
        for stage,pool in stages:
            plans.append((season,stage,pool))
    # Rotate attempts deterministically by UTC date to avoid requesting
    # the same unresponsive page forever, without persisting request state.
    if plans:
        offset=now.timetuple().tm_yday % len(plans)
        plans=plans[offset:]+plans[:offset]
    for k,(season,stage,pool) in enumerate(plans[:max_pages]):
        url=f'{ROOT_URL}/resultater/pulje/{pool}/kampprogramFuld'
        try:
            html=getter(url)
            results=parse_page(html,season,stage,pool,url)
            outcome=merge_matches(history,season,results)
            log['imported']+=outcome['new'];log['confirmed']+=outcome['confirmed']
            log['conflicts'].extend(outcome['conflicts'])
            log['attempts'].append({'season':season,'stage':stage,'url':url,
                'parsed':len(results),'status':'ok',**{a:outcome[a] for a in ('new','confirmed')}})
        except (ValueError,RuntimeError,PermissionError,urllib.error.URLError,TimeoutError) as exc:
            log['attempts'].append({'season':season,'stage':stage,'url':url,
                                    'status':'skipped','reason':str(exc)[:160]})
            if 'robots' in str(exc).lower():break
        if pause and k+1<min(max_pages,len(plans)):time.sleep(pause)
    log['status']='conflicts' if log['conflicts'] else 'updated' if log['imported'] else 'checked'
    report_path.parent.mkdir(parents=True,exist_ok=True)
    report_path.write_text(json.dumps(log,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    if log['imported'] or log['confirmed']:
        path.write_text(json.dumps(history,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    print(json.dumps({k:log[k] for k in ('status','imported','confirmed','conflicts','attempts')},ensure_ascii=False),flush=True)
    return log

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--max-pages',type=int,default=2)
    p.add_argument('--pause',type=float,default=7.0)
    args=p.parse_args()
    collect(max_pages=min(4,max(0,args.max_pages)),pause=max(3,args.pause))
