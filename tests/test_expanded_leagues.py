import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from scripts.collect_expanded_leagues import LEAGUES,RateLimit,collect,parse_event
from scripts.update_data import collect as collect_original


class ExtendedLeagueTests(unittest.TestCase):
    START=dt.datetime(2026,11,6,12,tzinfo=dt.timezone.utc)

    def fixture(self,lid,season=None,round_num=1,date=None,home='Home',away='Away',
                score_home='2',score_away='1'):
        cfg=LEAGUES[lid]
        return {'idEvent':f'{lid}:{round_num}:{home}', 'idLeague':str(cfg['id']),
                'strSeason':season or cfg['source_season'],
                'dateEvent':date or ('2026-05-03' if lid=='no' else '2026-10-04'),
                'strHomeTeam':home,'strAwayTeam':away,
                'intRound':str(round_num),'intHomeScore':score_home,
                'intAwayScore':score_away,'strTimestamp':''}

    def snapshot(self):
        return {'schema':1,'season':'2026-2027','leagues':{
            'pt':{'events':[{'id':'oldpt','date':'2026-11-01','home':'Porto',
                             'away':'Braga','finished':True,'home_score':1,'away_score':0}]},
            'dk':{'events':[{'id':'olddk','date':'2026-11-01','home':'AGF',
                             'away':'Brondby','finished':True,'home_score':1,'away_score':1}]}}}

    def test_ids_and_calendar_year_are_distinct(self):
        self.assertEqual({k:v['id'] for k,v in LEAGUES.items()},
                         {'nl':4337,'dk2':4683,'no':4358})
        n=parse_event(self.fixture('no'), 'no',self.START.date())
        self.assertTrue(n['finished'])
        self.assertEqual(n['date'],'2026-05-03')
        self.assertIsNone(parse_event(self.fixture('no',season='2026-2027'),
                                      'no',self.START.date()))
        self.assertIsNone(parse_event(self.fixture('nl',season='2026'), 'nl',
                                      self.START.date()))
        self.assertFalse(parse_event(self.fixture('dk2',date='2026-11-30'),
                                     'dk2',self.START.date())['finished'])
        self.assertIsNone(parse_event(self.fixture('dk2',score_home=None),
                                     'dk2',self.START.date())['home_score'])

    def test_progressive_collection_and_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'season.json'
            path.write_text(json.dumps(self.snapshot()),encoding='utf8')
            attempts=[]
            def fetch(endpoint,params):
                attempts.append((endpoint,params['id'],params['s'],params.get('r')))
                lid=next(k for k,v in LEAGUES.items() if v['id']==params['id'])
                if endpoint=='eventsseason.php':return []
                r=params['r']
                return [self.fixture(lid,round_num=r,home=f'Home{r}',
                                     away=f'Away{r}') for _ in range(LEAGUES[lid]['games_per_round'])]
            a=collect(path,max_calls=6,fetcher=fetch,pause=0,now=self.START)
            self.assertEqual(len(attempts),6)
            self.assertEqual(set(a['leagues']),{'pt','dk','nl','dk2','no'})
            self.assertEqual(a['leagues']['pt']['events'][0]['id'],'oldpt')
            self.assertEqual(a['leagues']['dk']['events'][0]['id'],'olddk')
            self.assertEqual(a['leagues']['nl']['source_season'],'2026-2027')
            self.assertEqual(a['leagues']['no']['source_season'],'2026')
            self.assertTrue(a['leagues']['nl']['partial'])
            self.assertEqual(a['leagues']['dk2']['rounds_ok'],1)
            # Avoid refetching season and round 1 within the daily interval.
            b=collect(path,max_calls=3,fetcher=fetch,pause=0,
                      now=self.START+dt.timedelta(hours=1))
            self.assertEqual(len(attempts),9)
            self.assertEqual(b['leagues']['no']['rounds_ok'],2)

    def test_429_stops_all_requests_and_keeps_previously_collected_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'season.json'
            prior=self.snapshot()
            prior['leagues']['nl']={'events':[{
                'id':'persisted','date':'2026-10-04','home':'Ajax',
                'away':'PSV','finished':True,'home_score':1,'away_score':2}],
                'collection':{'verified_rounds':[],'attempted_rounds':{}}}
            path.write_text(json.dumps(prior),encoding='utf8')
            calls=[]
            def limited(endpoint,params):
                calls.append((endpoint,params))
                raise RateLimit('HTTP 429')
            r=collect(path,max_calls=8,fetcher=limited,pause=0,now=self.START)
            self.assertEqual(len(calls),1)
            self.assertEqual(r['leagues']['nl']['events'][0]['id'],'persisted')
            self.assertTrue(r['leagues']['nl']['partial'])

    def test_original_two_league_refresh_keeps_three_new_leagues(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'season.json'
            original=self.snapshot()
            original['leagues']['no']={'events':[{'id':'no-existing','date':'2026-10-01'}],
                                      'partial':True}
            path.write_text(json.dumps(original),encoding='utf8')
            def fake(lid,rnd):
                return []
            result=collect_original(path,pause=0,max_round=1,fetcher=fake)
            self.assertEqual(result['leagues']['no']['events'][0]['id'],'no-existing')
            self.assertEqual(set(result['leagues']),{'pt','dk','no'})


if __name__=='__main__':
    unittest.main()
