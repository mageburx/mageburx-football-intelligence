#!/usr/bin/env python3
"""Verify *when* lineup information was observable, not merely that it exists.

TheSportsDB free event lineup endpoint can return a truncated list. We only
mark an XI verified if >=11 distinct starters for EACH team and the retrieval
time is strictly earlier than the stored UTC kickoff. Missing players NEVER
count as confirmed injuries / absences. Reports are observations, not bets.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data'/'prematch_lineups.json'
INPUT=ROOT/'data'/'season.json'
URL='https://www.thesportsdb.com/api/v1/json/123/lookuplineup.php'
USER_AGENT='MageburxFootballIntelligence/5.2 (public lineups; no post-game hindsight)'

def kickoff_utc(text):
    if not text:return None
    try:
        d=dt.datetime.fromisoformat(str(text).replace('Z','+00:00'))
        return d.astimezone(dt.timezone.utc) if d.tzinfo else None
    except (TypeError,ValueError):
        return None

def validate(event, payload, observed_at):
    start=kickoff_utc(event.get('utc'))
    if not start or observed_at>=start:
        return {'status':'unverifiable_pre_kickoff_timestamp','home_n':0,'away_n':0}
    records=payload.get('lineup') if isinstance(payload,dict) else None
    if not isinstance(records,list):
        return {'status':'unavailable','home_n':0,'away_n':0}
    starters={'home':set(),'away':set()}
    for row in records:
        if not isinstance(row,dict) or str(row.get('idEvent'))!=str(event['id']):
            continue
        if str(row.get('strSubstitute','')).lower() not in ('no','false','0'):
            continue
        side='home' if str(row.get('strHome')).lower()=='yes' else 'away' if str(row.get('strHome')).lower()=='no' else None
        player=str(row.get('idPlayer') or row.get('strPlayer') or '').strip()
        if side and player:
            starters[side].add(player)
    n1,n2=len(starters['home']),len(starters['away'])
    # Free endpoints may be capped at 5; do not declare missing entries absent.
    complete=(n1>=11 and n2>=11)
    return {'status':'observed_complete_pre_kickoff' if complete else
            'partial_lineup_not_for_absence_inference',
            'home_n':n1,'away_n':n2}

def fetch_lineup(event_id):
    url=URL+'?'+urllib.parse.urlencode({'id':str(event_id)})
    request=urllib.request.Request(url,headers={'User-Agent':USER_AGENT})
    with urllib.request.urlopen(request,timeout=16) as r:
        return json.load(r)

def collect(season, output=OUT, now=None, fetch=fetch_lineup, max_calls=3):
    now=now or dt.datetime.now(dt.timezone.utc)
    old=json.loads(output.read_text(encoding='utf8')) if output.exists() else {
        'schema':1,'observations':[],'source':'TheSportsDB free lookuplineup'}
    observations={f"{x['league']}:{x['id']}":x for x in old.get('observations',[])
                  if x.get('league') and x.get('id')}
    choices=[]
    for lid,info in season.get('leagues',{}).items():
        for e in info.get('events',[]):
            start=kickoff_utc(e.get('utc'))
            if not start or e.get('finished') or not now<start<=now+dt.timedelta(hours=36):
                continue
            choices.append((start,lid,e))
    choices.sort(key=lambda x:x[0])
    checked=0
    for start,lid,e in choices:
        if checked>=max_calls:break
        key=f"{lid}:{e['id']}"
        previous=observations.get(key)
        if previous and previous.get('status')=='observed_complete_pre_kickoff':
            continue
        checked+=1
        try:
            raw=fetch(e['id'])
            assessment=validate(e,raw,now)
        except (OSError,ValueError,TypeError,urllib.error.URLError) as exc:
            if isinstance(exc,urllib.error.HTTPError) and exc.code==429:break
            assessment={'status':'source_unavailable','home_n':0,'away_n':0}
        # Preserve the earliest VERIFIED full lineup; keep incomplete status
        # if no evidence is returned.
        observations[key]={'league':lid,'id':str(e['id']),'date':e['date'],
                           'home':e['home'],'away':e['away'],
                           'kickoff_utc':start.isoformat(),
                           'observed_at':now.isoformat(),
                           'source_url':URL+'?id='+str(e['id']),
                           **assessment}
    old['observations']=sorted(observations.values(),key=lambda x:(x['date'],x['id']))[-250:]
    old['updated_at']=now.isoformat()
    old['coverage']='partial_free_endpoint'
    old['notice']='Missing lineup names are NOT evidence of a player being absent. No post-match observations are accepted.'
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(old,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf8')
    print(json.dumps({'observations':len(old['observations']),'checked':checked,
                      'verified':sum(x['status']=='observed_complete_pre_kickoff' for x in old['observations'])}))
    return old

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--max-calls',type=int,default=3)
    args=p.parse_args()
    collect(json.loads(INPUT.read_text(encoding='utf8')),max_calls=max(0,min(5,args.max_calls)))
