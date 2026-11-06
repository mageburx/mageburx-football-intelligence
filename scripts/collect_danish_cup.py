#!/usr/bin/env python3
"""Optional Danish national cup fixtures from the *national* DBU competition.

Uses the existing robots-aware official DBU collector and fails closed when
pages are unavailable. Only match exposure/date is used for schedule context.
Do not infer goal strengths from a cup final score (which may include ET).
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
from pathlib import Path
try:
    from scripts.scrape_dbu import parse_page,fetch_allowed
    from scripts.collect_cross_competitions import canonical,normal
except ModuleNotFoundError:
    from scrape_dbu import parse_page,fetch_allowed
    from collect_cross_competitions import canonical,normal

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/'data'/'cross_competitions.json'
DBU_POOLS={'2026-2027':508655,'2025-2026':474116}

def collect(path=PATH,fetcher=fetch_allowed,parser=parse_page,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    data=json.loads(path.read_text(encoding='utf8'))
    existing={x['id']:x for x in data.get('events',[]) if x.get('id')}
    problems=[]
    added=0
    for season,pool in DBU_POOLS.items():
        url=f'https://www.dbu.dk/resultater/pulje/{pool}/kampprogramFuld'
        try:
            html=fetcher(url)
            matches=parser(html,season,'domestic_cup',pool,url)
            count=0
            for entry in matches:
                # DBU event id is already namespaced; preserve official record.
                if entry['date']>=now.date().isoformat() or not entry.get('finished'):
                    continue
                event={
                    'id':entry['id'],'date':entry['date'],'utc':'',
                    'home':canonical(entry['home']),'away':canonical(entry['away']),
                    'competition_id':'dk_cup','competition':'DBU Pokalen',
                    'competition_type':'domestic_cup',
                    'home_score':entry['home_score'],'away_score':entry['away_score'],
                    'finished':True,'league_model_eligible':False,
                    'score_basis':'unknown_regulation_or_extra_time',
                    'source':url,
                }
                if event['id'] in existing:
                    old=existing[event['id']]
                    if (old['home_score'],old['away_score'])!=(event['home_score'],event['away_score']):
                        data.setdefault('conflicts',[]).append({'id':event['id'],'reason':'DBU score conflict','source':url})
                    continue
                existing[event['id']]=event
                count+=1
                added+=1
            data.setdefault('danish_cup_source',{})[season]={
                'status':'partial_available','matches_seen':len(matches),
                'added':count,'source_url':url,'last_checked_at':now.isoformat()}
        except (OSError,ValueError,RuntimeError,PermissionError) as exc:
            data.setdefault('danish_cup_source',{})[season]={
                'status':'temporarily_unavailable_or_not_allowed',
                'source_url':url,'last_checked_at':now.isoformat(),
                'reason':str(exc)[:100]}
            problems.append(str(exc)[:140])
            if 'robots' in str(exc).casefold():break
    data['events']=sorted(existing.values(),key=lambda x:(x['date'],x['id']))
    data['coverage']='partial'
    path.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf8')
    print('DBU cup:',json.dumps({'added':added,'errors':problems[:3]},ensure_ascii=False))
    return data

if __name__=='__main__':
    p=argparse.ArgumentParser()
    args=p.parse_args()
    collect()
