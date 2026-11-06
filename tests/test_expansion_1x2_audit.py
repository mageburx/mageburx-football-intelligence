import datetime as dt
import hashlib
import json
import unittest

from scripts.audit_expansion_1x2 import calculate

NOW=dt.datetime(2026,11,10,14,tzinfo=dt.timezone.utc)


def forecast(key="no:2026-2027:fixture1",date="2026-11-08",
             issued="2026-11-06T15:00:00+00:00"):
    p={'key':key,'league':'no','match_id':'fixture1',
       'issued_at':issued,'model_generated_at':'2026-11-06T14:59:00+00:00',
       'model':'poisson','date':date,'home':'Brann','away':'Molde',
       'probabilities_1x2':[0.6,0.25,0.15],
       'warning':'Research only; no betting odds or verified financial edge.'}
    p['sha256']=hashlib.sha256(json.dumps(p,sort_keys=True,
        ensure_ascii=False).encode('utf8')).hexdigest()
    return p


def season(date="2026-11-08",score=None):
    h,a=score if score else (None,None)
    return {'schema':1,'season':'2026-2027','leagues':{'no':{
        'events':[{'id':'fixture1','date':date,'home':'Brann','away':'Molde',
                   'finished':score is not None,'result_verified':score is not None,
                   'match_status':'FT' if score else '', 'home_score':h,
                   'away_score':a}]}}}


class AuditTests(unittest.TestCase):
    def test_valid_forecast_stays_unscored_until_confirmed_result(self):
        db={'schema':1,'predictions':[forecast()],'settlements':[]}
        report=calculate(db,season(),NOW)
        self.assertEqual(report['leagues']['no']['issued'],1)
        self.assertEqual(report['leagues']['no']['past_due'],1)
        self.assertIsNone(report['leagues']['no']['brier'])
        self.assertEqual(report['leagues']['no']['settled_valid'],0)
        self.assertEqual(report['warning_count'],0)

    def test_only_real_signed_prematch_prediction_gets_brier(self):
        db={'schema':1,'predictions':[forecast()],
            'settlements':[{'key':'no:2026-2027:fixture1',
                'date':'2026-11-08','home_score':2,'away_score':1,'verified_final':True}]}
        report=calculate(db,season(score=(2,1)),NOW)
        no=report['leagues']['no']
        self.assertEqual(no['settled_valid'],1)
        self.assertAlmostEqual(no['brier'],0.245)
        self.assertEqual(report['warning_count'],0)

    def test_cannot_count_tampered_or_postmatch_tip(self):
        a=forecast()
        a['probabilities_1x2']=[.9,.05,.05]
        b=forecast(issued="2026-11-08T10:00:00+00:00")
        db={'schema':1,'predictions':[a,b],
            'settlements':[{'key':a['key'],'date':'2026-11-08',
                             'home_score':2,'away_score':1}]}
        report=calculate(db,season(score=(2,1)),NOW)
        self.assertEqual(report['leagues']['no']['settled_valid'],0)
        self.assertGreater(report['warning_count'],0)

    def test_reschedule_is_flagged_and_not_laundered_as_evidence(self):
        p=forecast()
        db={'schema':1,'predictions':[p],'settlements':[]}
        report=calculate(db,season(date='2026-11-15'),NOW)
        self.assertEqual(report['leagues']['no']['rescheduled'],1)
        self.assertEqual(report['leagues']['no']['future'],1)
        self.assertEqual(report['leagues']['no']['status'],'schedule_change_review')

    def test_orphan_or_conflicting_settlement_detected(self):
        db={'schema':1,'predictions':[forecast()],
            'settlements':[{'key':'no:2026-2027:fixture1',
                             'date':'2026-11-08','home_score':0,'away_score':5,'verified_final':True},
                           {'key':'orphan','date':'2026-11-08',
                             'home_score':1,'away_score':0}]}
        report=calculate(db,season(score=(2,1)),NOW)
        self.assertEqual(report['leagues']['no']['settled_valid'],0)
        self.assertIn('settlement_score_conflict',
                      [x['code'] for x in report['warnings']])
        self.assertIn('orphan_settlement',
                      [x['code'] for x in report['warnings']])


if __name__=='__main__':unittest.main()
