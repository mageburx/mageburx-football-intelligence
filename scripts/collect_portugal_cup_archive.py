#!/usr/bin/env python3
"""PT cup 2024/25–2025/26 plus 2024/25 league cup: archival fixture dates.

The archive has 148, 111 and 7 completed match records respectively.
Only competition schedule exposure is used for backtesting. Marked cup
scores (* / ** may mean extra time or shootout) never enter 90-min models.
Use a verified robots.txt check and fetch each fixed URL at most monthly.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import re
import urllib.request
import urllib.robotparser
from pathlib import Path

try:
    from scripts.collect_danish_cup_archive import ArchiveParser,MONTHS
    from scripts.collect_cross_competitions import canonical,normal
except ModuleNotFoundError:
    from collect_danish_cup_archive import ArchiveParser,MONTHS
    from collect_cross_competitions import canonical,normal

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/'data'/'cross_competitions.json'
SITE='https://ecst.se'
USER_AGENT='MageburxFootballIntelligence/5.4 (+https://github.com/mageburx/mageburx-football-intelligence)'
ARCHIVES={
  'pt_cup:2024-2025':{'url':SITE+'/fotboll/por/stat/C_2425.php','year':2024,
                       'competition':'Taça de Portugal','id':'pt_cup','expected':148},
  'pt_cup:2025-2026':{'url':SITE+'/fotboll/por/stat/C_2526.php','year':2025,
                       'competition':'Taça de Portugal','id':'pt_cup','expected':111},
  'pt_league_cup:2024-2025':{'url':SITE+'/fotboll/por/stat/L_2425.php','year':2024,
                       'competition':'Taça da Liga','id':'pt_league_cup','expected':7},
}
def parse_archive(html,reference):
    if not isinstance(html,str) or len(html)<300 or 'score-game' not in html:
        raise ValueError('Source document unavailable')
    pp=ArchiveParser()
    pp.feed(html)
    records={}
    for g in pp.games:
        label=g.get('date_label') or ''
        d=re.search(r'\b(\d{1,2})\s+([A-Za-zÅÄÖåäö]+)\s+(20\d{2})\b',label)
        # Starred cup scores are included solely to prove a fixture was played.
        score=re.fullmatch(r'\*{0,2}\s*(\d{1,2})\s*-\s*(\d{1,2})\s*\*{0,2}',g.get('m2',''))
        if not d or not score:continue
        month=MONTHS.get(d.group(2).lower())
        if month is None:continue
        try:day=dt.date(int(d.group(3)),month,int(d.group(1)))
        except ValueError:continue
        y=reference['year']
        if not dt.date(y,7,1)<=day<dt.date(y+1,7,1):continue
        home,away=(canonical(g.get(k,'')) for k in ('m1','m3'))
        if not home or not away or normal(home)==normal(away):continue
        key=(day.isoformat(),normal(home),normal(away))
        if key in records:
            raise ValueError('Duplicate date/team fixture in source archive')
        match_hash=hashlib.sha256('|'.join(key).encode('utf8')).hexdigest()[:18]
        records[key]={
          'id':f'ecst_{reference["id"]}:'+match_hash,
          'date':day.isoformat(),'utc':'','home':home,'away':away,
          'competition_id':reference['id'],'competition':reference['competition'],
          'competition_type':'domestic_cup',
          'home_score':int(score.group(1)),'away_score':int(score.group(2)),
          'finished':True,'league_model_eligible':False,
          'score_basis':'unknown_regulation_or_extra_time_or_penalties',
          'source':reference['url'],'source_name':'ECST historical Portugal cup calendar'
        }
    # Require a nearly complete archive, don't pretend 60 matches = 148.
    if len(records)<int(reference['expected']*.94) or len(records)>reference['expected']+3:
        raise ValueError(f'Incomplete archive {len(records)}/{reference["expected"]}')
    return sorted(records.values(),key=lambda e:(e['date'],e['id']))

def fetch_allowed(url):
    if url not in {ref['url'] for ref in ARCHIVES.values()}:
        raise ValueError('Unknown archive URL')
    rp=urllib.robotparser.RobotFileParser()
    req=urllib.request.Request(SITE+'/robots.txt',headers={'User-Agent':USER_AGENT})
    try:
        with urllib.request.urlopen(req,timeout=15) as response:
            robots=response.read(200000).decode('utf8','replace')
        if 'user-agent:' not in robots.lower():raise ValueError('Invalid robots.txt')
        rp.parse(robots.splitlines())
    except (ValueError,OSError) as exc:
        raise RuntimeError('Cannot verify robots.txt; skip archive') from exc
    if not rp.can_fetch(USER_AGENT,url):
        raise PermissionError('robots.txt prohibits scraping this archive')
    req=urllib.request.Request(url,headers={'User-Agent':USER_AGENT,'Accept':'text/html'})
    with urllib.request.urlopen(req,timeout=18) as response:
        if response.status!=200:raise RuntimeError('Source HTTP error')
        return response.read(2000000).decode('utf8','replace')

def collect(path=PATH,fetcher=fetch_allowed,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    data=json.loads(path.read_text(encoding='utf8'))
    report=data.setdefault('portugal_cup_archive',{})
    indexed={e['id']:e for e in data['events']}
    used={(e.get('competition_id'),e['date'],normal(canonical(e['home'])),
           normal(canonical(e['away']))):e for e in indexed.values()}
    for name,ref in ARCHIVES.items():
        previous=report.get(name,{})
        stamp=previous.get('checked_at')
        if stamp:
            try:
                age=(now-dt.datetime.fromisoformat(stamp)).total_seconds()
                if previous.get('status')=='historical_sample_available' and age<30*86400:continue
                if previous.get('status')!='historical_sample_available' and age<6*3600:continue
            except (TypeError,ValueError):pass
        added=matched=0
        try:
            matches=parse_archive(fetcher(ref['url']),ref)
            additions={}
            conflicts=[]
            for item in matches:
                key=(item['competition_id'],item['date'],
                     normal(canonical(item['home'])),normal(canonical(item['away'])))
                old=used.get(key)
                if old:
                    if (old.get('home_score'),old.get('away_score'))!=(
                          item['home_score'],item['away_score']):
                        conflicts.append({'date':item['date'],'home':item['home'],
                                          'away':item['away'],'competition':name})
                    else:matched+=1
                else:additions[item['id']]=item
            if conflicts:
                data.setdefault('conflicts',[]).extend(conflicts[:15])
                raise ValueError(f'{len(conflicts)} cross-source result conflicts')
            indexed.update(additions)
            for item in additions.values():
                key=(item['competition_id'],item['date'],
                     normal(canonical(item['home'])),normal(canonical(item['away'])))
                used[key]=item
            added=len(additions)
            report[name]={'status':'historical_sample_available','source_url':ref['url'],
                'checked_at':now.isoformat(),'parsed':len(matches),
                'added':added,'matched':matched,
                'license_note':'Dates for schedule research only; no source bulk republication.'}
        except (OSError,ValueError,RuntimeError,PermissionError) as exc:
            report[name]={'status':'source_unavailable_or_conflicted','source_url':ref['url'],
                          'checked_at':now.isoformat(),'reason':str(exc)[:180]}
            print('Portugal archive unavailable:',name,str(exc)[:130],flush=True)
            if 'robots.txt' in str(exc).lower():break
    data['events']=sorted(indexed.values(),key=lambda x:(x['date'],x['competition_id'],x['id']))
    data['coverage']='partial'
    path.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf8')
    print('Portugal archival cups: '+json.dumps({
        k:{'status':v['status'],'parsed':v.get('parsed'),'added':v.get('added')}
        for k,v in report.items()},ensure_ascii=False),flush=True)
    return data

if __name__=='__main__':
    collect()
