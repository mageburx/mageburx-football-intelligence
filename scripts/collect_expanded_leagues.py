#!/usr/bin/env python3
"""Incremental, rate-limited TheSportsDB season/round collection for new leagues.

Supports continental 2026/27 seasons and Norway's calendar-year 2026 season.
Do not infer missing results as losses or missing fixtures as cancelled.
"""
from __future__ import annotations
try:
    from scripts.match_status import final_confirmed, normalize_status
except ModuleNotFoundError:
    from match_status import final_confirmed, normalize_status

import argparse
import datetime as dt
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/'data'/'season.json'
API='https://www.thesportsdb.com/api/v1/json/123/'
USER_AGENT='MageburxFootballIntelligence/6.1 (public sports results; github actions)'
LEAGUES={
    'nl':{'id':4337,'name':'Eredivisie','country':'Países Baixos',
          'source_season':'2026-2027','rounds':34,'games_per_round':9},
    'dk2':{'id':4683,'name':'Danish 1st Division','country':'Dinamarca',
           'source_season':'2026-2027','rounds':32,'games_per_round':6},
    'no':{'id':4358,'name':'Eliteserien','country':'Noruega',
          'source_season':'2026','rounds':30,'games_per_round':8},
}


class RateLimit(RuntimeError):
    pass


def fetch(endpoint,params,timeout=18):
    if endpoint not in ('eventsseason.php','eventsround.php'):
        raise ValueError('Unsupported TheSportsDB endpoint')
    url=API+endpoint+'?'+urllib.parse.urlencode(params)
    req=urllib.request.Request(url,headers={'User-Agent':USER_AGENT,'Accept':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=timeout) as response:
            value=json.loads(response.read(1_500_000))
    except urllib.error.HTTPError as exc:
        if exc.code==429:raise RateLimit('TheSportsDB quota reached (HTTP 429)') from exc
        raise
    if not isinstance(value,dict) or value.get('events') is not None and not isinstance(value['events'],list):
        raise ValueError('Unexpected TheSportsDB event payload')
    return value.get('events') or []


def score(value):
    try:
        if value is None or isinstance(value,bool) or str(value).strip()=='':
            return None
        n=int(value)
        return n if 0<=n<30 else None
    except (TypeError,ValueError):
        return None


def parse_event(raw,lid,today=None):
    config=LEAGUES[lid]
    today=today or dt.datetime.now(dt.timezone.utc).date()
    if not isinstance(raw,dict) or str(raw.get('idLeague'))!=str(config['id']):
        return None
    if str(raw.get('strSeason'))!=config['source_season']:
        return None
    date=str(raw.get('dateEvent') or '')[:10]
    try:
        day=dt.date.fromisoformat(date)
        year=int(config['source_season'][:4])
        if not (year<=day.year<=year+int(lid!='no')):return None
    except (ValueError,TypeError):
        return None
    home=str(raw.get('strHomeTeam') or '').strip()
    away=str(raw.get('strAwayTeam') or '').strip()
    if not home or not away or home==away:return None
    hs,aws=score(raw.get('intHomeScore')),score(raw.get('intAwayScore'))
    finished=hs is not None and aws is not None and final_confirmed(raw)
    status=normalize_status(raw.get('strStatus'))
    try:
        rnd=int(raw.get('intRound') or 0)
        if rnd<1 or rnd>config['rounds']:rnd=0
    except (TypeError,ValueError):rnd=0
    return {
        'id':str(raw.get('idEvent') or f'{lid}:{date}:{home}:{away}'),
        'date':date,'utc':str(raw.get('strTimestamp') or ''),
        'round':rnd,'home':home,'away':away,
        'home_score':hs if finished else None,
        'away_score':aws if finished else None,
        'finished':finished,
        'result_verified':finished,
        'match_status':status,
        'progress':str(raw.get('strProgress') or ''),
        'live_home_score':hs if not finished else None,
        'live_away_score':aws if not finished else None,
    }


def valid_items(raw,lid,today):
    return [m for event in raw if (m:=parse_event(event,lid,today)) is not None]


def save_match(known,item):
    existing=known.get(item['id'])
    if existing is None:
        # Secondary CC0 archives use stable synthetic IDs; do not duplicate a
        # fixture from the primary API when its original ID differs.
        for previous in known.values():
            if (previous.get('date')==item.get('date') and
                previous.get('home')==item.get('home') and
                previous.get('away')==item.get('away')):
                existing=previous
                break
    if existing is not None and existing.get('id')!=item['id']:
        # Same displayed date/team names do NOT certify equal source IDs.
        # Preserve the original fixture and do not transfer score or FT.
        alternatives=existing.setdefault('other_source_ids',[])
        if item['id'] not in alternatives:alternatives.append(item['id'])
        return
    if existing is None:
        known[item['id']]=item
        return
    if existing.get('finished') and item.get('finished') and (
        existing.get('home_score'),existing.get('away_score'))!=(
        item.get('home_score'),item.get('away_score')):
        # Quarantine inconsistent provider scores instead of treating either as final.
        known[item['id']]={**existing,**item,'finished':False,'result_verified':False,
                           'home_score':None,'away_score':None,
                           'score_conflict':True,
                           'result_dispute':{
                               'original_score':[existing.get('home_score'),existing.get('away_score')],
                               'provider_score':[item.get('home_score'),item.get('away_score')]}}
        return
    if existing.get('score_conflict'):return
    if existing.get('finished') and not item.get('finished'):
        # Never discard a previously observed score just because an API
        # round snapshot omits FT status. It remains *unverified* unless
        # independent evidence confirmed it.
        return
    # Retain audit provenance and cooldown through routine API refreshes.
    known[item['id']]={**existing,**item}


def collect(path=PATH,max_calls=6,fetcher=fetch,pause=2.0,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    today=now.date()
    source=json.loads(path.read_text(encoding='utf8'))
    if source.get('schema')!=1 or source.get('season')!='2026-2027' or not all(
        x in source.get('leagues',{}) for x in ('pt','dk')):
        raise ValueError('Expected existing PT/DK 2026-27 league snapshot')
    work={}
    for lid,cfg in LEAGUES.items():
        existing=source['leagues'].get(lid,{})
        known={str(x['id']):x for x in existing.get('events',[])
               if isinstance(x,dict) and x.get('id')}
        meta=dict(existing.get('collection',{}))
        meta.setdefault('verified_rounds',[])
        meta.setdefault('attempted_rounds',{})
        work[lid]={'cfg':cfg,'known':known,'meta':meta,'status':'partial'}
    # Explore the league season endpoint once a day, where it is allowed.
    # Free endpoint may be truncated; completeness is NEVER inferred here.
    calls=0
    quota_exhausted=False
    for lid,c in work.items():
        if calls>=max_calls:break
        # Norway has a documented secondary research snapshot; skip TSDB bulk
        # calls while it already supplies almost the entire 2026 fixture list.
        norwegian=source['leagues'].get('no',{})
        if lid=='no' and len(c['known'])>=200 and (norwegian.get('fantasy_research') or {}).get('source_matches',0)>=220:
            continue
        last=c['meta'].get('season_checked_at')
        if last:
            try:
                if (now-dt.datetime.fromisoformat(last)).total_seconds()<86400:continue
            except (ValueError,TypeError):pass
        try:
            data=fetcher('eventsseason.php',{'id':c['cfg']['id'],'s':c['cfg']['source_season']})
            for event in valid_items(data,lid,today):save_match(c['known'],event)
            c['meta']['season_checked_at']=now.replace(microsecond=0).isoformat()
            c['meta']['season_api_count']=len(data)
        except RateLimit:
            c['status']='rate_limited'
            calls+=1
            quota_exhausted=True
            break
        except (OSError,ValueError,RuntimeError) as exc:
            c['status']='source_partial_or_unavailable'
            c['meta']['last_error']=str(exc)[:180]
            # Failure is not evidence of a blank season.
        calls+=1
        if pause:time.sleep(pause)
    # Interleave round-specific requests across leagues, retaining progress.
    targets=[]
    for lid,c in work.items():
        cfg=c['cfg'];meta=c['meta'];now_str=now.isoformat()
        norwegian=source['leagues'].get('no',{})
        if lid=='no' and len(c['known'])>=200 and (norwegian.get('fantasy_research') or {}).get('source_matches',0)>=220:
            continue
        verified=set(meta['verified_rounds'])
        attempted=meta['attempted_rounds']
        for rnd in range(1,cfg['rounds']+1):
            if rnd in verified:continue
            # Avoid spending scarce primary API calls on fully scored CC0 rounds.
            if lid=='nl' and sum(e.get('round')==rnd and e.get('finished') is True
                                  for e in c['known'].values())>=cfg['games_per_round']:
                continue
            recent=attempted.get(str(rnd))
            if recent:
                try:
                    if (now-dt.datetime.fromisoformat(recent)).total_seconds()<86400:continue
                except (ValueError,TypeError):pass
            # The earliest unverified rounds give a useful historical base.
            targets.append((rnd,lid))
    # Distinct leagues alternate; do not spend the budget on one competition.
    # Prioritize leagues without a complementary CC0 source first.
    targets.sort(key=lambda x:(x[0],('dk2','no','nl').index(x[1])))
    for rnd,lid in targets:
        if quota_exhausted or calls>=max_calls:break
        c=work[lid]
        cfg=c['cfg'];meta=c['meta']
        try:
            data=fetcher('eventsround.php',{'id':cfg['id'],'s':cfg['source_season'],'r':rnd})
            records=valid_items(data,lid,today)
            for item in records:save_match(c['known'],item)
            # A full round today may still be amended later by the provider;
            # refresh a few recent rounds daily through season endpoint.
            if len(records)>=cfg['games_per_round']:
                meta['verified_rounds']=sorted(set(meta['verified_rounds']+[rnd]))
            meta['attempted_rounds'][str(rnd)]=now.replace(microsecond=0).isoformat()
        except RateLimit:
            c['status']='rate_limited'
            calls+=1
            quota_exhausted=True
            break
        except (OSError,ValueError,RuntimeError) as exc:
            c['status']='source_partial_or_unavailable'
            meta['attempted_rounds'][str(rnd)]=now.replace(microsecond=0).isoformat()
            meta['last_error']=str(exc)[:180]
        calls+=1
        if pause:time.sleep(pause)
    for lid,c in work.items():
        cfg=c['cfg'];known=c['known'];meta=c['meta']
        events=sorted(known.values(),key=lambda m:(m['date'],m.get('utc',''),m['id']))
        checked=set(meta['verified_rounds'])
        partial=len(checked)<cfg['rounds'] or c['status']!='partial'
        previous=source['leagues'].get(lid,{})
        # Keep the complementary-source audit trail and daily-fetch gates.
        # Dropping these on each hourly update previously erased signed-ID
        # provenance and caused redundant Norwegian/DBU HTTP requests.
        source['leagues'][lid]={
            'name':cfg['name'],'id':cfg['id'],'country':cfg['country'],
            'source_season':cfg['source_season'],'events':events,
            'partial':partial,'rounds_ok':len(checked),
            'rounds_failed':[],
            'missing_past_rounds':[x for x in range(1,cfg['rounds']+1) if x not in checked],
            'last_attempt_at':now.replace(microsecond=0).isoformat(),
            'collection':meta,
            'coverage_note':'Partial until every round is independently verified. Norwegian season is calendar year 2026; Danish play-off rounds may reuse numbers.',
        }
        for field in ('openfootball','fantasy_research','dbu_official','result_recovery'):
            if isinstance(previous,dict) and isinstance(previous.get(field),dict):
                source['leagues'][lid][field]=previous[field]
        print(f'{lid}: {len(events)} fixtures, {sum(bool(e["finished"]) for e in events)} finished, verified rounds {len(checked)}/{cfg["rounds"]}; status {c["status"]}',flush=True)
    source['updated_at']=now.replace(microsecond=0).isoformat()
    path.write_text(json.dumps(source,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(f'Expanded league collection: {calls} API requests; existing PT/DK fixtures preserved.',flush=True)
    return source


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--output',type=Path,default=PATH)
    p.add_argument('--max-calls',type=int,default=6)
    p.add_argument('--pause',type=float,default=2.)
    args=p.parse_args()
    collect(path=args.output,max_calls=max(0,min(args.max_calls,12)),pause=args.pause)
