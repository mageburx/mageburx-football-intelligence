#!/usr/bin/env python3
"""Conservative five-league data-quality audit; read only, no score changes.

Reports what is observed and independently verified, NOT model accuracy.
The existing collectors already perform bounded source refreshes. This audit
builds actionable priorities and never fills missing scores or moves signed IDs.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import re
import unicodedata
from collections import Counter,defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
LIDS=('pt','dk','nl','dk2','no')
LABELS={'pt':'Liga Portugal','dk':'Superliga','nl':'Eredivisie',
        'dk2':'1. Division','no':'Eliteserien'}
# League-format reference only. Denmark's championship stage has variable
# fixture structure; the 1. Division may have split-stage changes.
REF={'pt':(34,9,306),'dk':(32,None,None),'nl':(34,9,306),
     'dk2':(32,6,None),'no':(30,8,240)}
HIST_YEARS=tuple(f'{y}-{y+1}' for y in range(2021,2026))

def normalize(value):
    value=unicodedata.normalize('NFKD',str(value or ''))
    value=''.join(c for c in value if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+',' ',value.casefold()).strip()

def confirmed(e):
    return (e.get('finished') is True and e.get('result_verified') is True
            and str(e.get('match_status') or '').upper() in
            ('FT','AET','PEN','FINISHED','FULL TIME','MATCH FINISHED','FULLTIME','AFTER EXTRA TIME','AFTER PENALTIES')
            and type(e.get('home_score')) is int and type(e.get('away_score')) is int
            and 0<=e['home_score']<100 and 0<=e['away_score']<100)

def historical(lid,history,nl_history):
    if lid=='nl':
        seasons=nl_history.get('seasons',{})
        source='OpenFootball CC0'
    else:
        seasons=history.get('leagues',{}).get(lid,{}).get('seasons',{})
        source='Historico verificado no projeto' if lid in ('pt','dk') else 'Sem arquivo historico validado'
    rows=[]
    for year in HIST_YEARS:
        record=seasons.get(year)
        if not isinstance(record,dict):
            rows.append({'season':year,'status':'not_observed','completed_matches':None,'expected':None})
            continue
        events=record.get('events',[])
        n=len(events) if isinstance(events,list) else 0
        expected=record.get('expected_games')
        good=(type(expected) is int and expected>0 and n==expected and
              record.get('complete') is True)
        rows.append({'season':year,'status':'source_complete' if good else 'incomplete',
                     'completed_matches':n,'expected':expected})
    return {'source':source,'complete_seasons':sum(x['status']=='source_complete' for x in rows),
            'required_seasons':len(HIST_YEARS),'seasons':rows}

def sample_stats(lid,meta,shots):
    entry=meta.get('leagues',{}).get(lid,{})
    shot=shots.get('leagues',{}).get(lid,{})
    checked=int(entry.get('sample_checked') or 0)
    field_counts={k:int(v) for k,v in entry.get('stats_fields_validated',{}).items()
                  if isinstance(v,int) and not isinstance(v,bool)}
    result={'status':'not_checked' if not checked else 'small_sample_only',
            'sample_checked':checked,'source_catalog_matches':int(entry.get('match_count') or 0),
            'verified_fields_in_sample':field_counts,
            'research_shots_recorded':int(shot.get('shots_recorded') or 0),
            'research_xg_recorded':int(shot.get('xg_recorded') or 0),
            'source_status':entry.get('status','not_checked'),
            'not_certified':'Samples do not establish full-season coverage or legal reuse rights.'}
    return result

def build(season,history,nl_history,stats,shots,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:raise ValueError('UTC-aware timestamp required')
    if season.get('schema')!=1 or 'leagues' not in season:raise ValueError('Invalid season snapshot')
    report={'schema':1,'generated_at':now.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat(),
            'source_updated_at':season.get('updated_at'),
            'production_model_changed':False,
            'policy':'Audit only. No guessed scores, no automatic fixture relinking, no unlicensed bulk scraping.',
            'leagues':{},'queue':[]}
    day=now.date().isoformat()
    for lid in LIDS:
        lg=season['leagues'].get(lid)
        if not isinstance(lg,dict):
            raise ValueError('Missing required league '+lid)
        rounds,per_round,reference=REF[lid]
        events=lg.get('events',[])
        if not isinstance(events,list):raise ValueError('Invalid fixture list: '+lid)
        known={str(e.get('id')):e for e in events if isinstance(e,dict) and e.get('id')}
        duplicates=len(events)-len(known)
        seen=defaultdict(list)
        for e in known.values():
            pair=(str(e.get('date')),normalize(e.get('home')),normalize(e.get('away')))
            if not pair[1] or not pair[2]:continue
            seen[pair].append(str(e['id']))
        duplicate_pairs=[{'date':date,'home':home,'away':away,'ids':ids[:4]}
                         for (date,home,away),ids in seen.items() if len(ids)>1]
        confirmed_count=sum(confirmed(e) for e in known.values())
        source_counts=Counter(str(e.get('result_source') or 'TheSportsDB original round/season')
                              for e in known.values() if confirmed(e))
        pending_research=sum(e.get('finished') is True and e.get('result_verified') is not True and
                              str(e.get('id') or '').startswith('fantasy-no:')
                              for e in known.values())
        past=[e for e in known.values() if str(e.get('date') or '')<day]
        past_not_final=[e for e in past if not confirmed(e)]
        current=lg.get('collection',{})
        checked=set(n for n in current.get('verified_rounds',[]) if type(n) is int and 1<=n<=rounds)
        # PT/DK collector does not retain an audit of previously checked rounds.
        # Count current fixture inventory only; rounds_ok from one run is NOT
        # enough to certify all rounds of the season.
        if lid in ('pt','dk'):
            round_mode='not_persisted'
            verified_rounds=None
            unverified_rounds=None
        else:
            round_mode='source_checked_subset'
            verified_rounds=len(checked)
            unverified_rounds=[r for r in range(1,rounds+1) if r not in checked]
        history_report=historical(lid,history,nl_history)
        observed=len(known)
        source_flags={}
        if lid=='nl':
            meta=lg.get('openfootball',{})
            source_flags={'source':'OpenFootball','conflicts':int(meta.get('conflicts') or 0),
                          'source_fixture_count':meta.get('source_fixture_count'),
                          'superseded_signed_ids_preserved':len(meta.get('superseded',[]))}
        elif lid=='dk2':
            meta=lg.get('dbu_official',{})
            source_flags={'source':'DBU','status':meta.get('status','not_checked'),
                          'conflicts':int(meta.get('conflicts') or 0),
                          'unrecognized_clubs':int(meta.get('unrecognized_clubs') or 0),
                          'source_error':meta.get('error')}
        elif lid=='no':
            meta=lg.get('fantasy_research',{})
            source_flags={'source':'TopMarx research export','status':meta.get('status','not_checked'),
                          'conflicts':int(meta.get('conflicts') or 0),
                          'source_matches':meta.get('source_matches'),
                          'rights':meta.get('rights')}
        else:
            source_flags={'source':'TheSportsDB','status':'observed'}
        missing_reference=max(0,reference-observed) if reference is not None else None
        stats_report=sample_stats(lid,stats,shots)
        issues=[]
        def issue(code,count,priority,meaning):
            if count:
                issues.append({'code':code,'count':count,'priority':priority,'meaning':meaning})
        issue('duplicate_identifiers',duplicates,'critical','Same ID repeated; review before reusing results')
        issue('potential_duplicate_fixtures',len(duplicate_pairs),'high','Distinct IDs with same date and teams; audit without merging')
        issue('source_result_conflicts',source_flags.get('conflicts',0),'critical','Sources disagree; do not overwrite scores')
        issue('past_not_final',len(past_not_final),'high','Past fixture lacks a verified final score')
        issue('unverified_rounds',len(unverified_rounds or []),'high','Rounds not confirmed by the primary season feed')
        issue('history_incomplete',len(HIST_YEARS)-history_report['complete_seasons'],'high','Historical season lacks complete verified coverage')
        issue('missing_reference_inventory',missing_reference or 0,'medium','Below format reference; some future fixtures may be unpublished')
        issue('shots_no_verified_sample',int(stats_report['sample_checked']==0),'medium','No independent match-stat sample checked')
        if reference is not None and observed>reference:
            inventory='reference_exceeded_requires_review'
        elif reference is not None and observed==reference:
            inventory=('reference_count_reached_with_conflicts' if duplicate_pairs or duplicates
                       else 'reference_count_reached_not_verified_complete')
        elif reference is None:
            inventory='format_variable_count_not_certified'
        else:
            inventory='below_reference_count'
        if source_flags.get('conflicts',0)>0 or duplicates:
            quality='requires_review'
        elif duplicate_pairs or past_not_final or (unverified_rounds is not None and len(unverified_rounds)>0):
            quality='partial'
        elif history_report['complete_seasons']<5 or stats_report['sample_checked']<2 or lg.get('partial'):
            quality='partial'
        else:
            quality='audit_indicators_ok_not_certified'
        report['leagues'][lid]={
            'name':LABELS[lid],'season':lg.get('source_season',season.get('season')),
            'status':quality,'source_declares_partial':bool(lg.get('partial',True)),
            'inventory':{'observed_unique':observed,'expected_reference':reference,
                         'difference_reference':missing_reference,'status':inventory,
                         'verified_final':confirmed_count,'past_unverified':len(past_not_final),
                         'past_unverified_sample':[{
                            'id':e.get('id'),'date':e.get('date'),'home':e.get('home'),'away':e.get('away')}
                            for e in sorted(past_not_final,key=lambda e:e.get('date',''))[:12]],
                         'duplicate_ids':duplicates,'potential_duplicate_pairs':duplicate_pairs[:12]},
            'rounds':{'total_reference':rounds,'verification':round_mode,
                      'verified':verified_rounds,'unverified':unverified_rounds,
                      'unverified_count':len(unverified_rounds) if unverified_rounds is not None else None},
            'history':history_report,'stats':stats_report,
            'result_evidence':{
                'confirmed_total':confirmed_count,
                'confirmed_by_source':dict(source_counts),
                'unverified_research_only':pending_research,
                'exact_id_provider_checks':int(lg.get('result_recovery',{}).get('checked',0) or 0),
                'exact_id_provider_newly_verified':int(lg.get('result_recovery',{}).get('verified',0) or 0),
                'official_or_cc0_evidence_refresh':bool(
                    lg.get('openfootball',{}).get('result_evidence_v1') or
                    lg.get('dbu_official',{}).get('result_evidence_v1')),
            },
            'sources':source_flags,'issues':issues
        }
        for x in issues:
            if x['code'] in ('unverified_rounds','past_not_final','history_incomplete',
                             'source_result_conflicts','potential_duplicate_fixtures'):
                report['queue'].append({'league':lid,'priority':x['priority'],
                                        'code':x['code'],'count':x['count'],
                                        'action':{
                                          'unverified_rounds':'Recheck missing round via existing rate-limited season collector',
                                          'past_not_final':'Check explicit FT/AET/PEN from provider; never infer final from numeric score',
                                          'history_incomplete':'Verify archival season count against source, not reconstructed odds',
                                          'source_result_conflicts':'Manual source comparison; quarantine disagreements',
                                          'potential_duplicate_fixtures':'Compare same oriented tie without transferring signed IDs'
                                        }[x['code']]})
    report['queue'].sort(key=lambda x:({'critical':0,'high':1,'medium':2}.get(x['priority'],3),-x['count'],x['league']))
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--season',type=Path,default=ROOT/'data'/'season.json')
    p.add_argument('--history',type=Path,default=ROOT/'data'/'history.json')
    p.add_argument('--nl-history',type=Path,default=ROOT/'data'/'nl_history.json')
    p.add_argument('--stats',type=Path,default=ROOT/'data'/'stats_coverage.json')
    p.add_argument('--shots',type=Path,default=ROOT/'data'/'shots_research.json')
    p.add_argument('--output',type=Path,default=ROOT/'data'/'data_coverage.json')
    args=p.parse_args()
    read=lambda x:json.loads(x.read_text(encoding='utf-8')) if x.is_file() else {}
    result=build(read(args.season),read(args.history),read(args.nl_history),
                 read(args.stats),read(args.shots))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    print('Data Coverage Engine',json.dumps({
        'leagues':{lid:{'status':v['status'],'observed':v['inventory']['observed_unique'],
          'past_unverified':v['inventory']['past_unverified'],
          'history_complete':v['history']['complete_seasons'],
          'source_conflicts':v['sources'].get('conflicts',0)}
                   for lid,v in result['leagues'].items()},
        'queued_checks':len(result['queue'])},ensure_ascii=False))

if __name__=='__main__':
    main()
