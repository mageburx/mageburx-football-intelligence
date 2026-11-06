#!/usr/bin/env python3
"""Small optional official DBU Betinia Liga 2026/27 results verification.

Reads one public league fixture table per day, only if robots.txt permits it.
On unrecognized HTML / rate limits, preserve TheSportsDB data unchanged.
No scraping authentication, bypass, bulk collection or redistribution of HTML.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import urllib.error
from pathlib import Path

try:
    from scripts.scrape_dbu import fetch_allowed,parse_page
    from scripts.collect_expanded_leagues import save_match
except ModuleNotFoundError:
    from scrape_dbu import fetch_allowed,parse_page
    from collect_expanded_leagues import save_match

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/'data'/'season.json'
URL='https://www.dbu.dk/resultater/pulje/507530/kampprogramFuld'
ALIASES={
    'Hvidovre':'Hvidovre','Vejle Boldklub':'Vejle','Vejle BK':'Vejle',
    'FC Fredericia':'Fredericia','AB':'AB Gladsaxe',
    'Aarhus Fremad':'Aarhus Fremad','Hobro IK':'Hobro',
    'Kolding IF':'Kolding','AaB':'AaB','Aalborg BK':'AaB',
    'Hillerød Fodbold':'Hillerød','Vendsyssel FF':'Vendsyssel',
    'HB Køge':'Køge','Esbjerg fB':'Esbjerg',
}
def normalize(name):
    if name not in ALIASES:raise ValueError('Unknown official Danish club: '+str(name))
    return ALIASES[name]


def collect(path=PATH,getter=fetch_allowed,now=None,min_hours=22):
    now=now or dt.datetime.now(dt.timezone.utc)
    data=json.loads(path.read_text(encoding='utf8'))
    league=data.get('leagues',{}).get('dk2')
    if not isinstance(league,dict) or league.get('source_season')!='2026-2027':
        raise ValueError('Expected initialized Danish first division 2026-27')
    meta=dict(league.get('dbu_official',{}))
    last=meta.get('checked_at')
    # A previous parser rejection caused by an unrecognized club alias can
    # be retried immediately after the parser is fixed. Other failures still
    # respect the daily interval to avoid hammering the official website.
    if last and not str(meta.get('error') or '').startswith('Unknown official Danish club'):
        try:
            if (now-dt.datetime.fromisoformat(last)).total_seconds()<min_hours*3600:
                return data
        except (ValueError,TypeError):pass
    report={'source_url':URL,'checked_at':now.replace(microsecond=0).isoformat(),
            'status':'unavailable_or_unverified','added':0,'matched':0,
            'conflicts':0,'error':None}
    try:
        html=getter(URL)
        records=parse_page(html,'2026-2027','regular',507530,URL)
        known={str(e['id']):e for e in league.get('events',[]) if e.get('id')}
        for event in records:
            if event['date']>=now.date().isoformat():continue
            try:
                home,away=normalize(event['home']),normalize(event['away'])
            except ValueError:
                report.setdefault('unrecognized_clubs',0)
                report['unrecognized_clubs']+=1
                continue
            key=(event['date'],home,away)
            existing=next((e for e in known.values()
                           if (e.get('date'),e.get('home'),e.get('away'))==key),None)
            if existing:
                if existing.get('finished') and (
                    existing.get('home_score'),existing.get('away_score'))!=(
                    event['home_score'],event['away_score']):
                    report['conflicts']+=1
                    continue
                if not existing.get('finished'):
                    existing.update({'finished':True,'home_score':event['home_score'],
                                     'away_score':event['away_score']})
                report['matched']+=1
                continue
            row={'id':event['id'],'date':event['date'],'utc':'','round':0,
                 'home':home,'away':away,'home_score':event['home_score'],
                 'away_score':event['away_score'],'finished':True}
            save_match(known,row)
            report['added']+=1
        league['events']=sorted(known.values(),key=lambda e:(e['date'],str(e.get('id'))))
        report['status']='partial_verified_source' if report['conflicts'] else 'sample_available'
    except (OSError,PermissionError,RuntimeError,ValueError,TypeError,
            urllib.error.URLError) as exc:
        report['error']=str(exc)[:170]
    league['dbu_official']=report
    league['partial']=True
    path.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf8')
    print('Danish official result sample',json.dumps(report,ensure_ascii=False))
    return data


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--season',type=Path,default=PATH)
    args=p.parse_args()
    collect(args.season)
