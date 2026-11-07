#!/usr/bin/env python3
"""Licensed CC0 Dutch league archive + safe complementary current-season feed.

TheSportsDB free season endpoint only returns 15 records. OpenFootball provides
more historical Dutch fixtures under CC0. Preserve original identifiers where
possible; never inject today's scores or overwrite contradictory scores.
The archive is *not* added to current-season model training: separate holdout
tests use completed years and prohibit temporal leakage.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SEASON_FILE=ROOT/'data'/'season.json'
ARCHIVE_FILE=ROOT/'data'/'nl_history.json'
BASE='https://raw.githubusercontent.com/openfootball/football.json/master/'
SEASONS=('2021-22','2022-23','2023-24','2024-25','2025-26')
CURRENT='2026-27'
NAME_MAP={
    'sc cambuur leeuwarden':'Cambuur','sbv excelsior':'Excelsior',
    'nec':'NEC Nijmegen','telstar 1963':'Telstar',
    'willem ii tilburg':'Willem II','psv':'PSV Eindhoven',
    'az':'AZ Alkmaar','feyenoord rotterdam':'Feyenoord',
    'fc groningen':'Groningen','fc utrecht':'Utrecht',
    'afc ajax':'Ajax','sc heerenveen':'Heerenveen',
    'fc twente 65':'Twente',
}
EXPECTED=306


def canonical(name):
    value=unicodedata.normalize('NFKD',str(name or ''))
    value=''.join(c for c in value if not unicodedata.combining(c))
    return re.sub(r'\s+',' ',re.sub(r'[^a-z0-9]+',' ',value.casefold())).strip()


def club(name):
    return NAME_MAP.get(canonical(name),str(name).strip())


def key(event):
    return (event.get('date'),canonical(club(event.get('home'))),
            canonical(club(event.get('away'))))


def get_json(path):
    if path not in [f'{v}/nl.1.json' for v in (*SEASONS,CURRENT)]:
        raise ValueError('Unexpected archive filename')
    req=urllib.request.Request(BASE+path,headers={
        'User-Agent':'MageburxFootballResearch/6.2 (public CC0 archival files)',
        'Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=22) as resp:
        if resp.status!=200:raise RuntimeError(f'HTTP {resp.status}')
        return json.loads(resp.read(500_000))


def score_pair(match):
    ft=match.get('score')
    if isinstance(ft,dict):ft=ft.get('ft')
    if not isinstance(ft,list) or len(ft)!=2:return (None,None)
    if any(type(x) is not int or not 0<=x<=25 for x in ft):
        return (None,None)
    return tuple(ft)


def parsed(raw,season,now):
    if not isinstance(raw,dict) or 'Eredivisie' not in str(raw.get('name','')):
        raise ValueError('Wrong league in public archive')
    results=[]
    for idx,e in enumerate(raw.get('matches',[])):
        if not isinstance(e,dict):continue
        date=str(e.get('date',''))[:10]
        try:
            dateobj=dt.date.fromisoformat(date)
            if dateobj.year not in (int(season[:4]),int(season[:4])+1):
                continue
        except (ValueError,TypeError):continue
        home,away=club(e.get('team1')),club(e.get('team2'))
        if not home or not away or home==away:continue
        rnd=e.get('round','')
        try:
            rn=int(str(rnd).rsplit(' ',1)[-1])
        except (TypeError,ValueError):rn=0
        h,a=score_pair(e)
        finished=h is not None and dateobj<now.date()
        # Only explicit source FT, not a numeric score or half-time score,
        # is eligible as independent final-result evidence.
        explicit_ft=(finished and isinstance(e.get('score'),dict)
                     and isinstance(e['score'].get('ft'),list)
                     and len(e['score']['ft'])==2)
        item={'id':f'ofnl:{season}:{date}:{canonical(home)}:{canonical(away)}',
              'date':date,'utc':'','round':rn,
              'home':home,'away':away,
              'home_score':h if finished else None,
              'away_score':a if finished else None,
              'finished':finished,
              'result_verified':bool(explicit_ft),
              'match_status':'FT' if explicit_ft else '',
              'result_source':'OpenFootball CC0 explicit FT' if explicit_ft else None}
        results.append(item)
    unique={}
    for e in results:
        k=key(e)
        if k in unique:
            # Do not certify a season with duplicate dated fixtures.
            raise ValueError('Duplicated fixture in OpenFootball: '+str(k))
        unique[k]=e
    return results


def merge_current(saved,additional):
    existing={key(e):e for e in saved if isinstance(e,dict) and e.get('id')}
    added=conflicts=updated=0
    for event in additional:
        k=key(event)
        prior=existing.get(k)
        if prior is None:
            # The archive uses provisional Saturday dates where TheSportsDB
            # can have a confirmed Sunday fixture. Do not create a second
            # fixture or transfer a score solely from equal team names.
            peers=[x for x in saved if
                   (canonical(club(x.get('home'))),canonical(club(x.get('away'))))==
                   (k[1],k[2])]
            if len(peers)==1 and peers[0].get('date')!=event.get('date'):
                continue
        if prior is not None:
            if prior.get('finished') and event.get('finished'):
                if (prior['home_score'],prior['away_score'])!=(
                    event['home_score'],event['away_score']):
                    # Never silently certify two disagreeing score sources.
                    prior['score_conflict']=True
                    prior['result_verified']=False
                    conflicts+=1
                    continue
                if event.get('result_verified') is True and not prior.get('score_conflict'):
                    prior.update({'result_verified':True,'match_status':'FT',
                                  'result_source':'OpenFootball CC0 matching existing score'})
            if event.get('finished') and not prior.get('finished'):
                # No borrowing a score from a different ID merely because
                # date and oriented teams match; require identical source ID.
                if prior.get('id')==event.get('id'):
                    prior.update({'home_score':event['home_score'],
                                  'away_score':event['away_score'],'finished':True,
                                  'result_verified':event.get('result_verified') is True,
                                  'match_status':event.get('match_status',''),
                                  'result_source':event.get('result_source')})
                    updated+=1
            continue
        saved.append(event)
        existing[k]=event
        added+=1
    return added,updated,conflicts



def reconcile_rescheduled_fixtures(events):
    """Drop only duplicate *unplayed* source fixtures for the same oriented tie.

    A domestic double round-robin has at most one home-to-away pairing.
    Keep the primary source identity if present, and log superseded IDs so
    already-issued predictions stay traceable but cannot settle accidentally.
    Finished games never get removed, even on conflict.
    """
    buckets={}
    for event in events:
        if not isinstance(event,dict):continue
        identity=(canonical(club(event.get('home'))),
                  canonical(club(event.get('away'))))
        if not all(identity):continue
        buckets.setdefault(identity,[]).append(event)
    superseded=[]
    keep_ids=set()
    for identity,group in buckets.items():
        if len(group)==1:
            keep_ids.add(group[0]['id'])
            continue
        if any(e.get('finished') is True for e in group):
            # A real final score is authoritative. A future entry can be a
            # stale schedule snapshot and may be safely dropped; however
            # multiple completed home/away games are left for manual review.
            completed=[e for e in group if e.get('finished') is True]
            if len(completed)>1:
                keep_ids.update(e['id'] for e in group)
                continue
            chosen=completed[0]
        else:
            # Prefer a fixture with original API identity to synthetic OpenFootball
            # IDs, regardless of its planned date (reschedules can move months).
            chosen=min(group,key=lambda e:(
                str(e.get('id','')).startswith('ofnl:'),
                not bool(e.get('utc')),
                str(e.get('id',''))))
        keep_ids.add(chosen['id'])
        for e in group:
            if e['id']!=chosen['id'] and e.get('finished') is not True:
                superseded.append({
                    'id':e['id'],'replacement_id':chosen['id'],
                    'old_date':e.get('date'),'replacement_date':chosen.get('date'),
                    'home':e.get('home'),'away':e.get('away'),
                    'reason':'duplicate_or_rescheduled_future_fixture',
                })
    return [e for e in events if e.get('id') in keep_ids],superseded


def collect(season_path=SEASON_FILE,archive_path=ARCHIVE_FILE,fetcher=get_json,now=None,
            min_hours=22):
    now=now or dt.datetime.now(dt.timezone.utc)
    doc=json.loads(season_path.read_text(encoding='utf8'))
    if doc.get('schema')!=1 or not isinstance(doc.get('leagues',{}).get('nl'),dict):
        raise ValueError('Dutch season must be initialized before OpenFootball backfill')
    archive=json.loads(archive_path.read_text(encoding='utf8')) if archive_path.exists() else {
        'schema':1,'source':{'name':'OpenFootball football.json',
            'url':'https://github.com/openfootball/football.json',
            'license':'CC0-1.0'},'seasons':{},'last_attempt_at':None,
        'status':'not_started','errors':[]}
    prev=archive.get('last_attempt_at')
    recheck_only=False
    current=doc['leagues']['nl']
    evidence=current.get('openfootball',{})
    prior_attempt=evidence.get('result_evidence_attempted_at')
    if prev:
        try:
            if (now-dt.datetime.fromisoformat(prev)).total_seconds()<min_hours*3600:
                # One bounded source refresh on upgrade only, after 22h on errors.
                upgrade=(evidence.get('result_evidence_v1') is not True and
                         (not prior_attempt or
                          (now-dt.datetime.fromisoformat(prior_attempt)).total_seconds()>=min_hours*3600))
                if upgrade:
                    recheck_only=True
                else:
                    # Even without a new HTTP fetch, reconcile newly restored
                # or primary-source duplicated future fixtures every run.
                current=doc['leagues']['nl']
                current['events'],superseded=reconcile_rescheduled_fixtures(
                    current.get('events',[]))
                if superseded:
                    details=current.setdefault('openfootball',{})
                    by_id={x['id']:x for x in details.get('superseded',[])+superseded}
                    details['superseded']=list(by_id.values())
                    details['newly_reconciled']=len(superseded)
                    season_path.write_text(json.dumps(doc,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf8')
                    return doc,archive
        except (ValueError,TypeError):pass
    archive['last_attempt_at']=now.replace(microsecond=0).isoformat()
    if recheck_only:
        current.setdefault('openfootball',{})['result_evidence_attempted_at']=now.replace(microsecond=0).isoformat()
    errors=[]
    for year in ((CURRENT,) if recheck_only else (*SEASONS,CURRENT)):
        try:
            value=fetcher(f'{year}/nl.1.json')
            records=parsed(value,year,now)
            if year==CURRENT:
                current=doc['leagues']['nl']
                n,u,c=merge_current(current['events'],records)
                current['events'],superseded=reconcile_rescheduled_fixtures(
                    current['events'])
                current['events'].sort(key=lambda x:(x['date'],x['id']))
                prior_superseded=current.get('openfootball',{}).get('superseded',[])
                superseded_by_id={x['id']:x for x in prior_superseded+superseded
                                  if x.get('id')}
                current['openfootball']={
                    'source':'OpenFootball football.json CC0-1.0',
                    'result_evidence_v1':True,
                    'result_evidence_attempted_at':now.replace(microsecond=0).isoformat(),
                    'updated_at':now.replace(microsecond=0).isoformat(),
                    'added':n,'results_confirmed':u,'conflicts':c,
                    'source_fixture_count':len(records),
                    'superseded':list(superseded_by_id.values()),
                    'newly_reconciled':len(superseded)}
                if c:errors.append(f'{year}: {c} conflicting results')
                continue
            actual=[m for m in records if m['finished']]
            teams={m['home'] for m in actual}|{m['away'] for m in actual}
            complete=(len(actual)==EXPECTED and len(teams)==18 and
                      all(sum(t in (e['home'],e['away']) for e in actual)==34 for t in teams))
            # Archive only verifiable results; incomplete scores never treated as finished.
            archive['seasons'][f'{year[:4]}-{int(year[:4])+1}']={
                'events':actual,'actual_games':len(actual),
                'expected_games':EXPECTED,'complete':complete,
                'verified_from':'OpenFootball football.json (CC0-1.0)',
                'fetched_at':now.replace(microsecond=0).isoformat()}
        except (OSError,RuntimeError,ValueError,json.JSONDecodeError) as exc:
            errors.append(f'{year}: {str(exc)[:120]}')
    archive['status']='partial' if errors else 'sample_available'
    archive['errors']=errors[:12]
    season_path.write_text(json.dumps(doc,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf8')
    archive_path.parent.mkdir(parents=True,exist_ok=True)
    archive_path.write_text(json.dumps(archive,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf8')
    print('OpenFootball NL CC0',json.dumps({'current':len(doc['leagues']['nl']['events']),
        'completed':sum(e.get('finished') is True for e in doc['leagues']['nl']['events']),
        'seasons':{k:{'n':v['actual_games'],'complete':v['complete']}
                   for k,v in archive['seasons'].items()},'errors':errors},ensure_ascii=False))
    return doc,archive


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--season',type=Path,default=SEASON_FILE)
    p.add_argument('--archive',type=Path,default=ARCHIVE_FILE)
    args=p.parse_args()
    collect(args.season,args.archive)
