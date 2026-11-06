#!/usr/bin/env python3
"""Historical Danish Pokalen (2024/25) public archive — dates for fatigue only.

The live DBU endpoint is intermittently unavailable, and the fallback
Fodboldzone website has no 2024/25 fixtures. This opt-in, robots-aware
archival source exposes 109 played cup fixtures for the 2024/25 season.

Only schedule exposure (date, sides, competition) enters research features.
A cup score may include extra time/penalties and MUST NOT enter league goal
or Elo models. Data provenance and partial-coverage flags are retained.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import re
import urllib.request
import urllib.robotparser
from html.parser import HTMLParser
from pathlib import Path

try:
    from scripts.collect_cross_competitions import canonical,normal
except ModuleNotFoundError:
    from collect_cross_competitions import canonical,normal

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/'data'/'cross_competitions.json'
SITE='https://ecst.se'
URL=SITE+'/fotboll/den/stat/C_2425.php'
AGENT='MageburxFootballIntelligence/5.4 (+https://github.com/mageburx/mageburx-football-intelligence)'
MONTHS={
    'januari':1,'februari':2,'mars':3,'april':4,'maj':5,'juni':6,
    'juli':7,'augusti':8,'september':9,'oktober':10,'november':11,'december':12,
}

class ArchiveParser(HTMLParser):
    """Semantic extraction from score-date, score-game/m1/m2/m3 divs."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.div_stack=[]
        self.capture=None
        self.text_fragments=[]
        self.date=None
        self.game=None
        self.games=[]
    def handle_starttag(self,tag,attrs):
        if tag!='div':return
        klass=set(dict(attrs).get('class','').split())
        field=next((k for k in ('score-date','m1','m2','m3') if k in klass),None)
        if 'score-game' in klass:
            self.game={'date_label':self.date}
        self.div_stack.append(klass)
        if field:
            self.capture=field
            self.text_fragments=[]
    def handle_data(self,data):
        if self.capture:
            self.text_fragments.append(data)
    def handle_endtag(self,tag):
        if tag!='div' or not self.div_stack:return
        klass=self.div_stack.pop()
        if self.capture in klass:
            t=' '.join(' '.join(self.text_fragments).split())
            if self.capture=='score-date':self.date=t
            elif self.game is not None:self.game[self.capture]=t
            self.capture=None
            self.text_fragments=[]
        if 'score-game' in klass and self.game is not None:
            self.games.append(self.game)
            self.game=None

def parse_archive(html,season='2024-2025'):
    if season!='2024-2025':raise ValueError('This archive only supports 2024/25')
    if not isinstance(html,str) or len(html)<1500 or 'score-game' not in html:
        raise ValueError('Archive HTML unavailable, do not import')
    parser=ArchiveParser()
    parser.feed(html)
    results={}
    for g in parser.games:
        date_raw=g.get('date_label') or ''
        # e.g. "Onsdag 7 maj 2025", "Tisdag 17 september 2024"
        mat=re.search(r'\b(\d{1,2})\s+([A-Za-zÅÄÖåäö]+)\s+(20\d{2})\b',date_raw)
        score=re.fullmatch(r'\s*(\d{1,2})\s*-\s*(\d{1,2})\s*',g.get('m2',''))
        if not mat or not score:continue
        month=MONTHS.get(mat.group(2).lower())
        if month is None:continue
        try:day=dt.date(int(mat.group(3)),month,int(mat.group(1)))
        except ValueError:continue
        if not dt.date(2024,7,1)<=day<dt.date(2025,7,1):continue
        h,a=canonical(g.get('m1','')),canonical(g.get('m3',''))
        if not h or not a or normal(h)==normal(a):continue
        key=(day.isoformat(),normal(h),normal(a))
        if key in results:
            if (results[key]['home_score'],results[key]['away_score'])!=tuple(map(int,score.groups())):
                raise ValueError('Conflicting duplicate results in source archive')
            continue
        ident=hashlib.sha256('|'.join(key).encode('utf8')).hexdigest()[:18]
        results[key]={
            'id':'ecst_dk_cup:'+ident,
            'date':day.isoformat(),'utc':'','home':h,'away':a,
            'competition_id':'dk_cup','competition':'DBU Pokalen',
            'competition_type':'domestic_cup',
            'home_score':int(score.group(1)),'away_score':int(score.group(2)),
            'finished':True,'league_model_eligible':False,
            'score_basis':'unknown_regulation_or_extra_time',
            'source':URL,'source_name':'ECST historical Danish cup results',
        }
    if not 90<=len(results)<=130:
        raise ValueError(f'Unexpected number of archival cup games: {len(results)}; do not import')
    return sorted(results.values(),key=lambda x:(x['date'],x['id']))

def fetch_allowed():
    rp=urllib.robotparser.RobotFileParser()
    req=urllib.request.Request(SITE+'/robots.txt',headers={'User-Agent':AGENT})
    try:
        with urllib.request.urlopen(req,timeout=14) as response:
            robots=response.read(180000).decode('utf8','replace')
        if 'user-agent:' not in robots.lower():raise ValueError('Invalid robots file')
        rp.parse(robots.splitlines())
    except (OSError,ValueError) as exc:
        raise RuntimeError('Cannot verify robots.txt; archive not fetched') from exc
    if not rp.can_fetch(AGENT,URL):
        raise PermissionError('Archive collection denied by robots.txt')
    req=urllib.request.Request(URL,headers={'User-Agent':AGENT,'Accept':'text/html'})
    with urllib.request.urlopen(req,timeout=18) as response:
        if response.status!=200:raise RuntimeError(f'Unexpected HTTP status {response.status}')
        return response.read(1800000).decode('utf8','replace')

def collect(path=PATH,fetcher=fetch_allowed,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    data=json.loads(path.read_text(encoding='utf8'))
    report=data.setdefault('danish_cup_archive',{})
    old_date=report.get('last_success_at')
    if old_date:
        try:
            if (now-dt.datetime.fromisoformat(old_date)).total_seconds()<30*86400:
                print('Historical Danish cup 2024/25 already sourced; skip',flush=True)
                return data
        except ValueError:pass
    original={e['id']:e for e in data['events']}
    existing={(e['date'],normal(canonical(e['home'])),normal(canonical(e['away']))):e
              for e in original.values() if e.get('competition_id')=='dk_cup'}
    added=verified=0
    try:
        results=parse_archive(fetcher())
        conflicts=[]
        for event in results:
            key=(event['date'],normal(canonical(event['home'])),normal(canonical(event['away'])))
            previous=existing.get(key)
            if previous:
                if (previous.get('home_score'),previous.get('away_score')) != (
                    event['home_score'],event['away_score']):
                    conflicts.append({'date':event['date'],'home':event['home'],
                                      'away':event['away'],'source':URL})
                else:
                    verified+=1
                continue
            original[event['id']]=event
            added+=1
        if conflicts:
            # Do not import this run if any score disagreements occur.
            data.setdefault('conflicts',[]).extend(conflicts[:30])
            raise ValueError(f'{len(conflicts)} official vs archival score discrepancies')
        data['events']=sorted(original.values(),key=lambda e:(e['date'],e['id']))
        report.update({'status':'historical_sample_available','source_url':URL,
                       'season':'2024-2025','parsed':len(results),
                       'added':added,'matched_existing':verified,
                       'last_success_at':now.isoformat(),
                       'license_note':'Public results and dates for research; source attribution retained. No bulk republication or bookmaker data.'})
    except (OSError,RuntimeError,ValueError,PermissionError) as exc:
        report.update({'status':'unavailable_or_conflicted',
                       'last_attempt':now.isoformat(),'reason':str(exc)[:190],
                       'source_url':URL})
        print('Historical Danish cup archive skipped:',str(exc)[:190],flush=True)
    path.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf8')
    print('Historical Danish cup archive: '+json.dumps({
        'status':report['status'],'added':added if report['status']=='historical_sample_available' else 0,
        'existing_verified':verified if report['status']=='historical_sample_available' else 0
    },ensure_ascii=False),flush=True)
    return data

if __name__=='__main__':
    collect()
