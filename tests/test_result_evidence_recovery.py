"""Independent full-time evidence, no cross-ID settlement or source-status guesses."""
import copy
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from scripts.recover_verified_results import recover,verify_one
from scripts.collect_expanded_leagues import save_match
from scripts.collect_openfootball_nl import parsed,merge_current
from scripts.collect_danish_first_official import collect as collect_dbu
from scripts.match_status import verified_event

NOW=dt.datetime(2026,11,7,1,0,tzinfo=dt.timezone.utc)

def event(id,date,home,away,score=(None,None),finished=False):
    return {'id':id,'date':date,'home':home,'away':away,'finished':finished,
            'result_verified':False,'home_score':score[0],'away_score':score[1]}

def api(id,lid,season,date,home,away,score=(2,1),status='FT'):
    return {'idEvent':id,'idLeague':str(lid),'strSeason':season,
            'dateEvent':date,'strTimestamp':date+'T15:00:00',
            'strHomeTeam':home,'strAwayTeam':away,'intHomeScore':str(score[0]),
            'intAwayScore':str(score[1]),'strStatus':status,'intRound':'1'}

class ResultRecoveryTests(unittest.TestCase):
    def snapshot(self):
        return {'schema':1,'season':'2026-2027','leagues':{
            'no':{'events':[
                event('2398991','2026-03-14','Hamarkameratene','Viking',(2,1),True),
                event('fantasy-no:2026:44','2026-03-15','Molde','Rosenborg',(2,0),True)]},
            'nl':{'events':[event('2489066','2026-08-07','Cambuur','Excelsior',(0,4),True)]},
            'dk2':{'events':[event('2488341','2026-07-24','Vejle','AB Gladsaxe',(2,2),True)]}}}
    def sources(self):
        return {
            '2398991':api('2398991',4358,'2026','2026-03-14','Hamarkameratene','Viking'),
            '2489066':api('2489066',4337,'2026-2027','2026-08-07','Cambuur','Excelsior',(0,4)),
            '2488341':api('2488341',4683,'2026-2027','2026-07-24','Vejle','AB Gladsaxe',(2,2))}
    def test_exact_source_id_promotes_independent_final_only(self):
        season=self.snapshot();sources=self.sources();calls=[]
        def getter(id):calls.append(id);return [sources[id]]
        out=recover(season,getter,NOW,{'no':2,'nl':1,'dk2':1})
        self.assertEqual(out['verified'],3)
        self.assertEqual(calls,['2398991','2489066','2488341'])
        self.assertTrue(verified_event(season['leagues']['no']['events'][0]))
        self.assertEqual(season['leagues']['no']['events'][0]['id'],'2398991')
        self.assertFalse(verified_event(season['leagues']['no']['events'][1]))
        self.assertTrue(verified_event(season['leagues']['nl']['events'][0]))
        # Signed predictions and model input are not used or modified here.
        self.assertEqual(out['leagues']['no']['unverified_research_results'],1)
        self.assertEqual(recover(season,getter,NOW,{'no':2,'nl':1,'dk2':1})['requests'],0)
        self.assertEqual(len(calls),3)
    def test_cross_id_rejected_without_transferring_result(self):
        old=event('2398991','2026-03-14','Hamarkameratene','Viking',(2,1),True)
        original=copy.deepcopy(old)
        answer=verify_one(old,'no',api('2398992',4358,'2026','2026-03-14',
            'Hamarkameratene','Viking'),NOW)
        self.assertEqual(answer,'missing_exact_id')
        self.assertEqual(old,original)
    def test_partial_status_does_not_promote(self):
        season=self.snapshot()
        original=season['leagues']['no']['events'][0].copy()
        sources=self.sources();sources['2398991']['strStatus']='HT'
        out=recover(season,lambda id:[sources[id]],NOW,{'no':1,'nl':0,'dk2':0})
        self.assertEqual(out['verified'],0)
        self.assertFalse(season['leagues']['no']['events'][0]['result_verified'])
        self.assertEqual(season['leagues']['no']['events'][0]['home_score'],original['home_score'])
    def test_disagreeing_provider_quarantined_preserves_original_score(self):
        season=self.snapshot()
        sources=self.sources()
        sources['2398991']['intHomeScore']='7'
        out=recover(season,lambda id:[sources[id]],NOW,{'no':1,'nl':0,'dk2':0})
        row=season['leagues']['no']['events'][0]
        self.assertEqual(out['conflicts'],1)
        self.assertEqual((row['home_score'],row['away_score']),(2,1))
        self.assertEqual(row['result_dispute']['provider_score'],[7,1])
        self.assertTrue(row['score_conflict'])
        self.assertFalse(verified_event(row))
    def test_name_and_date_mismatches_block_confirmation(self):
        sources=self.sources()
        first=event('2398991','2026-03-14','Hamarkameratene','Viking',(2,1),True)
        sources['2398991']['strAwayTeam']='Other club'
        self.assertEqual(verify_one(first,'no',sources['2398991'],NOW),'fixture_identity_conflict')
        self.assertFalse(first['result_verified'])
        sources['2398991']['strAwayTeam']='Viking'
        sources['2398991']['dateEvent']='2026-03-15'
        self.assertEqual(verify_one(first,'no',sources['2398991'],NOW),'fixture_identity_conflict')

class TwoSourceDanishTests(unittest.TestCase):
    def disagreement(self):
        e=event('2488421','2026-11-06','AB Gladsaxe','Vendsyssel',(2,0),True)
        e['score_conflict']=True
        e['result_dispute']={'status':'pending_independent_confirmation',
             'stored_score':[2,0],'official_score':[3,0],
             'official_source':'DBU official fixture table',
             'official_match_id':'176500','checked_at':NOW.isoformat()}
        return e

    def test_two_sources_confirm_different_score_without_erasing_old_value(self):
        e=self.disagreement()
        new=api('2488421',4683,'2026-2027','2026-11-06',
                'AB Gladsaxe','Vendsyssel',(3,0))
        status=verify_one(e,'dk2',new,NOW)
        self.assertEqual(status,'verified_two_source')
        self.assertTrue(verified_event(e))
        self.assertEqual(e['id'],'2488421')
        self.assertEqual((e['home_score'],e['away_score']),(3,0))
        self.assertEqual(e['result_dispute']['stored_score'],[2,0])
        self.assertEqual(e['result_dispute']['status'],'resolved_two_source_agreement')
        self.assertFalse(e['score_conflict'])
        self.assertEqual(e['result_source'],'DBU official + TheSportsDB exact original ID')

    def test_provider_does_not_agree_official_result(self):
        e=self.disagreement()
        new=api('2488421',4683,'2026-2027','2026-11-06',
                'AB Gladsaxe','Vendsyssel',(4,0))
        self.assertEqual(verify_one(e,'dk2',new,NOW),'source_disagreement')
        self.assertTrue(e['score_conflict'])
        self.assertFalse(verified_event(e))
        self.assertEqual((e['home_score'],e['away_score']),(2,0))

    def test_round_snapshot_does_not_erase_conflicted_original(self):
        original=event('2488421','2026-11-06','AB Gladsaxe','Vendsyssel',(2,0),True)
        known={'2488421':original}
        new={**original,'home_score':3,'away_score':0,
             'result_verified':True,'match_status':'FT'}
        save_match(known,new)
        self.assertEqual((known['2488421']['home_score'],known['2488421']['away_score']),(2,0))
        self.assertTrue(known['2488421']['score_conflict'])
        self.assertFalse(known['2488421']['result_verified'])
        again=known['2488421']['result_dispute'].copy()
        save_match(known,new)
        self.assertEqual(known['2488421']['result_dispute'],again)

    def test_recovery_prioritizes_dispute_without_cross_id_substitution(self):
        e=self.disagreement()
        old=event('2488341','2026-07-24','Vejle','AB Gladsaxe',(2,2),True)
        doc={'schema':1,'season':'2026-2027','leagues':{
          'no':{'events':[]},'nl':{'events':[]},'dk2':{'events':[old,e]}}}
        source=api('2488421',4683,'2026-2027','2026-11-06',
                   'AB Gladsaxe','Vendsyssel',(3,0))
        calls=[]
        def fetch(id):calls.append(id);return [source]
        report=recover(doc,fetch,NOW,{'no':0,'nl':0,'dk2':1})
        self.assertEqual(calls,['2488421'])
        self.assertEqual(report['resolved_disputes'],1)
        self.assertEqual(report['verified'],1)
        self.assertFalse(old['result_verified'])

class CC0EvidenceTests(unittest.TestCase):
    def test_only_explicit_ft_is_valid_evidence(self):
        raw={'name':'Netherlands Eredivisie 2026/27',
             'matches':[{'date':'2026-08-07','team1':'SC Cambuur-Leeuwarden',
                         'team2':'SBV Excelsior','score':{'ht':[0,3],'ft':[0,4]}}]}
        new=parsed(raw,'2026-27',NOW)[0]
        self.assertTrue(verified_event(new))
        old=[event('2489066','2026-08-07','Cambuur','Excelsior',(0,4),True)]
        values=merge_current(old,[new])
        self.assertEqual(values,(0,0,0))
        self.assertEqual(old[0]['id'],'2489066')
        self.assertTrue(verified_event(old[0]))
        self.assertEqual(old[0]['result_source'],'OpenFootball CC0 matching existing score')
        raw['matches'][0]['score']=[0,4]
        unreliable=parsed(raw,'2026-27',NOW)[0]
        self.assertFalse(verified_event(unreliable))
    def test_conflicting_cc0_score_does_not_confirm(self):
        earlier=[event('2489066','2026-08-07','Cambuur','Excelsior',(1,4),True)]
        next=[{'id':'ofnl:1','date':'2026-08-07','home':'Cambuur','away':'Excelsior',
               'finished':True,'home_score':0,'away_score':4,'result_verified':True}]
        self.assertEqual(merge_current(earlier,next),(0,0,1))
        self.assertTrue(earlier[0]['score_conflict'])
        self.assertFalse(earlier[0]['result_verified'])

class DBUEvidenceTests(unittest.TestCase):
    def test_official_table_confirmation_preserves_original_id(self):
        document={'schema':1,'season':'2026-2027','leagues':{
            'dk2':{'source_season':'2026-2027','events':[
              event('2488341','2026-09-18','Kolding','Hillerød',(1,1),True)]}}}
        html='''<html><h1>Kampprogram Kampnr</h1><table>
        <tr><th>Kampnr</th><th>Dato</th><th>Tid</th><th>Hjemme</th><th>Ude</th><th>Resultat</th></tr>
        <tr><td>169493</td><td>18-09 2026</td><td>19:00</td>
        <td>Kolding IF</td><td>Hillerød Fodbold</td><td>1 - 1</td></tr></table></html>'''
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'season.json'
            path.write_text(json.dumps(document))
            actual=collect_dbu(path,lambda _:html,NOW)
            row=actual['leagues']['dk2']['events'][0]
            self.assertEqual(row['id'],'2488341')
            self.assertTrue(verified_event(row))
            self.assertEqual(actual['leagues']['dk2']['dbu_official']['verified_results'],1)
            self.assertTrue(actual['leagues']['dk2']['dbu_official']['result_evidence_v1'])
    def test_official_score_on_other_id_cannot_fill_missing_result(self):
        document={'schema':1,'season':'2026-2027','leagues':{
            'dk2':{'source_season':'2026-2027','events':[
              event('2488341','2026-09-18','Kolding','Hillerød')]}}}
        html='''<html><h1>Kampprogram Kampnr</h1><table>
        <tr><th>Kampnr</th><th>Dato</th><th>Tid</th><th>Hjemme</th><th>Ude</th><th>Resultat</th></tr>
        <tr><td>169493</td><td>18-09 2026</td><td>19:00</td>
        <td>Kolding IF</td><td>Hillerød Fodbold</td><td>1 - 1</td></tr></table></html>'''
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'season.json';path.write_text(json.dumps(document))
            result=collect_dbu(path,lambda _:html,NOW)
            self.assertFalse(verified_event(result['leagues']['dk2']['events'][0]))
            self.assertEqual(result['leagues']['dk2']['dbu_official']['unconfirmed_cross_ids'],1)
            self.assertIsNone(result['leagues']['dk2']['events'][0]['home_score'])

if __name__=='__main__':
    unittest.main()
