#!/usr/bin/env python3
"""Descriptive 1X2 scoreboard for all five competitions.

Only metrics from the independently audited, signed, prospectively issued
predictions are used. Never mix reconstructed historical simulations with
actual predictions or infer betting profitability from a forecast score.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
LEAGUE_NAMES={
    'pt':'Liga Portugal',
    'dk':'Superliga dinamarquesa',
    'nl':'Eredivisie',
    'dk2':'1. Division dinamarquesa',
    'no':'Eliteserien',
}
MIN_OBSERVATIONS=100


def build(audit,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    if not isinstance(audit,dict) or audit.get('schema')!=1:
        raise ValueError('Expected a signed 1X2 audit with schema 1')
    source=audit.get('leagues',{})
    if not isinstance(source,dict) or not all(lid in source for lid in LEAGUE_NAMES):
        raise ValueError('1X2 audit does not contain every league; cannot compare')
    leagues={}
    for lid,name in LEAGUE_NAMES.items():
        a=source[lid]
        issued=int(a.get('issued',0))
        settled=int(a.get('settled',0))
        valid=int(a.get('settled_valid',0))
        invalid=int(a.get('invalid',0))
        if min(issued,settled,valid,invalid)<0 or valid>settled or settled>issued:
            raise ValueError('Contradictory prospective settlement counters: '+lid)
        brier=a.get('brier') if valid else None
        loss=a.get('log_loss') if valid else None
        if valid and (type(brier) not in (int,float) or not math.isfinite(brier)
                      or type(loss) not in (int,float) or not math.isfinite(loss)
                      or not (0<=brier<=2) or loss<0):
            raise ValueError('Missing audited 1X2 error metrics: '+lid)
        ci=a.get('brier_ci95') if valid>=30 else None
        if ci is not None and (not isinstance(ci,list) or len(ci)!=2
                               or any(type(z) not in (int,float) or not 0<=z<=2 for z in ci)
                               or ci[0]>ci[1]):
            raise ValueError('Invalid approximate confidence interval: '+lid)
        superseded=int(a.get('superseded',0))
        if not 0<=superseded<=issued:
            raise ValueError('Contradictory superseded-ID count: '+lid)
        needs_review=sum(int(a.get(field,0)) for field in
                         ('invalid','rescheduled','fixture_missing','superseded','past_due'))
        leagues[lid]={
            'name':name,'issued':issued,'settled':settled,
            'valid_settled':valid,
            'pending':issued-settled,
            'active_ids':issued-superseded,
            'superseded_signed_ids':superseded,
            'excluded_or_flagged':invalid,
            'past_due':int(a.get('past_due',0)),
            'rescheduled':int(a.get('rescheduled',0)),
            'superseded':int(a.get('superseded',0)),
            'fixture_missing':int(a.get('fixture_missing',0)),
            'audit_status':a.get('status','unknown'),
            'brier':round(brier,5) if valid else None,
            'log_loss':round(loss,5) if valid else None,
            'brier_ci95':ci if valid>=30 else None,
            'progress_to_100':min(valid,MIN_OBSERVATIONS),
            'minimum_sample':MIN_OBSERVATIONS,
            'sample_status':('awaiting_first_valid_result' if valid==0 else
                             'preliminary_only' if valid<MIN_OBSERVATIONS else
                             'sufficient_for_descriptive_review'),
            'quality_warning':needs_review>0,
        }
    all_ready=all(x['valid_settled']>=MIN_OBSERVATIONS and
                  not x['quality_warning'] for x in leagues.values())
    return {
        'schema':1,
        'generated_at':now.replace(microsecond=0).isoformat(),
        'method':'Forward-signed 1X2 results, audited for issuance time, hash, fixture identity and final-score integrity',
        'ranking_status':('descriptive_only_not_a_financial_ranking' if all_ready else
                          'not_rankable_insufficient_or_nonuniform_evidence'),
        'totals':{'issued':sum(x['issued'] for x in leagues.values()),
                  'active_ids':sum(x['active_ids'] for x in leagues.values()),
                  'superseded_signed_ids':sum(x['superseded_signed_ids'] for x in leagues.values()),
                  'settled_valid':sum(x['valid_settled'] for x in leagues.values()),
                  'leagues_with_results':sum(x['valid_settled']>0 for x in leagues.values())},
        'leagues':leagues,
        'warning':'Comparação meramente descritiva entre calendários e adversários diferentes; não comparar Brier até existirem amostras suficientes. Sem odds reais, nenhuma métrica prova rentabilidade. Intervalos CI95 são aproximações sem ajuste para dependência entre jogos.',
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--audit',type=Path,default=ROOT/'data'/'expansion_1x2_audit.json')
    parser.add_argument('--output',type=Path,default=ROOT/'data'/'league_comparison.json')
    args=parser.parse_args()
    report=build(json.loads(args.audit.read_text(encoding='utf8')))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,separators=(',',':'))+'\n',
                           encoding='utf8')
    print('Five-league prospective 1X2 comparison',
          json.dumps({'totals':report['totals'],
                      'n_by_league':{k:v['valid_settled'] for k,v in report['leagues'].items()},
                      'status':report['ranking_status']},ensure_ascii=False))


if __name__=='__main__':
    main()
