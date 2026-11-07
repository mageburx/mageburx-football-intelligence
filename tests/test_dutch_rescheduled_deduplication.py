"""Dutch future match duplication and frozen-forward-forecast safety."""
import datetime as dt
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.collect_openfootball_nl import reconcile_rescheduled_fixtures,collect
from scripts.audit_expansion_1x2 import calculate

NOW=dt.datetime(2026,11,6,21,tzinfo=dt.timezone.utc)

def event(id,date,home='Twente',away='Sparta Rotterdam',finished=False):
    return {'id':id,'date':date,'home':home,'away':away,
            'home_score':1 if finished else None,'away_score':0 if finished else None,
            'finished':finished,'round':12,'utc':''}

def signed(key):
    p={'key':key,'league':'nl','match_id':key.split(':')[-1],
       'issued_at':'2026-11-06T19:00:00+00:00',
       'model_generated_at':'2026-11-06T18:55:00+00:00',
       'date':'2027-02-06','home':'Twente','away':'Sparta Rotterdam',
       'probabilities_1x2':[.5,.3,.2],'model':'poisson'}
    p['sha256']=hashlib.sha256(json.dumps(p,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return p

class DutchDuplicateTests(unittest.TestCase):
    def test_primary_id_survives_replanned_date(self):
        entries=[event('tsdb-1','2026-12-13'),event('ofnl:other','2027-02-06')]
        cleaned,removed=reconcile_rescheduled_fixtures(entries)
        self.assertEqual(len(cleaned),1)
        self.assertEqual(cleaned[0]['id'],'tsdb-1')
        self.assertEqual(removed[0]['id'],'ofnl:other')
        self.assertEqual(removed[0]['replacement_id'],'tsdb-1')

    def test_finished_results_are_never_removed(self):
        records=[event('primary','2026-12-13',finished=True),
                 event('ofnl:other','2027-02-06')]
        result,removed=reconcile_rescheduled_fixtures(records)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['id'],'primary')
        self.assertEqual(len(removed),1)
        both=[event('a','2026-12-13',finished=True),
              event('b','2027-02-06',finished=True)]
        result,removed=reconcile_rescheduled_fixtures(both)
        self.assertEqual(len(result),2)
        self.assertEqual(removed,[])

    def test_different_home_away_ties_are_not_merged(self):
        a=event('a','2026-12-13')
        b=event('b','2027-02-06',home='Sparta Rotterdam',away='Twente')
        result,removed=reconcile_rescheduled_fixtures([a,b])
        self.assertEqual(len(result),2)
        self.assertEqual(removed,[])

    def test_hourly_cleanup_without_external_request(self):
        with tempfile.TemporaryDirectory() as root:
            s=Path(root)/'season.json'
            h=Path(root)/'nl_history.json'
            original={'schema':1,'season':'2026-2027','leagues':{
                'nl':{'events':[event('tsdb-1','2026-12-13'),
                                event('ofnl:other','2027-02-06')],
                      'openfootball':{'result_evidence_v1':True}}}}
            archive={'schema':1,'seasons':{},
                     'last_attempt_at':'2026-11-06T20:00:00+00:00'}
            s.write_text(json.dumps(original),encoding='utf8')
            h.write_text(json.dumps(archive),encoding='utf8')
            def forbidden(*args):
                raise AssertionError('No archive fetch before 22h')
            result,_=collect(s,h,fetcher=forbidden,now=NOW)
            self.assertEqual(len(result['leagues']['nl']['events']),1)
            self.assertEqual(len(result['leagues']['nl']['openfootball']['superseded']),1)
            self.assertEqual(len(json.loads(s.read_text())['leagues']['nl']['events']),1)

    def test_signed_superseded_prediction_flagged_not_reassigned(self):
        key='nl:2026-2027:ofnl:other'
        ledger={'schema':1,'predictions':[signed(key)],'settlements':[]}
        snapshot={'season':'2026-2027','leagues':{
            'nl':{'events':[event('tsdb-1','2026-12-13')],
                  'openfootball':{'superseded':[{'id':'ofnl:other',
                                               'replacement_id':'tsdb-1'}]}},
            'dk2':{'events':[]},'no':{'events':[]}}}
        audit=calculate(ledger,snapshot,now=NOW)
        nl=audit['leagues']['nl']
        self.assertEqual(nl['issued'],1)
        self.assertEqual(nl['superseded'],1)
        self.assertEqual(nl['settled_valid'],0)
        self.assertIn('superseded_duplicate_fixture',
                      [x['code'] for x in audit['warnings']])
        self.assertEqual(ledger['predictions'][0]['key'],key)

if __name__=='__main__':
    unittest.main()
