"""No retroactive changes, no unknown matches after restoring Dutch 1X2 lineage."""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.audit_expansion_1x2 import calculate
from scripts.collect_expanded_leagues import collect as collect_expanded
from scripts.collect_openfootball_nl import merge_current
from scripts.record_expansion_1x2 import run
from scripts.reconcile_nl_forecast_ids import recover

NOW=dt.datetime(2026,11,6,21,0,tzinfo=dt.timezone.utc)


def fixture(id,date,home='Ajax',away='Groningen'):
    return {'id':id,'date':date,'home':home,'away':away,
            'finished':False,'home_score':None,'away_score':None,
            'round':24,'utc':''}


def snapshot(primary='2489400'):
    return {'schema':1,'season':'2026-2027','leagues':{
        'pt':{'events':[]},'dk':{'events':[]},
        'nl':{'source_season':'2026-2027','events':[fixture(primary,'2027-02-14')],
              'openfootball':{'source':'CC0','superseded':[]}},
        'dk2':{'source_season':'2026-2027','events':[],
               'dbu_official':{'checked_at':NOW.isoformat(),'status':'sample_available'}},
        'no':{'source_season':'2026','events':[],
              'fantasy_research':{'source_matches':240,
                                  'checked_at':NOW.isoformat()}}}}


def issued(id='ofnl:2026-27:2027-02-13:ajax:groningen',date='2027-02-13',
           home='Ajax',away='Groningen'):
    record={'key':f'nl:2026-2027:{id}','league':'nl','match_id':id,
            'issued_at':NOW.isoformat(),
            'model_generated_at':(NOW-dt.timedelta(minutes=1)).isoformat(),
            'model':'poisson','date':date,'home':home,'away':away,
            'probabilities_1x2':[.5,.3,.2],
            'warning':'Research only; no betting odds or verified financial edge.'}
    record['sha256']=hashlib.sha256(json.dumps(record,sort_keys=True,
            ensure_ascii=False).encode('utf8')).hexdigest()
    return record


class SignedForecastReconciliationTests(unittest.TestCase):
    def test_disappeared_id_is_linked_but_forecast_never_migrates(self):
        season=snapshot()
        entry=issued()
        ledger={'schema':1,'predictions':[entry],'settlements':[]}
        immutable=json.dumps(ledger,sort_keys=True)
        actual,report=recover(season,ledger,NOW)
        self.assertEqual(report['newly_recovered'],1)
        self.assertEqual(report['missing_without_safe_match'],0)
        self.assertEqual(json.dumps(ledger,sort_keys=True),immutable)
        mapping=actual['leagues']['nl']['openfootball']['superseded'][0]
        self.assertEqual(mapping['id'],entry['match_id'])
        self.assertEqual(mapping['replacement_id'],'2489400')
        self.assertFalse(mapping['settlement_transfer_allowed'])
        a=calculate(ledger,actual,NOW)
        self.assertEqual(a['leagues']['nl']['fixture_missing'],0)
        self.assertEqual(a['leagues']['nl']['superseded'],1)
        self.assertEqual(a['leagues']['nl']['settled_valid'],0)
        self.assertEqual(a['warnings'][0]['code'],'superseded_duplicate_fixture')
        _,again=recover(actual,ledger,NOW)
        self.assertEqual(again['newly_recovered'],0)
        self.assertEqual(len(actual['leagues']['nl']['openfootball']['superseded']),1)

    def test_bad_signature_or_ambiguous_pair_not_auto_linked(self):
        season=snapshot()
        valid=issued()
        bad=copy.deepcopy(valid)
        bad['sha256']='tampered'
        ledger={'schema':1,'predictions':[bad],'settlements':[]}
        _,report=recover(season,ledger,NOW)
        self.assertEqual(report['invalid_signature'],1)
        self.assertEqual(report['newly_recovered'],0)
        self.assertEqual(calculate(ledger,season,NOW)['leagues']['nl']['fixture_missing'],1)

        season2=snapshot()
        season2['leagues']['nl']['events'].append(fixture('2489401','2027-02-15'))
        _,report=recover(season2,{'schema':1,'predictions':[valid],
                                  'settlements':[]},NOW)
        self.assertEqual(report['ambiguous_match'],1)
        self.assertEqual(report['newly_recovered'],0)

    def test_mismatch_over_120_days_is_unresolved(self):
        season=snapshot()
        entry=issued(date='2026-08-01')
        ledger={'schema':1,'predictions':[entry],'settlements':[]}
        _,report=recover(season,ledger,NOW)
        self.assertEqual(report['missing_without_safe_match'],1)
        self.assertEqual(report['newly_recovered'],0)

    def test_no_second_1x2_tip_for_same_oriented_pair(self):
        prior=snapshot('ofnl:fixture')
        prior['leagues']['nl']['events'][0]['date']='2027-02-13'
        model={'generated_at':NOW.isoformat(),'leagues':{'nl':{
            'predictions':{'ofnl:fixture':{
                'p1':.50,'px':.30,'p2':.20,'model':'blend'}}}}}
        db=run(prior,model,now=NOW)
        self.assertEqual(len(db['predictions']),1)
        new_snapshot=snapshot('tsdb-primary')
        model['leagues']['nl']['predictions']={'tsdb-primary':{
            'p1':.52,'px':.29,'p2':.19,'model':'blend'}}
        updated=run(new_snapshot,model,existing=db,now=NOW+dt.timedelta(minutes=20))
        self.assertEqual(len(updated['predictions']),1)
        self.assertEqual(updated['predictions'][0]['match_id'],'ofnl:fixture')

    def test_primary_and_cc0_alternative_dates_not_inserted_as_duplicate(self):
        saved=[fixture('2489400','2027-02-14')]
        added,confirmed,conflicts=merge_current(saved,
            [fixture('ofnl:2026-27:2027-02-13:ajax:groningen','2027-02-13')])
        self.assertEqual((added,confirmed,conflicts),(0,0,0))
        self.assertEqual(len(saved),1)

    def test_hourly_recollection_retains_original_source_audit_state(self):
        original=snapshot()
        original['leagues']['nl']['openfootball']['superseded']=[{
            'id':'legacy-id','replacement_id':'2489400'}]
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'season.json'
            path.write_text(json.dumps(original),encoding='utf8')
            actual=collect_expanded(path,max_calls=0,pause=0,now=NOW)
            self.assertEqual(actual['leagues']['nl']['openfootball']['superseded'][0]['id'],
                             'legacy-id')
            self.assertEqual(actual['leagues']['dk2']['dbu_official']['status'],
                             'sample_available')
            self.assertEqual(actual['leagues']['no']['fantasy_research']['source_matches'],
                             240)


if __name__=='__main__':
    unittest.main()
