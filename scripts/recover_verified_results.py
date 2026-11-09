#!/usr/bin/env python3
"""Bounded original-ID full-time confirmation from TheSportsDB.

No cross-provider ID matching, no score guesses, no edits to signed forecasts.
Official / CC0 data is handled by its existing limited collector. Fantasy-NO
research scores are never promoted without an independent exact-ID final.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

try:
    from scripts.collect_expanded_leagues import LEAGUES,parse_event,RateLimit
    from scripts.build_data_coverage import normalize
except ModuleNotFoundError:
    from collect_expanded_leagues import LEAGUES,parse_event,RateLimit
    from build_data_coverage import normalize

ROOT=Path(__file__).resolve().parents[1]
FILE=ROOT/'data'/'season.json'
API='https://www.thesportsdb.com/api/v1/json/123/lookupevent.php'
AGENT='MageburxFootballResearch/7.0 (small bounded result verification)'
QUOTAS={'pt':1,'dk':1,'no':2,'nl':1,'dk2':1}
COOLDOWN_HOURS=22

def fetch_event(event_id):
    if not str(event_id).isdigit() or not 5<=len(str(event_id))<=10:
        raise ValueError('Only original numeric TheSportsDB IDs may be checked')
    url=API+'?'+urllib.parse.urlencode({'id':str(event_id)})
    request=urllib.request.Request(url,headers={'User-Agent':AGENT,'Accept':'application/json'})
    try:
        with urllib.request.urlopen(request,timeout=14) as response:
            if response.status!=200:raise RuntimeError('Unexpected sports API HTTP status')
            data=json.loads(response.read(280_000))
    except urllib.error.HTTPError as error:
        if error.code==429:raise RateLimit('Provider returned HTTP 429') from error
        raise
    if not isinstance(data,dict) or data.get('events') is not None and not isinstance(data['events'],list):
        raise ValueError('Unexpected source event format')
    return data.get('events') or []

def eligible(e,now):
    eid=str(e.get('id') or '')
    if not (eid.isdigit() and 5<=len(eid)<=10):return False
    if not e.get('date') or e['date']>=now.date().isoformat():return False
    if str(e.get('match_status') or '').upper() in (
        'PST','POSTPONED','CANC','CANCELLED','ABD','ABANDONED'):
        return False
    dispute=e.get('result_dispute') or {}
    eligible_dispute=(e.get('score_conflict') is True and
        dispute.get('status')=='pending_independent_confirmation' and
        dispute.get('official_source')=='DBU official fixture table')
    if e.get('result_verified') is True or (e.get('score_conflict') is True and not eligible_dispute):
        return False
    last=e.get('verification_checked_at')
    if last:
        try:
            stamp=dt.datetime.fromisoformat(last.replace('Z','+00:00'))
            if stamp.tzinfo and (now-stamp).total_seconds()<COOLDOWN_HOURS*3600:return False
        except (TypeError,ValueError):pass
    return True

def verify_one(event,lid,raw,now):
    """Returns a reason and mutates only this same original-ID event."""
    if not isinstance(raw,dict) or str(raw.get('idEvent'))!=str(event.get('id')):
        return 'missing_exact_id'
    parsed=parse_event(raw,lid,now.date())
    if parsed is None:return 'invalid_source_fixture'
    if (parsed.get('id')!=str(event['id']) or
        parsed.get('date')!=event.get('date') or
        normalize(parsed.get('home'))!=normalize(event.get('home')) or
        normalize(parsed.get('away'))!=normalize(event.get('away'))):
        return 'fixture_identity_conflict'
    if not parsed.get('result_verified'):
        return 'no_explicit_full_time'
    original=(event.get('home_score'),event.get('away_score'))
    updated=(parsed.get('home_score'),parsed.get('away_score'))
    if event.get('score_conflict') is True:
        dispute=event.get('result_dispute') or {}
        official=dispute.get('official_score')
        stored=dispute.get('stored_score')
        if (lid!='dk2' or dispute.get('status')!='pending_independent_confirmation'
                or dispute.get('official_source')!='DBU official fixture table'
                or not isinstance(official,list) or not isinstance(stored,list)
                or len(official)!=2 or len(stored)!=2 or
                tuple(stored)!=original):
            return 'score_conflict'
        if tuple(official)!=updated:
            return 'source_disagreement'
        # Two independent sources agree on the same oriented fixture and
        # exact original provider ID: retain the old score for audit.
        event['result_dispute']={**dispute,'status':'resolved_two_source_agreement',
                                 'provider_score':list(updated),
                                 'provider_id':str(event['id']),
                                 'resolved_at':now.replace(microsecond=0).isoformat()}
        event['score_conflict']=False
        event.update({'finished':True,'home_score':updated[0],'away_score':updated[1],
                      'result_verified':True,'match_status':parsed['match_status'],
                      'result_source':'DBU official + TheSportsDB exact original ID',
                      'result_verified_at':now.replace(microsecond=0).isoformat()})
        return 'verified_two_source'
    if event.get('finished') is True and original!=updated:
        event['score_conflict']=True
        event['result_verified']=False
        event['result_dispute']={'original_score':list(original),
                                 'provider_score':list(updated),
                                 'provider':'TheSportsDB','checked_at':now.replace(microsecond=0).isoformat()}
        return 'score_conflict'
    if event.get('score_conflict'):return 'score_conflict'
    # No substitution of match_id, date, fixture identity, or pre-match forecasts.
    event.update({'finished':True,'home_score':updated[0],'away_score':updated[1],
                  'result_verified':True,'match_status':parsed['match_status'],
                  'result_source':'TheSportsDB exact original event ID',
                  'result_verified_at':now.replace(microsecond=0).isoformat()})
    return 'verified'

def recover(season,fetcher=fetch_event,now=None,quotas=QUOTAS,priority_keys=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:raise ValueError('Timezone-aware timestamp required')
    now=now.astimezone(dt.timezone.utc)
    if season.get('schema')!=1 or not all(lid in season.get('leagues',{}) for lid in quotas):
        raise ValueError('The five-league season snapshot has not been initialized')
    report={'checked_at':now.replace(microsecond=0).isoformat(),
            'source':'TheSportsDB lookupevent.php (free)',
            'max_requests':sum(quotas.values()),'requests':0,'verified':0,
            'resolved_disputes':0,'conflicts':0,'rate_limited':False,'leagues':{}}
    stop=False
    priority_keys=set(priority_keys or ())
    def rank(e,lid):
        key=f'{lid}:{season.get("season","unknown")}:{e["id"]}'
        # Official disputes first, then signed unsettled forecasts.
        # Remaining original IDs are rotated: previously unchecked first.
        return (not bool(e.get('score_conflict')),
                key not in priority_keys,
                bool(e.get('verification_checked_at')),
                not bool(e.get('finished')),
                -int(str(e.get('date') or '0000-00-00').replace('-','') or 0),
                str(e.get('id')))
    for lid,quota in quotas.items():
        league=season['leagues'][lid]
        candidates=sorted((e for e in league.get('events',[])
            if isinstance(e,dict) and eligible(e,now)),
            key=lambda x:rank(x,lid))
        result={'candidates':len(candidates),'checked':0,'verified':0,
                'resolved_disputes':0,'no_final':0,'conflicts':0,'source_errors':0,
                'not_found':0,'identity_errors':0,'unverified_research_results':0}
        for e in candidates[:min(max(0,int(quota)),8)]:
            if stop:break
            report['requests']+=1
            result['checked']+=1
            e['verification_checked_at']=now.replace(microsecond=0).isoformat()
            try:
                items=fetcher(e['id'])
                if len(items)!=1:
                    outcome='missing_exact_id'
                else:
                    outcome=verify_one(e,lid,items[0],now)
            except RateLimit:
                report['rate_limited']=True
                stop=True
                outcome='source_error'
            except (OSError,RuntimeError,TimeoutError,ValueError,TypeError,
                    urllib.error.URLError,json.JSONDecodeError):
                outcome='source_error'
            e['verification_last_status']=outcome
            if outcome in ('verified','verified_two_source'):
                result['verified']+=1;report['verified']+=1
                if outcome=='verified_two_source':
                    result['resolved_disputes']+=1;report['resolved_disputes']+=1
            elif outcome=='no_explicit_full_time':result['no_final']+=1
            elif outcome in ('score_conflict','source_disagreement'):
                result['conflicts']+=1;report['conflicts']+=1
            elif outcome=='missing_exact_id':result['not_found']+=1
            elif outcome=='fixture_identity_conflict':result['identity_errors']+=1
            else:result['source_errors']+=1
        # Research-only results can still be visible, but are never reported
        # as confirmed without original-ID official/API FT evidence.
        result['unverified_research_results']=sum(
            e.get('finished') is True and e.get('result_verified') is not True
            and str(e.get('id','')).startswith('fantasy-no:')
            for e in league.get('events',[]))
        league['result_recovery']={**report['leagues'].get(lid,{}),
                                  'checked_at':now.replace(microsecond=0).isoformat(),
                                  'source':report['source'],**result}
        report['leagues'][lid]=result
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--season',type=Path,default=FILE)
    p.add_argument('--max-requests',type=int,default=6)
    p.add_argument('--signed-ledger',type=Path,
                   default=ROOT/'data'/'expansion_1x2_ledger.json')
    args=p.parse_args()
    doc=json.loads(args.season.read_text(encoding='utf8'))
    quotas={lid:val for lid,val in QUOTAS.items()}
    if args.max_requests<6:
        remaining=max(0,args.max_requests)
        quotas={lid:min(limit,max(0,remaining-sum(quotas[x] for x in list(quotas)[:i])))
                for i,(lid,limit) in enumerate(QUOTAS.items())}
    keys=set()
    if args.signed_ledger.exists():
        signed=json.loads(args.signed_ledger.read_text(encoding='utf8'))
        settled={x.get('key') for x in signed.get('settlements',[])}
        keys={str(x['key']) for x in signed.get('predictions',[])
              if x.get('key') and x['key'] not in settled}
    result=recover(doc,quotas=quotas,priority_keys=keys)
    args.season.write_text(json.dumps(doc,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf8')
    print('Result verification',json.dumps(result,ensure_ascii=False),flush=True)

if __name__=='__main__':
    main()
