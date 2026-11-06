#!/usr/bin/env python3
"""Robots-aware Danish Pokalen fallback; only played-match dates and opponents.

Preferred official DBU remains in collect_danish_cup.py. Fodboldzone is a
secondary, clearly attributed source when DBU returns temporary errors.
Do not use these knockout scores for 90-minute football goal models; scores
can include extra time. The only feature used is the observed match date.

Source permits robots.txt crawling on this route as checked on 2026-11-06.
On later changes to robots or source format, fail closed and keep prior records.
"""
from __future__ import annotations
import datetime as dt
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
BASE='https://fodboldzone.dk'
USER_AGENT='MageburxFootballIntelligence/5.3 (+https://github.com/mageburx/mageburx-football-intelligence)'
SEASONS=(2026,2025,2024)
MONTHS={'jan':1,'feb':2,'mar':3,'apr':4,'maj':5,'jun':6,'jul':7,
        'aug':8,'sep':9,'okt':10,'nov':11,'dec':12}

class FinishedCards(HTMLParser):
    """Read only scored cards INSIDE the <section id="resultater">."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.seen_results=False
        self.section_depth=0
        self.card=None
        self.field=None
        self.text=[]
        self.cards=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='section':
            if attrs.get('id')=='resultater':
                self.seen_results=True
                self.section_depth=1
            elif self.seen_results and self.section_depth:
                self.section_depth+=1
        if not self.seen_results:return
        klass=attrs.get('class','')
        if tag=='a' and 'fdh-match-card' in klass.split():
            link=attrs.get('href','')
            match=re.search(r'/kamp/(\d+)/?',link)
            self.card={'id':match.group(1),'date':None,'teams':[],'score':None} if match else None
        if tag=='span' and self.card is not None:
            if 'fdh-match-card__date' in klass.split():self.field='date'
            elif 'fdh-match-card__team' in klass.split():self.field='team'
            elif 'fdh-match-card__score' in klass.split():self.field='score'
            if self.field:self.text=[]
    def handle_data(self,data):
        if self.field:self.text.append(data)
    def handle_endtag(self,tag):
        if tag=='span' and self.card is not None and self.field:
            value=' '.join(' '.join(self.text).split()).strip()
            if self.field=='team':self.card['teams'].append(value)
            else:self.card[self.field]=value
            self.field=None;self.text=[]
        if tag=='a' and self.card is not None:
            self.cards.append(self.card)
            self.card=None
        if tag=='section' and self.seen_results:
            self.section_depth-=1
            if self.section_depth<=0:self.seen_results=False

def parse_fixture_page(html,season):
    if not isinstance(html,str) or len(html)<200:return []
    p=FinishedCards()
    p.feed(html)
    if not p.cards:
        raise ValueError('No scored result cards; source layout unavailable')
    results=[]
    for card in p.cards:
        value=card.get('date') or ''
        match=re.search(r'\b(\d{1,2})\.\s*([A-Za-zÆØÅæøå]+)\s+(\d{2}):(\d{2})',value)
        score=re.fullmatch(r'\s*(\d{1,2})\s*-\s*(\d{1,2})\s*',card.get('score') or '')
        if not match or not score or len(card['teams'])!=2:continue
        month=MONTHS.get(match.group(2).lower().strip('.')[:3])
        if not month:continue
        year=season if month>=7 else season+1
        try:date=dt.date(year,month,int(match.group(1))).isoformat()
        except ValueError:continue
        home,away=(canonical(n) for n in card['teams'])
        if not home or not away or normal(home)==normal(away):continue
        results.append({
            'id':f'fodboldzone:{card["id"]}','date':date,
            'home':home,'away':away,
            'competition_id':'dk_cup','competition':'DBU Pokalen',
            'competition_type':'domestic_cup',
            'home_score':int(score.group(1)),'away_score':int(score.group(2)),
            'finished':True,
            'league_model_eligible':False,
            'score_basis':'unknown_regulation_extra_time_or_penalties',
            'source':f'{BASE}/kamp/{card["id"]}/',
            'source_name':'Fodboldzone — Danish Pokalen public fixture page'
        })
    if not results:raise ValueError('No validated scored fixtures found')
    if len(set(e['id'] for e in results))!=len(results):
        raise ValueError('Duplicate match IDs in Danish Cup page')
    return results

def fetch_allowed(url):
    if not url.startswith(BASE+'/turnering/dbu-pokalen/kampe/?season='):
        raise ValueError('Unexpected Danish Cup source path')
    rp=urllib.robotparser.RobotFileParser()
    roboreq=urllib.request.Request(BASE+'/robots.txt',headers={'User-Agent':USER_AGENT})
    try:
        with urllib.request.urlopen(roboreq,timeout=15) as response:
            robots=response.read(200000).decode('utf8','replace')
        if 'user-agent:' not in robots.lower():raise ValueError('Invalid robots.txt')
        rp.parse(robots.splitlines())
    except (OSError,ValueError) as exc:
        raise RuntimeError('Cannot validate robots.txt; collection blocked') from exc
    if not rp.can_fetch(USER_AGENT,url):
        raise PermissionError('robots.txt does not allow this route')
    req=urllib.request.Request(url,headers={'User-Agent':USER_AGENT,'Accept':'text/html'})
    with urllib.request.urlopen(req,timeout=18) as response:
        if response.status!=200:raise RuntimeError('Source HTTP status '+str(response.status))
        return response.read(2000000).decode('utf8','replace')

def collect(path=PATH,fetcher=fetch_allowed,now=None,max_seasons=2):
    now=now or dt.datetime.now(dt.timezone.utc)
    data=json.loads(path.read_text(encoding='utf8'))
    indexed={x['id']:x for x in data.get('events',[]) if x.get('id')}
    report=data.setdefault('danish_cup_fallback',{})
    successful=0
    added=0
    for season in SEASONS:
        if successful>=max_seasons:break
        previous=report.get(str(season),{})
        last=previous.get('checked_at')
        if last:
            try:
                age=(now-dt.datetime.fromisoformat(last)).total_seconds()
                # A successful historical scrape is immutable; refresh
                # current season no more than once a day, older once a month.
                limit=86400 if season==now.year else 30*86400
                if previous.get('status')=='partial_available' and 0<=age<limit:continue
                if previous.get('status')!='partial_available' and 0<=age<6*3600:continue
            except (ValueError,TypeError):pass
        url=f'{BASE}/turnering/dbu-pokalen/kampe/?season={season}'
        try:
            records=parse_fixture_page(fetcher(url),season)
            k=0
            for match in records:
                if match['date']>=now.date().isoformat():continue
                before=indexed.get(match['id'])
                if before:
                    if ((before['date'],normal(before['home']),normal(before['away']))!=
                        (match['date'],normal(match['home']),normal(match['away'])) or
                        (before['home_score'],before['away_score'])!=(match['home_score'],match['away_score'])):
                        data.setdefault('conflicts',[]).append({
                            'id':match['id'],'reason':'Alternative Danish cup source disagreement',
                            'source':match['source']})
                    continue
                indexed[match['id']]=match;k+=1;added+=1
            report[str(season)]={'status':'partial_available',
                                 'checked_at':now.isoformat(),
                                 'source_url':url,'scored_cards':len(records),
                                 'new':k,'license_note':'Public dates and results; attribution required; not evidence of 90-minute goals.'}
            successful+=1
        except (OSError,RuntimeError,PermissionError,ValueError) as exc:
            report[str(season)]={'status':'source_unavailable_or_not_allowed',
                                 'checked_at':now.isoformat(),'source_url':url,
                                 'reason':str(exc)[:160]}
            if 'robots.txt' in str(exc):break
    data['events']=sorted(indexed.values(),key=lambda e:(e['date'],e['id']))
    data['coverage']='partial'
    path.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf8')
    print('Danish Cup alternative:',json.dumps({'new':added,'success_seasons':successful,
          'errors':{k:v['reason'] for k,v in report.items() if v['status']!='partial_available'}},ensure_ascii=False))
    return data

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument('--max-seasons',type=int,default=2)
    a=p.parse_args()
    collect(max_seasons=max(0,min(2,a.max_seasons)))
