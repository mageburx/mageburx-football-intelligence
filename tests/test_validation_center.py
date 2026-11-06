"""Validation Center: never count future/partial/replaced IDs as valid results."""
import datetime as dt
import hashlib
import json
import unittest
from scripts.build_validation_center import build
NOW=dt.datetime(2026,11,6,21,tzinfo=dt.timezone.utc)

def sign(key,lid,date,home='Home',away='Away'):
    pred={'key':key,'league':lid,'match_id':key.split(':',2)[-1],
          'issued_at':'2026-11-05T12:00:00+00:00',
          'model_generated_at':'2026-11-05T11:55:00+00:00',
          'model':'blend','date':date,'home':home,'away':away,
          'probabilities_1x2':[.4,.3,.3]}
    pred['sha256']=hashlib.sha256(json.dumps(pred,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return pred

def fixture(id,date,finished=False,status='NS',score=(None,None)):
    return {'id':id,'date':date,'home':'Home','away':'Away',
            'finished':finished,'result_verified':finished,
            'match_status':status,'home_score':score[0],'away_score':score[1]}

class ValidationCenterTests(unittest.TestCase):
    def make(self):
        specs=[
            ('a','pt','2026-11-08'),('b','dk','2026-11-06'),('c','no','2026-11-04'),
            ('d','dk2','2026-11-04'),('e','pt','2026-11-04'),('f','pt','2026-11-08'),
            ('g','nl','2026-11-08'),('h','pt','2026-11-04'),('i','pt','2026-11-08')]
        ps=[sign(f'{lid}:2026-2027:{k}',lid,date) for k,lid,date in specs]
        leagues={lid:{'events':[]} for lid in ('pt','dk','nl','dk2','no')}
        for k,lid,date in specs:
            if k=='g':continue
            if k=='h':date='2026-11-09'
            if k=='i':continue
            finished=k in ('d','e')
            event=fixture(k,date,finished,'FT' if finished else ('2H' if k=='b' else 'NS'),
                          (2,1) if finished else (None,None))
            leagues[lid]['events'].append(event)
        leagues['nl']['openfootball']={'superseded':[{'id':'g','replacement_id':'new_g'}]}
        season={'schema':1,'season':'2026-2027','updated_at':NOW.isoformat(),'leagues':leagues}
        settlement={'key':'pt:2026-2027:e','verified_final':True,'date':'2026-11-04',
                    'home_score':2,'away_score':1}
        ledger={'schema':1,'predictions':ps,'settlements':[settlement]}
        audit={'schema':1,'leagues':{lid:{'issued':sum(p['league']==lid for p in ps),
              'settled_valid':1 if lid=='pt' else 0} for lid in leagues}}
        return ledger,season,audit
    def test_status_partition_and_source_id_safety(self):
        ledger,season,audit=self.make()
        report=build(ledger,season,audit,now=NOW)
        self.assertEqual(report['total'],9)
        self.assertEqual(report['active_ids'],8)
        self.assertEqual(report['counts'],{
            'future':2,'in_progress':1,'unconfirmed':1,
            'awaiting_settlement':1,'validated':1,'review':2,'superseded':1})
        by_key={r['key'].rsplit(':',1)[-1]:r for r in report['records']}
        self.assertEqual(by_key['g']['replacement_id'],'new_g')
        self.assertIsNone(by_key['g']['score'])
        self.assertEqual(by_key['h']['reason'],'rescheduled_identity_requires_review')
        self.assertEqual(by_key['i']['reason'],'fixture_id_missing')
        self.assertEqual(by_key['e']['score'],{'home':2,'away':1})
        self.assertEqual(report['counts']['validated'],1)
    def test_unsigned_or_conflicting_result_never_valid(self):
        ledger,season,audit=self.make()
        ledger['settlements'][0]['away_score']=0
        audit['leagues']['pt']['settled_valid']=0
        report=build(ledger,season,audit,now=NOW)
        self.assertEqual(report['counts']['validated'],0)
        self.assertEqual(report['counts']['review'],3)
        self.assertTrue(report['general_ledger']['integrity_alerts']==0)
    def test_corrupted_signature_is_in_review(self):
        ledger,season,audit=self.make()
        ledger['predictions'][0]['probabilities_1x2']=[.9,.05,.05]
        result=build(ledger,season,audit,now=NOW)
        self.assertTrue(any(r['status']=='in_progress' for r in result['records']))
        found=next(r for r in result['records'] if r['key'].endswith(':a'))
        self.assertEqual(found['reason'],'invalid_signed_hash')
    def test_mismatched_audit_does_not_publish(self):
        ledger,season,audit=self.make()
        audit['leagues']['pt']['settled_valid']=2
        with self.assertRaises(ValueError):
            build(ledger,season,audit,now=NOW)
    def test_snapshot_live_is_not_verified_settlement(self):
        ledger,season,audit=self.make()
        report=build(ledger,season,audit,now=NOW)
        self.assertEqual(report['leagues']['dk']['in_progress'],1)
        self.assertEqual(report['leagues']['dk']['validated'],0)

if __name__=='__main__':
    unittest.main()
