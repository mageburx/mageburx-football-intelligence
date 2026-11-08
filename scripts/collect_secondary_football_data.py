#!/usr/bin/env python3
"""Optional football-data.org secondary cross-check for Portugal and Eredivisie.

No result is overwritten, no signed prediction is settled. Only one authenticated
bulk competition request per league every 22h. Missing tokens, 403 and 429
are normal, recorded states. Exact/oriented club/date checks avoid ID transfer.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'data'/'secondary_football_data.json'
BASE='https://api.football-data.org/v4/competitions/'
CODES={'pt':'PPL','nl':'DED'}
SEASON=2026
MIN_HOURS=22
MAX_EXAMPLES=8

def normalized(name):
    value=unicodedata.normalize('NFKD',str(name or ''))
    value=''.join(x for x in value if not unicodedata.combining(x))
    value=re.sub(r'[^a-z0-9]+',' ',value.casefold()).strip()
    parts=[x for x in value.split() if x not in
           ('fc','sc','cf','afc','sl','sv','futebol','clube','club','de','da','do')]
    return ' '.join(parts)

def download(code,token,season=SEASON):
    if code not in CODES.values() or not token:
        raise ValueError('Unknown competition or missing authentication')
    url=BASE+code+'/matches?'+urllib.parse.urlencode({'season':season})
    request=urllib.request.Request(url,headers={
        'Accept':'application/json','X-Auth-Token':token,
        'User-Agent':'MageburxFootballResearch/9.0 (max two league checks daily)'})
    with urllib.request.urlopen(request,timeout=25) as response:
        if response.status!=200:raise RuntimeError('Unexpected API HTTP status')
        data=response.read(1_300_000)
        if len(data)>=1_300_000:raise ValueError('Provider response unusually large')
        return json.loads(data)

def score_from_api(e):
    if str(e.get('status'))!='FINISHED':return None
    result=(e.get('score') or {}).get('fullTime') or {}
    a,b=result.get('home'),result.get('away')
    if type(a) is int and type(b) is int and 0<=a<=25 and 0<=b<=25:return a,b
    return None

def compare(league,local_events,payload):
    if not isinstance(payload,dict) or not isinstance(payload.get('matches'),list):
        raise ValueError('Malformed football-data.org match listing')
    competition=(payload.get('competition') or {}).get('code')
    if competition is not None and competition!=CODES[league]:
        raise ValueError('Unexpected competition')
    local=[x for x in local_events if isinstance(x,dict) and x.get('id')]
    results={'source':'football-data.org API v4','competition':CODES[league],
             'scope':'secondary audit only, no settlement or overwrite',
             'provider_matches':len(payload['matches']),
             'provider_final':0,'matched_fixtures':0,'agreed_scores':0,
             'disagreements':0,'local_score_missing':0,'unmatched_provider':0,
             'ambiguous_candidates':0,'examples':[]}
    for m in payload['matches']:
        if not isinstance(m,dict):continue
        score=score_from_api(m)
        if score is None:continue
        results['provider_final']+=1
        home=normalized((m.get('homeTeam') or {}).get('name'))
        away=normalized((m.get('awayTeam') or {}).get('name'))
        day=str(m.get('utcDate') or '')[:10]
        try:target=dt.date.fromisoformat(day)
        except ValueError:continue
        if not home or not away:continue
        candidates=[]
        for e in local:
            if normalized(e.get('home'))!=home or normalized(e.get('away'))!=away:
                continue
            try:fixture_day=dt.date.fromisoformat(str(e.get('date') or ''))
            except ValueError:continue
            if abs((target-fixture_day).days)<=1:candidates.append(e)
        if len(candidates)!=1:
            kind='unmatched_provider' if not candidates else 'ambiguous_candidates'
            results[kind]+=1
            continue
        e=candidates[0]
        results['matched_fixtures']+=1
        prior=(e.get('home_score'),e.get('away_score'))
        if not all(type(x) is int for x in prior) or e.get('finished') is not True:
            results['local_score_missing']+=1
            if len(results['examples'])<MAX_EXAMPLES:
                results['examples'].append({'kind':'local_final_not_verified',
                    'date':e.get('date'),'home':e.get('home'),'away':e.get('away'),
                    'provider_score':list(score),'local_id':str(e['id'])})
        elif prior==score:
            results['agreed_scores']+=1
        else:
            results['disagreements']+=1
            if len(results['examples'])<MAX_EXAMPLES:
                results['examples'].append({'kind':'source_disagreement',
                    'date':e.get('date'),'home':e.get('home'),'away':e.get('away'),
                    'stored_score':list(prior),'provider_score':list(score),
                    'local_id':str(e['id'])})
    return results

def collect(season,token,previous=None,fetcher=download,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:raise ValueError('Timezone-aware now required')
    prev=previous if isinstance(previous,dict) and previous.get('schema')==1 else {}
    out={'schema':1,'generated_at':now.isoformat(),
         'source_url':'https://www.football-data.org/',
         'policy':'Secondary source only; never write current fixtures or signed forecasts',
         'token_configured':bool(token),'leagues':{}}
    if not token:
        out['status']='not_configured'
        for lid in CODES:
            old=prev.get('leagues',{}).get(lid,{})
            out['leagues'][lid]={**old,'status':'not_configured'}
        return out
    statuses=[]
    for lid,code in CODES.items():
        prior=prev.get('leagues',{}).get(lid,{})
        attempted=prior.get('checked_at')
        cooldown=7*24 if prior.get('status') in ('access_restricted','unauthorized') else MIN_HOURS
        try:
            if attempted:
                age=(now-dt.datetime.fromisoformat(attempted.replace('Z','+00:00'))).total_seconds()
                if 0<=age<cooldown*3600:
                    out['leagues'][lid]=prior
                    statuses.append('cached')
                    continue
        except (ValueError,TypeError):pass
        result={'checked_at':now.isoformat(),'source':'football-data.org','competition':code}
        try:
            raw=fetcher(code,token,SEASON)
            result.update(compare(lid,season.get('leagues',{}).get(lid,{}).get('events',[]),raw))
            result['status']='audited'
        except urllib.error.HTTPError as exc:
            result['status']='access_restricted' if exc.code==403 else (
                'rate_limited' if exc.code==429 else 'source_unavailable')
            result['http_status']=exc.code
        except (OSError,RuntimeError,TypeError,KeyError,ValueError,
                urllib.error.URLError,json.JSONDecodeError) as exc:
            result['status']='source_unavailable'
            result['error_type']=type(exc).__name__
        statuses.append(result['status'])
        out['leagues'][lid]=result
    out['status']='audited' if all(s in ('audited','cached') for s in statuses) else 'partial_or_restricted'
    return out

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--season',type=Path,default=ROOT/'data'/'season.json')
    p.add_argument('--output',type=Path,default=OUTPUT)
    args=p.parse_args()
    season=json.loads(args.season.read_text(encoding='utf8'))
    previous=json.loads(args.output.read_text(encoding='utf8')) if args.output.exists() else None
    token=os.getenv('FOOTBALL_DATA_API_TOKEN','').strip()
    report=collect(season,token,previous)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf8')
    print('football-data.org secondary audit:',json.dumps({
      'status':report['status'],
      'leagues':{k:{x:y for x,y in v.items()
          if x in ('status','matched_fixtures','agreed_scores','disagreements','local_score_missing')}
          for k,v in report['leagues'].items()}},ensure_ascii=False),flush=True)

if __name__=='__main__':
    main()
