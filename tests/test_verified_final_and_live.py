"""Regression tests: no live-score may settle a signed forecast."""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from scripts.match_status import final_confirmed, verified_event
from scripts.update_data import parse_event
from scripts.collect_expanded_leagues import parse_event as parse_expanded
from scripts.record_predictions import write_ledger
from scripts.restore_published_state import merge_ledger

NOW=dt.datetime(2026,11,6,21,0,tzinfo=dt.timezone.utc)

def raw(status='2H',home='0',away='0',kickoff='2026-11-06T18:00:00'):
    return {'idEvent':'2481875','idLeague':'4340','strSeason':'2026-2027',
            'strHomeTeam':'Silkeborg IF','strAwayTeam':'Lyngby',
            'dateEvent':'2026-11-06','strTimestamp':kickoff,
            'intHomeScore':home,'intAwayScore':away,'strStatus':status,'intRound':'14'}

class VerifiedFinalTests(unittest.TestCase):
    def test_interim_score_never_finished(self):
        self.assertFalse(final_confirmed(raw('2H'),NOW))
        e=parse_event(raw('2H'),'dk')
        self.assertFalse(e['finished'])
        self.assertEqual(e['live_home_score'],0)
        self.assertIsNone(e['home_score'])
        self.assertFalse(verified_event(e))

    def test_missing_status_or_premature_ft_is_not_a_final(self):
        self.assertFalse(final_confirmed(raw(''),NOW))
        self.assertFalse(final_confirmed(raw('FT',kickoff='2026-11-06T20:45:00'),NOW))
        self.assertFalse(final_confirmed(raw('POST'),NOW))
        self.assertFalse(final_confirmed(raw('FT',home='',away='0'),NOW))

    def test_verified_full_time(self):
        self.assertTrue(final_confirmed(raw('FT',home='1'),NOW))
        e=parse_event(raw('FT',home='1'),'dk')
        self.assertTrue(e['finished'])
        self.assertTrue(e['result_verified'])
        self.assertEqual(e['home_score'],1)

    def test_expanded_league_does_not_settle_halftime(self):
        r=raw('HT')
        r.update({'idLeague':'4337','strSeason':'2026-2027','dateEvent':'2026-11-06',
                  'strHomeTeam':'Ajax','strAwayTeam':'PSV','intRound':'14'})
        e=parse_expanded(r,'nl',NOW.date())
        self.assertFalse(e['finished'])
        self.assertIsNone(e['home_score'])

    def test_old_wrong_result_quarantined_and_replacement_verified(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'ledger.json'
            key='dk:2026-2027:2481875'
            original={'key':key,'date':'2026-11-06','home_score':0,'away_score':0,
                      'resolved_at':'2026-11-06T18:52:28+00:00'}
            path.write_text(json.dumps({'schema':1,'predictions':[{
                'key':key,'league':'dk','date':'2026-11-06','home':'Silkeborg IF',
                'away':'Lyngby','markets':{'over_2_5':.6}}],
                'settlements':[original]}))
            event={'id':'2481875','date':'2026-11-06','home':'Silkeborg IF',
                   'away':'Lyngby','home_score':1,'away_score':0,
                   'finished':True,'result_verified':True,'match_status':'FT'}
            season={'season':'2026-2027','leagues':{'dk':{'events':[event]}}}
            result=write_ledger(season,{},path,now=NOW+dt.timedelta(days=1))
            self.assertEqual(len(result['quarantined_settlements']),1)
            self.assertEqual(result['quarantined_settlements'][0]['home_score'],0)
            self.assertEqual(result['settlements'][0]['home_score'],1)
            self.assertTrue(result['settlements'][0]['verified_final'])
            again=write_ledger(season,{},path,now=NOW+dt.timedelta(days=1))
            self.assertEqual(len(again['quarantined_settlements']),1)
            self.assertEqual(len(again['settlements']),1)
            # An old Pages snapshot must never resurrect the 0-0.
            merged=merge_ledger(again,{'schema':1,'predictions':[],
                                       'settlements':[original]})
            self.assertEqual(len(merged['settlements']),1)
            self.assertEqual(merged['settlements'][0]['home_score'],1)

    def test_unverified_final_remains_unsettled(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'ledger.json'
            key='dk:2026-2027:2481875'
            original={'key':key,'date':'2026-11-06','home_score':0,'away_score':0}
            path.write_text(json.dumps({'schema':1,'predictions':[{'key':key}],
                                         'settlements':[original]}))
            event={'id':'2481875','date':'2026-11-06','finished':False,
                   'home_score':None,'away_score':None,'match_status':'2H'}
            result=write_ledger({'season':'2026-2027','leagues':{'dk':{'events':[event]}}},{},
                                path,now=NOW)
            self.assertFalse(result['settlements'])
            self.assertEqual(result['quarantined_settlements'][0]['home_score'],0)

if __name__=='__main__':
    unittest.main()
