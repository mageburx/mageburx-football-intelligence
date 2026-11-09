"""Weekend result audits remain signed, contemporaneous and source verified."""
import copy
import datetime as dt
import hashlib
import json
import unittest

from scripts.record_expansion_1x2 import run
from scripts.audit_weekend_1x2 import build,weekend_days
from scripts.audit_expansion_1x2 import calculate
from scripts.build_validation_center import build as build_validation_center

NOW=dt.datetime(2026,11,9,0,35,tzinfo=dt.timezone.utc)
SAME_DAY=dt.datetime(2026,11,8,22,0,tzinfo=dt.timezone.utc)

def signed(id,date='2026-11-08',league='pt',home='Home',away='Away',p=None):
    p=p or [.6,.25,.15]
    record={'key':f'{league}:2026-2027:{id}','league':league,
            'match_id':id,'issued_at':'2026-11-06T19:00:00+00:00',
            'model_generated_at':'2026-11-06T18:59:00+00:00',
            'model':'blend','date':date,'home':home,'away':away,
            'probabilities_1x2':p,
            'warning':'Research only; no betting odds or verified financial edge.'}
    record['sha256']=hashlib.sha256(json.dumps(record,sort_keys=True,
                  ensure_ascii=False).encode('utf8')).hexdigest()
    return record

def fixture(id,date='2026-11-08',score=(2,0),home='Home',away='Away'):
    return {'id':id,'date':date,'home':home,'away':away,
            'finished':score is not None,'result_verified':score is not None,
            'match_status':'FT' if score else '',
            'home_score':score[0] if score else None,
            'away_score':score[1] if score else None}

def season(*entries):
    return {'schema':1,'season':'2026-2027','leagues':{
        'pt':{'events':list(entries)},
        'dk':{'events':[]},'nl':{'events':[]},
        'dk2':{'events':[]},'no':{'events':[]}}}

def ledger(*entries):
    return {'schema':1,'method':'Frozen 1X2 pre-match forecasts',
            'predictions':list(entries),'settlements':[]}

def model():
    return {'generated_at':'2026-11-08T21:59:00+00:00','leagues':{}}

class VerifiedWeekendTests(unittest.TestCase):
    def test_weekend_interval_after_sunday(self):
        self.assertEqual(tuple(x.isoformat() for x in weekend_days(NOW)),
                         ('2026-11-07','2026-11-08'))
        self.assertEqual(tuple(x.isoformat() for x in weekend_days(
            dt.datetime(2026,11,8,19,tzinfo=dt.timezone.utc))),
                         ('2026-11-07','2026-11-08'))
    def test_same_day_verified_ft_settles_original_signed_prediction(self):
        p=signed('123')
        s=season(fixture('123'))
        db=run(s,model(),ledger(p),now=SAME_DAY)
        self.assertEqual(len(db['predictions']),1)
        self.assertEqual(len(db['settlements']),1)
        self.assertEqual(db['settlements'][0]['date'],'2026-11-08')
        self.assertTrue(db['settlements'][0]['verified_final'])
        self.assertEqual(run(s,model(),db,now=NOW)['settlements'],db['settlements'])
        audit=calculate(db,s,now=NOW)
        self.assertEqual(audit['leagues']['pt']['settled_valid'],1)
        scorecard=build(db,s,now=NOW)
        self.assertEqual(scorecard['metrics']['n'],1)
        self.assertEqual(scorecard['metrics']['top_pick_correct'],1)
        self.assertAlmostEqual(scorecard['metrics']['brier'],.245)
        self.assertAlmostEqual(scorecard['metrics']['uniform_brier'],2/3,places=4)
        self.assertEqual(scorecard['counts']['validated'],1)
        full=build_validation_center(db,s,audit,now=NOW)
        self.assertEqual(full['weekend_audit']['metrics']['n'],1)
    def test_no_settlement_after_date_change_even_when_final(self):
        p=signed('123',date='2026-11-07')
        db=run(season(fixture('123',date='2026-11-08')),model(),ledger(p),NOW)
        self.assertEqual(db['settlements'],[])
        scorecard=build(db,season(fixture('123',date='2026-11-08')),NOW)
        self.assertEqual(scorecard['counts']['rescheduled'],1)
        self.assertIsNone(scorecard['metrics']['brier'])
    def test_invalid_signature_or_nonprematch_cannot_settle(self):
        p=signed('123');p['probabilities_1x2']=[.99,.005,.005]
        db=run(season(fixture('123')),model(),ledger(p),NOW)
        self.assertEqual(db['settlements'],[])
        p=signed('123');p['issued_at']='2026-11-08T09:00:00+00:00'
        p['sha256']=hashlib.sha256(json.dumps({k:v for k,v in p.items() if k!='sha256'},
                      sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        db=run(season(fixture('123')),model(),ledger(p),NOW)
        self.assertEqual(db['settlements'],[])
    def test_pending_ft_is_not_a_false_hit(self):
        p=signed('123')
        r=build(ledger(p),season(fixture('123')),now=NOW)
        self.assertEqual(r['counts']['confirmed_pending'],1)
        self.assertEqual(r['metrics']['n'],0)
        self.assertIsNone(r['metrics']['accuracy'])
    def test_unverified_scores_and_postponed_games_not_used(self):
        p1=signed('123',date='2026-11-07')
        p2=signed('456')
        e1=fixture('123',date='2026-11-07',score=None)
        e1.update({'finished':True,'home_score':3,'away_score':2})
        e2=fixture('456',score=None)
        e2['match_status']='PST'
        db=ledger(p1,p2)
        report=build(db,season(e1,e2),NOW)
        self.assertEqual(report['counts']['unverified'],1)
        self.assertEqual(report['counts']['postponed'],1)
        self.assertEqual(report['metrics']['n'],0)
        self.assertTrue(all(x['score'] is None for x in report['records']))
    def test_copy_of_original_prediction_not_modified(self):
        p=signed('123');before=copy.deepcopy(p)
        db=run(season(fixture('123')),model(),ledger(p),NOW)
        self.assertEqual(p,before)
        self.assertEqual(db['predictions'][0],before)

if __name__=='__main__':
    unittest.main()
