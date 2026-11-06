import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from scripts.collect_cross_competitions import canonical, collect, parse_event
from scripts.build_schedule_context import context, build
from scripts.collect_prematch_lineups import validate, collect as collect_lineups

class CrossCompetitionTests(unittest.TestCase):
    def test_name_mapping_and_source_verification(self):
        self.assertEqual(canonical('F.C. København'),'FC Copenhagen')
        self.assertEqual(canonical('FC Porto'),'Porto')
        self.assertEqual(canonical('Sporting Lisbon'),'Sporting CP')
        e={'idEvent':'abc','idLeague':'4480','strSeason':'2025-2026',
           'dateEvent':'2025-10-22','strHomeTeam':'FC Porto',
           'strAwayTeam':'Ajax','intHomeScore':'2','intAwayScore':'1'}
        p=parse_event(e,'2025-2026','uefa_cl','2025-10-24')
        self.assertTrue(p['finished'])
        self.assertEqual(p['home'],'Porto')
        self.assertFalse(p['league_model_eligible'])
        self.assertIsNone(parse_event({**e,'idLeague':'4340'},'2025-2026','uefa_cl','2025-10-24'))
        self.assertFalse(parse_event(e,'2025-2026','uefa_cl','2025-10-22')['finished'])

    def test_round_checkpoint_and_source_conflict(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'cross.json'
            def fetch(key,season,rnd):
                e={'idEvent':f'{key}-{season}-{rnd}','idLeague':{
                   'uefa_cl':'4480','uefa_el':'4481','uefa_ecl':'5071',
                   'pt_cup':'4510','pt_league_cup':'4509'}[key],
                   'strSeason':season,'dateEvent':season[:4]+'-10-02',
                   'strHomeTeam':'Benfica','strAwayTeam':'Ajax',
                   'intHomeScore':'1','intAwayScore':'0'}
                return [e]
            a=collect(path,max_calls=3,pause=0,fetcher=fetch,
                      now=dt.datetime(2026,11,6,tzinfo=dt.timezone.utc))
            self.assertEqual(len(a['events']),3)
            b=collect(path,max_calls=2,pause=0,fetcher=fetch,
                      now=dt.datetime(2026,11,6,tzinfo=dt.timezone.utc))
            self.assertEqual(len(b['events']),5)
            self.assertEqual(b['coverage'],'partial')
            self.assertEqual(sum(len(v['checked_rounds']) for v in b['competitions'].values()),5)

    def test_cup_changes_known_rest_not_earlier_results(self):
        league=[{'id':'lg','date':'2026-10-01','home':'Porto','away':'Braga',
                 'home_score':1,'away_score':0,'finished':True}]
        cup={'id':'cup','date':'2026-10-09','home':'FC Porto','away':'Other',
             'competition':'UEFA Europa League','competition_type':'european',
             'home_score':2,'away_score':0,'finished':True}
        target={'id':'next','date':'2026-10-12','home':'Porto','away':'Benfica'}
        no_cup=context(target,league,[])
        yes_cup=context(target,league,[cup])
        self.assertEqual(no_cup['home']['days_since_last_known_match'],11)
        self.assertEqual(yes_cup['home']['days_since_last_known_match'],3)
        self.assertEqual(yes_cup['home']['cup_europe_last_21'],1)
        self.assertTrue(yes_cup['partial_coverage'])
        bad={**cup,'date':'2026-10-12'}
        self.assertEqual(context(target,league,[bad])['home']['days_since_last_known_match'],11)

    def test_pre_kickoff_lineup_requires_all_starters_and_timestamp(self):
        event={'id':'abc','utc':'2026-11-07T19:00:00Z'}
        now=dt.datetime(2026,11,7,18,0,tzinfo=dt.timezone.utc)
        def item(i,home):
            return {'idEvent':'abc','idPlayer':str(i)+home,'strHome':home,
                    'strSubstitute':'No'}
        small={'lineup':[item(i,'Yes') for i in range(5)]}
        self.assertEqual(validate(event,small,now)['status'],
                         'partial_lineup_not_for_absence_inference')
        complete={'lineup':[item(i,'Yes') for i in range(11)]+
                   [item(i,'No') for i in range(11)]}
        self.assertEqual(validate(event,complete,now)['status'],'observed_complete_pre_kickoff')
        self.assertEqual(validate(event,complete,now+dt.timedelta(hours=1))['status'],
                         'unverifiable_pre_kickoff_timestamp')
        self.assertEqual(validate({**event,'utc':''},complete,now)['status'],
                         'unverifiable_pre_kickoff_timestamp')

    def test_pre_kickoff_collector_does_not_fetch_after_kickoff(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'prematch.json'
            calls=[]
            def fetch(id):
                calls.append(id)
                return {'lineup':None}
            season={'leagues':{'dk':{'events':[
                 {'id':'1','date':'2026-11-07','utc':'2026-11-07T22:00:00Z','finished':False,
                  'home':'Copenhagen','away':'Odense'},
                 {'id':'2','date':'2026-11-06','utc':'2026-11-06T17:00:00Z','finished':False,
                  'home':'Silkeborg','away':'Lyngby'}]}}}
            now=dt.datetime(2026,11,6,20,0,tzinfo=dt.timezone.utc)
            x=collect_lineups(season,output=p,now=now,fetch=fetch,max_calls=5)
            self.assertEqual(calls,['1'])
            self.assertEqual(x['observations'][0]['status'],'unavailable')
            self.assertEqual(x['observations'][0]['id'],'1')

if __name__=='__main__':
    unittest.main()
