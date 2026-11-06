import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from scripts.collect_openfootball_nl import canonical,club,collect,merge_current,parsed
from scripts.build_expansion_reliability import build,metrics


class OpenFootballNLTests(unittest.TestCase):
    NOW=dt.datetime(2026,11,6,17,tzinfo=dt.timezone.utc)

    def test_club_aliases_and_conflicts_do_not_duplicate(self):
        self.assertEqual(club('AFC Ajax'),'Ajax')
        self.assertEqual(club('Feyenoord Rotterdam'),'Feyenoord')
        self.assertEqual(club("FC Twente '65"),'Twente')
        records=[{'id':'tsdb01','date':'2026-08-07','home':'Cambuur',
                  'away':'Excelsior','finished':True,'home_score':0,'away_score':4}]
        copy=[{'id':'ofnl:1','date':'2026-08-07','home':'Cambuur',
               'away':'Excelsior','finished':True,'home_score':0,'away_score':4},
              {'id':'ofnl:2','date':'2026-08-07','home':'Cambuur',
               'away':'Excelsior','finished':True,'home_score':5,'away_score':4},
              {'id':'ofnl:3','date':'2026-09-03','home':'Ajax',
               'away':'PSV Eindhoven','finished':True,'home_score':1,'away_score':0}]
        added,updated,conflicts=merge_current(records,copy)
        self.assertEqual((added,updated,conflicts),(1,0,1))
        self.assertEqual(len(records),2)
        self.assertEqual(records[0]['id'],'tsdb01')

    def test_no_future_results_or_wrong_league(self):
        raw={'name':'Netherlands Eredivisie 2026/27','matches':[
            {'round':'Matchday 1','date':'2026-08-07','team1':'SC Cambuur-Leeuwarden',
             'team2':'SBV Excelsior','score':{'ft':[0,4]}},
            {'round':'Matchday 20','date':'2027-01-07','team1':'AFC Ajax',
             'team2':'PSV','score':{'ft':[9,0]}}
        ]}
        result=parsed(raw,'2026-27',self.NOW)
        self.assertEqual(len(result),2)
        self.assertTrue(result[0]['finished'])
        self.assertFalse(result[1]['finished'])
        self.assertIsNone(result[1]['home_score'])
        with self.assertRaises(ValueError):
            parsed({'name':'Bundesliga','matches':[]},'2026-27',self.NOW)

    def test_current_merge_archival_persistence_and_daily_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            season=Path(tmp)/'season.json'
            archive=Path(tmp)/'nl_history.json'
            season.write_text(json.dumps({'schema':1,'season':'2026-2027',
                'leagues':{'nl':{'events':[{
                    'id':'official','date':'2026-08-07','home':'Cambuur',
                    'away':'Excelsior','home_score':0,'away_score':4,'finished':True}]}}}),
                encoding='utf8')
            calls=[]
            def fetch(path):
                calls.append(path)
                if path=='2026-27/nl.1.json':
                    return {'name':'Netherlands Eredivisie 2026/27','matches':[
                        {'date':'2026-08-07','team1':'SC Cambuur-Leeuwarden',
                         'team2':'SBV Excelsior','score':{'ft':[0,4]}},
                        {'date':'2026-09-01','team1':'AFC Ajax',
                         'team2':'PSV','score':{'ft':[1,2]}}
                    ]}
                season_year=path[:4]
                return {'name':f'Netherlands Eredivisie {season_year}','matches':[
                    {'date':f'{season_year}-08-13','team1':'AFC Ajax','team2':'PSV',
                     'score':{'ft':[3,1]}}
                ]}
            doc,arc=collect(season,archive,fetch,now=self.NOW)
            self.assertEqual(len(calls),6)
            self.assertEqual(len(doc['leagues']['nl']['events']),2)
            self.assertEqual(len(arc['seasons']),5)
            self.assertTrue(all(v['complete'] is False for v in arc['seasons'].values()))
            again,_=collect(season,archive,fetch,now=self.NOW+dt.timedelta(hours=2))
            self.assertEqual(len(calls),6)
            self.assertEqual(len(again['leagues']['nl']['events']),2)


class LeagueReliabilityTests(unittest.TestCase):
    NOW=dt.datetime(2026,11,6,17,tzinfo=dt.timezone.utc)

    def test_insufficient_evidence_is_not_a_positive_brier(self):
        report=build({'leagues':{
          'nl':{'name':'Eredivisie','events':[], 'partial':True},
          'dk2':{'name':'1. Division','events':[], 'partial':True},
          'no':{'name':'Eliteserien','events':[], 'partial':True}}},
          {},{},self.NOW)
        for lid in ('nl','dk2','no'):
            self.assertEqual(report['leagues'][lid]['best_available_1x2']['n'],0)
            self.assertIsNone(report['leagues'][lid]['best_available_1x2']['brier'])
            self.assertEqual(report['leagues'][lid]['quality'],
                             'insufficient_independent_holdout')

    def test_walk_forward_cannot_use_future_or_same_day_games(self):
        events=[]
        for i in range(40):
            date=(dt.date(2026,8,1)+dt.timedelta(days=i)).isoformat()
            events.append({'id':str(i),'date':date,'home':'PSV','away':'Ajax',
                           'home_score':1,'away_score':0,'finished':True})
        report=metrics([],events,'current')
        self.assertGreater(report['n'],0)
        base=metrics([],events[:30],'current')
        self.assertEqual(base['n'],0)
        self.assertEqual(report['status'],'current_season_walk_forward_not_independent')
        self.assertIsNotNone(report['baseline_brier'])


if __name__=='__main__':
    unittest.main()
