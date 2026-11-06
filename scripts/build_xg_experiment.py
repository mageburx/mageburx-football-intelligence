#!/usr/bin/env python3
"""Shadow Poisson+xG research: only forward-looking, time-stamped evidence.

Never changes the public production model or advises bets. Candidate uses fixed,
predeclared blending (20% xG proxy, 80% independent model goal rates) and
can only be evaluated after an actual pre-match candidate was frozen.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path

try:
    from scripts.build_model import score_probs
    from scripts.build_shots_research import team_key
except ModuleNotFoundError:
    from build_model import score_probs
    from build_shots_research import team_key

ROOT=Path(__file__).resolve().parents[1]
SAMPLE_MIN=3
LOOKBACK_DAYS=90
WEIGHT_XG=0.20
REVIEW_MIN=100
LEDGER=ROOT/'data'/'xg_shadow_ledger.json'
REPORT=ROOT/'data'/'xg_experiment.json'


def as_utc(value):
    try:
        date=dt.datetime.fromisoformat(str(value).replace('Z','+00:00'))
        if date.tzinfo is None:return None
        return date.astimezone(dt.timezone.utc)
    except (ValueError,TypeError):
        return None


def sample_for_team(records,team,fixture_date,asof):
    cutoff=dt.datetime.combine(dt.date.fromisoformat(fixture_date),dt.time.min,
                               tzinfo=dt.timezone.utc)
    seen=set()
    values=[]
    for item in records:
        if not isinstance(item,dict):continue
        source_id=item.get('source_id')
        if not source_id or source_id in seen:continue
        day=item.get('date','')
        if not isinstance(day,str) or day>=fixture_date:continue
        observed=as_utc(item.get('first_observed_at'))
        if observed is None or observed>asof or observed>=cutoff:continue
        try:
            age=(dt.date.fromisoformat(fixture_date)-dt.date.fromisoformat(day)).days
        except ValueError:continue
        if age<=0 or age>LOOKBACK_DAYS:continue
        xg=item.get('xg')
        if not isinstance(xg,list) or len(xg)!=2 or any(
            type(v) not in (int,float) or not math.isfinite(v) or v<0 or v>15 for v in xg):
            continue
        home,away=team_key(item.get('home','')),team_key(item.get('away',''))
        if home==team:pair=(float(xg[0]),float(xg[1]))
        elif away==team:pair=(float(xg[1]),float(xg[0]))
        else:continue
        seen.add(source_id)
        values.append((day,pair))
    values.sort(key=lambda t:t[0],reverse=True)
    return [v for _,v in values[:5]]


def candidate_rates(lh,la,home,away):
    # Fixed research rule, NOT optimized using future results.
    hxgf=sum(x[0] for x in home)/len(home)
    hxga=sum(x[1] for x in home)/len(home)
    axgf=sum(x[0] for x in away)/len(away)
    axga=sum(x[1] for x in away)/len(away)
    hproxy=(hxgf+axga)/2
    aproxy=(axgf+hxga)/2
    def blend(base,proxy):
        return max(.15,min(4.,(1-WEIGHT_XG)*base+WEIGHT_XG*proxy))
    return blend(lh,hproxy),blend(la,aproxy)


def probabilities(lh,la):
    return [round(float(v),7) for v in score_probs(lh,la,dc=True)['p']]


def brier(p,outcome):
    return sum((p[i]-(1 if i==outcome else 0))**2 for i in range(3))


def evaluate(ledger,league):
    candidates=[x for x in ledger.get('predictions',[]) if x.get('league')==league]
    settled={x['key']:x for x in ledger.get('settlements',[]) if x.get('key')}
    differences=[]
    llbase=llxg=bsbase=bsxg=0.
    for p in candidates:
        match=settled.get(p['key'])
        if match is None:continue
        hs,aws=match.get('home_score'),match.get('away_score')
        if type(hs) is not int or type(aws) is not int:continue
        y=0 if hs>aws else 1 if hs==aws else 2
        baseline=p['baseline_1x2']
        challenger=p['xg_1x2']
        e0=brier(baseline,y)
        e1=brier(challenger,y)
        bsbase+=e0
        bsxg+=e1
        llbase-=math.log(max(1e-9,baseline[y]))
        llxg-=math.log(max(1e-9,challenger[y]))
        differences.append(e0-e1)
    n=len(differences)
    if n==0:return {'n':0,'status':'no_settled_shadow_predictions','model_proven':False}
    gain=sum(differences)/n
    variance=(sum((x-gain)**2 for x in differences)/(n-1)) if n>1 else 0.
    interval=[round(gain-1.96*math.sqrt(variance/n),6),
              round(gain+1.96*math.sqrt(variance/n),6)]
    return {'n':n,'baseline_brier':round(bsbase/n,5),
            'xg_brier':round(bsxg/n,5),
            'baseline_log_loss':round(llbase/n,5),
            'xg_log_loss':round(llxg/n,5),
            'brier_gain':round(gain,6),'gain_ci95_approx':interval,
            'status':('signal_for_human_review' if n>=REVIEW_MIN and interval[0]>0
                      else 'collecting_or_inconclusive'),
            'model_proven':False}


def build(signals,season,model,ledger=None,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:raise ValueError('Aware timestamp required')
    now=now.astimezone(dt.timezone.utc)
    today=now.date().isoformat()
    original=ledger or {'schema':1,'predictions':[],'settlements':[]}
    # Preserve past forecasts and settlements as immutable research records.
    if original.get('schema')!=1:raise ValueError('Unknown shadow ledger schema')
    old={v['key'] for v in original['predictions']}
    settled={v['key'] for v in original['settlements']}
    report={'schema':1,'generated_at':now.replace(microsecond=0).isoformat(),
            'status':'research_only','production_model_changed':False,
            'candidate':'Dixon-Coles fixed baseline (goal rates) vs 80% baseline/20% observed xG proxy; NOT fitted or approved',
            'min_pre_match_xg_matches_per_team':SAMPLE_MIN,
            'minimum_paired_settled_for_review':REVIEW_MIN,
            'source':'Cornerflick with explicit attribution; limited research observations',
            'leagues':{}}
    generated=as_utc(model.get('generated_at'))
    fresh_model=generated is not None and dt.timedelta(0)<=now-generated<=dt.timedelta(hours=48)
    for lid in ('pt','dk'):
        info=season.get('leagues',{}).get(lid,{})
        events=info.get('events',[])
        obs=signals.get('leagues',{}).get(lid,{}).get('records',[])
        forecasts=model.get('leagues',{}).get(lid,{}).get('predictions',{})
        coverage={'xg_observations':sum(isinstance(x.get('xg'),list) for x in obs if isinstance(x,dict)),
                  'eligible_future_matches':0,'new_shadow_predictions':0,
                  'blocked_missing_xg_samples':0,'blocked_missing_model':0}
        for e in events:
            key=f'{lid}:{season.get("season","unknown")}:{e.get("id","")}'
            if key in old and key not in settled and e.get('finished') is True and (
                type(e.get('home_score')) is int and type(e.get('away_score')) is int):
                original['settlements'].append({
                    'key':key,'date':e['date'],'home_score':e['home_score'],
                    'away_score':e['away_score'],'resolved_at':now.replace(microsecond=0).isoformat()})
                settled.add(key)
            if key in old or e.get('finished') or e.get('date','')<=today:continue
            try:
                h=sample_for_team(obs,team_key(e['home']),e['date'],now)
                a=sample_for_team(obs,team_key(e['away']),e['date'],now)
            except (ValueError,KeyError):continue
            if len(h)<SAMPLE_MIN or len(a)<SAMPLE_MIN:
                coverage['blocked_missing_xg_samples']+=1
                continue
            p=forecasts.get(str(e['id']))
            if not fresh_model or not p or (
                type(p.get('lambdaH')) not in (int,float) or
                type(p.get('lambdaA')) not in (int,float) or
                p['lambdaH']<=0 or p['lambdaA']<=0):
                coverage['blocked_missing_model']+=1
                continue
            coverage['eligible_future_matches']+=1
            baseh,basea=p['lambdaH'],p['lambdaA']
            xgh,xga=candidate_rates(baseh,basea,h,a)
            original['predictions'].append({
                'key':key,'league':lid,'date':e['date'],
                'home':e['home'],'away':e['away'],
                'issued_at':now.replace(microsecond=0).isoformat(),
                'baseline_1x2':probabilities(baseh,basea),
                'xg_1x2':probabilities(xgh,xga),
                'base_lambdas':[baseh,basea],
                'shadow_lambdas':[round(xgh,5),round(xga,5)],
                'xg_samples_home':len(h),'xg_samples_away':len(a),
                'note':'Research-only; different from selected live 1X2 method when live uses Elo blend.',
            })
            old.add(key)
            coverage['new_shadow_predictions']+=1
        coverage['paired_evaluation']=evaluate(original,lid)
        coverage['status']=('prospective_shadow_running' if
            coverage['eligible_future_matches'] or
            any(x.get('league')==lid for x in original['predictions'])
            else 'blocked_insufficient_club_xg_history')
        report['leagues'][lid]=coverage
    report['total_shadow_predictions']=len(original['predictions'])
    report['total_shadow_settlements']=len(original['settlements'])
    report['warning']='No in-sample xG lift claim. These snapshots start only when both clubs have three earlier validated xG observations. No model promotion, automatic betting, or assumed profitability.'
    return report,original


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--signals',type=Path,default=ROOT/'data'/'advanced_signals.json')
    p.add_argument('--season',type=Path,default=ROOT/'data'/'season.json')
    p.add_argument('--model',type=Path,default=ROOT/'data'/'model.json')
    p.add_argument('--ledger',type=Path,default=LEDGER)
    p.add_argument('--report',type=Path,default=REPORT)
    args=p.parse_args()
    def load(path,fallback=None):
        return json.loads(path.read_text(encoding='utf8')) if path.exists() else fallback
    report,ledger=build(load(args.signals,{}),load(args.season),load(args.model),
                        load(args.ledger),now=dt.datetime.now(dt.timezone.utc))
    for path,value in ((args.ledger,ledger),(args.report,report)):
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n',
                        encoding='utf8')
    print('xG shadow study',json.dumps({k:{'status':v['status'],'observations':v['xg_observations'],
                                           'new':v['new_shadow_predictions'],
                                           'paired':v['paired_evaluation']['n']}
                            for k,v in report['leagues'].items()},ensure_ascii=False))


if __name__=='__main__':
    main()
