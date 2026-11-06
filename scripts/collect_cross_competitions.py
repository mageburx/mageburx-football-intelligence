#!/usr/bin/env python3
"""Conservative cross-competition calendar for PT/DK league clubs.

Domestic cups + UEFA competitions. This is a PARTIAL schedule of freely
returned TheSportsDB round endpoints; no full-season completeness claims.
Historical fixtures only influence *past-match schedule context*, never
league results, goals priors, Elo or the main trained models.

Respect free API 429 / retry-after; every successful round is checkpointed
in data/cross_competitions.json and persisted through football-data branch.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/'data'/'cross_competitions.json'
API='https://www.thesportsdb.com/api/v1/json/123/eventsround.php'
AGENT='MageburxFootballIntelligence/5.2 (public schedule metadata)'
COMPETITIONS={
  'pt_cup':{'id':'4510','name':'Taça de Portugal','scope':'pt','type':'domestic_cup'},
  'pt_league_cup':{'id':'4509','name':'Taça da Liga','scope':'pt','type':'domestic_cup'},
  'uefa_cl':{'id':'4480','name':'UEFA Champions League','scope':'both','type':'european'},
  'uefa_el':{'id':'4481','name':'UEFA Europa League','scope':'both','type':'european'},
  'uefa_ecl':{'id':'5071','name':'UEFA Conference League','scope':'both','type':'european'},
}
SEASONS=('2024-2025','2025-2026','2026-2027')
# A trial upper bound on rounds to CHECK, never assumed season completeness.
MAX_ROUND={'domestic_cup':9,'european':10}
ALIASES={
    'sporting lisbon':'Sporting CP','sporting cp':'Sporting CP','sporting':'Sporting CP',
    'fc porto':'Porto','porto':'Porto','sl benfica':'Benfica','benfica':'Benfica',
    'sc braga':'Braga','sporting braga':'Braga','braga':'Braga',
    'famalicao':'Famalicao','fc famalicao':'Famalicao',
    'vitoria sc':'Vitória de Guimarães','vitoria guimaraes':'Vitória de Guimarães',
    'vitoria de guimaraes':'Vitória de Guimarães',
    'cd nacional':'Nacional de Madeira','nacional':'Nacional de Madeira',
    'estoril':'Estoril Praia','estoril praia':'Estoril Praia',
    'boavista':'Boavista','gil vicente':'Gil Vicente','rio ave':'Rio Ave',
    'santa clara':'Santa Clara','casa pia':'Casa Pia',
    'fc copenhagen':'FC Copenhagen','fc kobenhavn':'FC Copenhagen',
    'f c kobenhavn':'FC Copenhagen','f c copenhagen':'FC Copenhagen',
    'fc kobenhavn':'FC Copenhagen','kobenhavn':'FC Copenhagen',
    'brondby':'Brøndby','brondby if':'Brøndby',
    'agf aarhus':'AGF Aarhus','aarhus gf':'AGF Aarhus','agf':'AGF Aarhus',
    'fc midtjylland':'FC Midtjylland','midtjylland':'FC Midtjylland',
    'fc nordsjaelland':'FC Nordsjælland','nordsjaelland':'FC Nordsjælland',
    'silkeborg':'Silkeborg IF','silkeborg if':'Silkeborg IF',
    'viborg':'Viborg','viborg ff':'Viborg',
    'sonderjyske':'Sønderjyske','sonderjyske fodbold':'Sønderjyske',
    'odense':'Odense BK','odense bk':'Odense BK','ob':'Odense BK',
    'randers':'Randers FC','randers fc':'Randers FC',
    'lyngby':'Lyngby','lyngby bk':'Lyngby',
}
def normal(text):
    text=unicodedata.normalize('NFKD',str(text).strip().casefold())
    text=''.join(c for c in text if not unicodedata.combining(c))
    text=text.replace('ø','o').replace('æ','ae').replace('ß','ss')
    return re.sub(r'\s+',' ',re.sub(r'[^a-z0-9 ]',' ',text)).strip()

def canonical(name):
    return ALIASES.get(normal(name),str(name).strip())

def parse_event(e,season,key,asof_date):
    c=COMPETITIONS[key]
    if str(e.get('idLeague'))!=c['id'] or str(e.get('strSeason'))!=season:
        return None
    eid=str(e.get('idEvent') or '').strip()
    date=str(e.get('dateEvent') or '')[:10]
    try:
        day=dt.date.fromisoformat(date)
    except ValueError:
        return None
    if day.year not in (int(season[:4]),int(season[:4])+1) or not eid:return None
    home=canonical(e.get('strHomeTeam') or '')
    away=canonical(e.get('strAwayTeam') or '')
    if not home or not away or normal(home)==normal(away):return None
    def score(v):
        try:
            n=int(v)
            return n if 0<=n<=30 else None
        except (TypeError,ValueError):return None
    hs,aws=score(e.get('intHomeScore')),score(e.get('intAwayScore'))
    finished=bool(hs is not None and aws is not None and date<asof_date)
    return {
      'id':eid,'date':date,'utc':str(e.get('strTimestamp') or ''),
      'home':home,'away':away,'competition_id':key,
      'competition':c['name'],'competition_type':c['type'],
      'home_score':hs if finished else None,
      'away_score':aws if finished else None,
      'finished':finished,
      'league_model_eligible':False,'source':'TheSportsDB round schedule',
    }

def fetch_round(key,season,round_number):
    c=COMPETITIONS[key]
    url=API+'?'+urllib.parse.urlencode({'id':c['id'],'s':season,'r':round_number})
    request=urllib.request.Request(url,headers={'User-Agent':AGENT,'Accept':'application/json'})
    try:
        with urllib.request.urlopen(request,timeout=20) as response:
            payload=json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code==429:raise RuntimeError('rate_limit_429') from exc
        raise
    if not isinstance(payload,dict):raise ValueError('Invalid JSON payload')
    events=payload.get('events')
    if events is None:return []
    if not isinstance(events,list):raise ValueError('Invalid events payload')
    return events

def empty():
    return {'schema':1,'source':'TheSportsDB v1 free eventsround',
            'coverage':'partial','updated_at':None,
            'competitions':{},'events':[],'conflicts':[],
            'disclaimer':'Coverage partial; missing cup/European fixtures may understate fatigue. No league model changes.'}

def priorities(data,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    # Gather 2026/27 UEFA rounds first; then cups and retrospective seasons.
    plans=[]
    for season in reversed(SEASONS):
        for key in ('uefa_cl','uefa_el','uefa_ecl','pt_cup','pt_league_cup'):
            meta=data['competitions'].get(f'{key}:{season}',{})
            checked=set(meta.get('checked_rounds',[]))
            for rnd in range(1,MAX_ROUND[COMPETITIONS[key]['type']]+1):
                if rnd in checked:continue
                last_empty=(meta.get('empty_checked_at') or {}).get(str(rnd))
                if last_empty:
                    try:
                        age=(now-dt.datetime.fromisoformat(last_empty)).total_seconds()
                        if age<7*86400:continue
                    except (ValueError,TypeError):pass
                plans.append((key,season,rnd))
    # Prioritise autumn UEFA league-phase (R4 then R3) for current
    # fixtures AND 2024/25, 2025/26 historical ablation. Do not spend
    # the entire free daily request budget on 2027 future rounds.
    season_order={s:i for i,s in enumerate(reversed(SEASONS))}
    league_order={k:i for i,k in enumerate(COMPETITIONS)}
    def ranking(p):
        key,season,rnd=p
        meta=COMPETITIONS[key]
        priority=0 if meta['type']=='european' and rnd in (3,4) else (
            1 if meta['type']=='european' and rnd in (2,5) else 2)
        round_rank={4:0,3:1,5:2,2:3,1:4}.get(rnd,5+rnd)
        return (priority,season_order[season],round_rank,league_order[key])
    return sorted(plans,key=ranking)

def collect(path=PATH,max_calls=9,pause=3.5,fetcher=fetch_round,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    asof_date=now.date().isoformat()
    data=json.loads(path.read_text(encoding='utf-8')) if path.exists() else empty()
    indexed={e['id']:e for e in data.get('events',[]) if isinstance(e,dict) and e.get('id')}
    added=updated=success=attempted=0
    errors=[]
    for key,season,rnd in priorities(data,now)[:max_calls]:
        attempted+=1
        title=f'{key}:{season}'
        meta=data['competitions'].setdefault(title,{
            'id':COMPETITIONS[key]['id'],'name':COMPETITIONS[key]['name'],
            'scope':COMPETITIONS[key]['scope'],'type':COMPETITIONS[key]['type'],
            'checked_rounds':[],'empty_rounds':[],'empty_checked_at':{},'status':'partial',
        })
        try:
            raw=fetcher(key,season,rnd)
            events=[e for row in raw if (e:=parse_event(row,season,key,asof_date))]
            if not events:
                meta['empty_rounds']=sorted(set(meta.get('empty_rounds',[])+[rnd]))
                meta.setdefault('empty_checked_at',{})[str(rnd)]=now.isoformat()
                errors.append(f'{title} R{rnd}: empty round; retry in 7 days')
                continue
            for e in events:
                old=indexed.get(e['id'])
                if old:
                    if old['competition_id']!=key or old['date']!=e['date'] or (
                        normal(old['home'])!=normal(e['home']) or normal(old['away'])!=normal(e['away'])
                    ) or (old.get('finished') and e['finished'] and
                          (old['home_score'],old['away_score'])!=(e['home_score'],e['away_score'])):
                        data['conflicts'].append({'id':e['id'],'competition_id':key,'date':e['date'],
                                                  'reason':'Conflicting ID/date/clubs/final score'})
                        continue
                    if e['finished'] and not old.get('finished'):
                        indexed[e['id']]=e;updated+=1
                else:
                    indexed[e['id']]=e;added+=1
            meta['checked_rounds']=sorted(set(meta['checked_rounds']+[rnd]))
            meta['empty_rounds']=[x for x in meta.get('empty_rounds',[]) if x!=rnd]
            meta.setdefault('empty_checked_at',{}).pop(str(rnd),None)
            success+=1
            print(title,'round',rnd,'events',len(events),flush=True)
        except (ValueError,TimeoutError,urllib.error.URLError,RuntimeError) as exc:
            errors.append(f'{title} R{rnd}: {str(exc)[:140]}')
            if 'rate_limit_429' in str(exc):
                print('API rate limit: ending batch; preserving previous results',flush=True)
                break
        if pause and max_calls>1:time.sleep(pause)
    data['events']=sorted(indexed.values(),key=lambda x:(x['date'],x['competition_id'],x['id']))
    data['updated_at']=now.replace(microsecond=0).isoformat()
    data['coverage']='partial'
    data['last_run']={'attempted':attempted,
                      'successful_rounds':success,'added':added,'updated':updated,
                      'warnings':errors[:24]}
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    print('Cross competitions',json.dumps({'total':len(data['events']),'added':added,
                                          'success':success,'warnings':errors[:5]},ensure_ascii=False))
    return data

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--max-calls',type=int,default=9)
    p.add_argument('--pause',type=float,default=3.5)
    args=p.parse_args()
    collect(max_calls=max(0,min(18,args.max_calls)),pause=max(0,args.pause))
