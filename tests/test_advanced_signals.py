import datetime as dt
import tempfile
import unittest
from pathlib import Path

from scripts.collect_advanced_signals import collect,extract_match,new_report
from scripts.build_shots_research import build,timeline,team_key


class AdvancedSignalsTests(unittest.TestCase):
    NOW=dt.datetime(2026,11,6,12,tzinfo=dt.timezone.utc)

    def match(self,mid='m1',date='2026-11-01T17:00:00+00:00'):
        return {'id':mid,'status':'finished','kickoff_at':date,'home_team':'Porto',
                'away_team':'Benfica','dataset_url':'https://cornerflick.com/football/primeira-liga/matches/'+mid+'/data.json'}

    def raw(self,xg=False):
        stats=[
            {'label':'Shots','home':13,'away':8},
            {'label':'Shots on Target','home':6,'away':3},
        ]
        if xg:stats.append({'label':'Expected Goals','home':1.3,'away':.6})
        return {'meta':{'license':'CC BY 4.0'},'statistics':stats}

    def test_collect_limited_attributed_and_cached_not_zero_xg(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'obs.json'
            urls=[]
            def fetch(url):
                urls.append(url)
                if url.endswith('season.json'):
                    return {'meta':{'license':'CC BY 4.0'},
                            'matches':[self.match('m1'),self.match('m2')]}
                return self.raw()
            a=collect(path,now=self.NOW,max_per_league=1,fetcher=fetch,
                      allow=lambda _:True,sleep=lambda _:None)
            self.assertEqual(len(a['leagues']['pt']['records']),1)
            record=a['leagues']['pt']['records'][0]
            self.assertEqual(record['shots_on_target'],[6.,3.])
            self.assertIsNone(record['xg'])
            self.assertIn('Cornerflick',a['source']['attribution'])
            self.assertEqual(len(urls),4) # 2 season indexes, 2 sampled matches
            b=collect(path,now=self.NOW+dt.timedelta(hours=1),max_per_league=1,
                      fetcher=fetch,allow=lambda _:True,sleep=lambda _:None)
            self.assertEqual(len(urls),4) # daily gate prevents extra traffic
            c=collect(path,now=self.NOW+dt.timedelta(hours=23),max_per_league=1,
                      fetcher=fetch,allow=lambda _:True,sleep=lambda _:None)
            self.assertEqual(len(c['leagues']['pt']['records']),2)
            self.assertEqual(len(c['leagues']['dk']['records']),2)

    def test_invalid_shot_counts_not_accepted(self):
        raw=self.raw(xg=True)
        raw['statistics'][1]['home']=15
        with self.assertRaises(ValueError):
            extract_match(self.match(),raw,'pt',self.NOW)

    def test_source_denied_does_not_fetch_or_manufacture_stats(self):
        with tempfile.TemporaryDirectory() as folder:
            calls=[]
            def fetch(url):
                calls.append(url)
                raise AssertionError('Must not request forbidden source')
            r=collect(Path(folder)/'data.json',now=self.NOW,
                      fetcher=fetch,allow=lambda _:False,sleep=lambda _:None)
            self.assertEqual(calls,[])
            self.assertEqual(r['leagues']['pt']['status'],'source_unavailable')
            self.assertEqual(r['leagues']['pt']['records'],[])

    def test_descriptive_shots_use_only_prior_observed_games(self):
        rec={'date':'2026-11-01','home':'Porto','away':'Benfica',
             'shots_on_target':[6,3],
             'first_observed_at':'2026-11-05T12:00:00+00:00'}
        signals={'leagues':{'pt':{'records':[rec],'status':'limited_sample'}}}
        season={'leagues':{'pt':{'events':[
            {'id':'1','date':'2026-11-09','home':'Porto','away':'Benfica',
             'finished':False}]}}}
        report=build(signals,season,self.NOW)
        self.assertFalse(report['production_model_changed'])
        self.assertEqual(report['leagues']['pt']['sample_matches'],1)
        self.assertEqual(report['leagues']['pt']['xg_recorded'],0)
        self.assertEqual(report['leagues']['pt']['candidates'][0]['status'],'insufficient_sample')
        self.assertEqual(len(timeline([rec],team_key('Porto'),'2026-11-03',self.NOW)),1)
        self.assertEqual(len(timeline([rec],team_key('Porto'),'2026-11-01',self.NOW)),0)
        earlier=self.NOW-dt.timedelta(days=2)
        self.assertEqual(len(timeline([rec],team_key('Porto'),'2026-11-09',earlier)),0)

    def test_three_prior_samples_are_observational_only(self):
        recs=[]
        for day in (1,2,3):
            recs.append({'date':f'2026-11-{day:02d}','home':'Porto','away':'Benfica',
                'shots_on_target':[5,2],
                'first_observed_at':'2026-11-05T12:00:00+00:00'})
        s={'leagues':{'pt':{'records':recs,'status':'limited_sample'}}}
        season={'leagues':{'pt':{'events':[{'id':'a','date':'2026-11-10',
                                      'home':'Porto','away':'Benfica','finished':False}]}}}
        a=build(s,season,self.NOW)['leagues']['pt']['candidates'][0]
        self.assertEqual(a['status'],'observational_signal_only')
        self.assertEqual(a['pressure_home'],5.0)
        self.assertEqual(a['pressure_away'],2.0)
        self.assertFalse(a['adjusts_probability'])


if __name__=='__main__':
    unittest.main()
