import datetime as dt
import unittest

from scripts.audit_ledger_health import build as ledger_report, fingerprint
from scripts.audit_european_coverage import build as european_report
from scripts.collect_cross_competitions import priorities, empty


class AuditExpansionTests(unittest.TestCase):
    def at(self,day=6):
        return dt.datetime(2026,11,day,12,tzinfo=dt.timezone.utc)

    def example_prediction(self):
        p={'key':'pt:2026-2027:1','league':'pt',
           'issued_at':'2026-11-05T09:00:00+00:00',
           'date':'2026-11-06','home':'Porto','away':'Braga',
           'markets':{'over_2_5':.55}}
        p['sha256']=fingerprint(p)
        return p

    def test_ledger_classifies_today_and_later_missing_result(self):
        p=self.example_prediction()
        season={'season':'2026-2027','leagues':{'pt':{'events':[
            {'id':'1','date':'2026-11-06','home':'Porto','away':'Braga','finished':False}]}}}
        a=ledger_report({'predictions':[p],'settlements':[]},season,self.at())
        self.assertEqual(a['states']['today'],1)
        self.assertEqual(a['states']['settled'],0)
        self.assertEqual(a['issue_count'],0)
        b=ledger_report({'predictions':[p],'settlements':[]},season,self.at(8))
        self.assertEqual(b['states']['past_due_missing_result'],1)
        self.assertEqual(b['status'],'monitoring')
        season['leagues']['pt']['events'][0].update(
            {'finished':True,'home_score':2,'away_score':1})
        c=ledger_report({'predictions':[p],'settlements':[]},season,self.at(8))
        self.assertEqual(c['states']['finished_awaiting_settlement'],1)
        self.assertEqual(c['status'],'requires_review')

    def test_ledger_hash_and_provider_score_conflicts(self):
        p=self.example_prediction()
        s={'key':p['key'],'date':'2026-11-06','home_score':2,'away_score':1}
        season={'season':'2026-2027','leagues':{'pt':{'events':[
            {'id':'1','date':'2026-11-06','home':'Porto','away':'Braga',
             'finished':True,'home_score':0,'away_score':1}]}}}
        a=ledger_report({'predictions':[p],'settlements':[s]},season,self.at(8))
        self.assertTrue(any(e['code']=='settlement_conflicts_with_provider'
                            for e in a['issues']))
        p['markets']['over_2_5']=.99
        b=ledger_report({'predictions':[p],'settlements':[]},season,self.at(8))
        self.assertTrue(any(e['code']=='prediction_hash_mismatch' for e in b['issues']))

    def test_uefa_audit_deduplicates_and_never_certifies_complete(self):
        match={'id':'a','competition_id':'uefa_cl','date':'2025-10-02',
               'home':'FC Porto','away':'Ajax','finished':True}
        duplicate={**match,'id':'b','home':'Porto'}
        raw={'events':[match,duplicate],'competitions':{
             'uefa_cl:2025-2026':{'checked_rounds':[2,3,4]}}}
        a=european_report(raw,self.at())
        row=a['leagues']['uefa_cl:2025-2026']
        self.assertEqual(row['observed_matches'],1)
        self.assertEqual(row['unqueried_rounds_in_trial_window'],[1,5,6,7,8,9,10])
        self.assertEqual(row['status'],'partial_not_certified')

    def test_historical_uefa_rounds_have_priority_over_current_future(self):
        d=empty()
        d['competitions']={'uefa_cl:2026-2027':{'checked_rounds':[1,2,3,4,5,6,7,8],
                                                'empty_checked_at':{}}}
        todo=priorities(d,self.at())
        self.assertEqual(todo[0][1],'2024-2025')
        self.assertEqual(todo[0][0],'uefa_cl')

    def test_refreshes_checked_rounds_after_overdue_unscored_fixture(self):
        d=empty()
        d['competitions']={'uefa_cl:2026-2027':{'checked_rounds':[3],
                                                'empty_checked_at':{}}}
        d['events']=[{'id':'a','competition_id':'uefa_cl',
                      'date':'2026-10-05','finished':False}]
        todo=priorities(d,self.at())
        self.assertIn(('uefa_cl','2026-2027',3),todo)
        d['competitions']['uefa_cl:2026-2027']['round_refresh_at']={
            '3':'2026-11-06T11:00:00+00:00'}
        self.assertNotIn(('uefa_cl','2026-2027',3),priorities(d,self.at()))


if __name__=='__main__':
    unittest.main()
