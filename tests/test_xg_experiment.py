import datetime as dt
import math
import unittest

from scripts.build_xg_experiment import (
    build, sample_for_team, candidate_rates, evaluate, REVIEW_MIN
)


class ShadowXGTests(unittest.TestCase):
    now=dt.datetime(2026,11,6,16,0,tzinfo=dt.timezone.utc)

    def samples(self,observed='2026-11-05T09:00:00+00:00'):
        return [{'source_id':str(i),'date':f'2026-11-0{i}',
                 'home':'Porto','away':'Benfica','xg':[1.6,1.1],
                 'first_observed_at':observed} for i in (1,2,3)]

    def source(self,observed=None):
        return {'leagues':{'pt':{'records':self.samples(observed or '2026-11-05T09:00:00+00:00')},
                           'dk':{'records':[]}}}

    def season(self,finished=False):
        event={'id':'game42','date':'2026-11-10','home':'FC Porto',
               'away':'Benfica','finished':finished}
        if finished:event.update({'home_score':2,'away_score':1})
        return {'season':'2026-2027','leagues':{'pt':{'events':[event]},
                                              'dk':{'events':[]}}}

    def model(self):
        return {'generated_at':'2026-11-06T15:00:00+00:00',
                'leagues':{'pt':{'predictions':{'game42':{
                    'lambdaH':1.5,'lambdaA':1.1,'p1':.5,'px':.2,'p2':.3}}},
                           'dk':{'predictions':{}}}}

    def test_future_forecast_recorded_once_and_settled_later(self):
        r,l=build(self.source(),self.season(),self.model(),now=self.now)
        self.assertFalse(r['production_model_changed'])
        self.assertEqual(len(l['predictions']),1)
        self.assertEqual(len(l['settlements']),0)
        p=l['predictions'][0]
        self.assertEqual(p['xg_samples_home'],3)
        self.assertAlmostEqual(sum(p['xg_1x2']),1,places=5)
        self.assertEqual(r['leagues']['pt']['paired_evaluation']['n'],0)
        unchanged,again=build(self.source(),self.season(),self.model(),l,now=self.now)
        self.assertEqual(again['predictions'],l['predictions'])
        after=dt.datetime(2026,11,11,8,tzinfo=dt.timezone.utc)
        done,settled=build(self.source(),self.season(True),
                           {'generated_at':'2026-11-11T06:00:00+00:00','leagues':{}},
                           again,now=after)
        self.assertEqual(done['total_shadow_predictions'],1)
        self.assertEqual(done['total_shadow_settlements'],1)
        self.assertEqual(done['leagues']['pt']['paired_evaluation']['n'],1)
        self.assertEqual(done['leagues']['pt']['paired_evaluation']['status'],
                         'collecting_or_inconclusive')
        self.assertFalse(done['leagues']['pt']['paired_evaluation']['model_proven'])
        again_done,again_settled=build(self.source(),self.season(True),{},settled,now=after)
        self.assertEqual(len(again_settled['settlements']),1)

    def test_post_match_observations_cannot_enter_a_prior_forecast(self):
        future_obs=self.source('2026-11-11T10:00:00+00:00')
        r,l=build(future_obs,self.season(),self.model(),now=self.now)
        self.assertEqual(len(l['predictions']),0)
        self.assertEqual(r['leagues']['pt']['status'],'blocked_insufficient_club_xg_history')

    def test_missing_or_fake_xg_never_zero_fills(self):
        rows=self.samples()
        rows[0]['xg']=None
        rows[1]['xg']=[float('nan'),1.1]
        self.assertEqual(len(sample_for_team(rows,'porto','2026-11-10',self.now)),1)
        r,l=build({'leagues':{'pt':{'records':rows}}},
                  self.season(),self.model(),now=self.now)
        self.assertEqual(len(l['predictions']),0)

    def test_same_day_data_and_duplicate_sources_are_excluded(self):
        rows=self.samples()
        rows.append({**rows[0],'source_id':'1','date':'2026-11-04'})
        rows.append({**rows[0],'source_id':'new','date':'2026-11-10'})
        self.assertEqual(len(sample_for_team(rows,'porto','2026-11-10',self.now)),3)

    def test_candidate_changes_rates_conservatively(self):
        p=candidate_rates(1.5,1.1,[(1.6,1.1)]*3,[(1.1,1.6)]*3)
        self.assertEqual(len(p),2)
        self.assertTrue(all(math.isfinite(x) and .15<=x<=4 for x in p))
        self.assertTrue(all(abs(x-b)<.2 for x,b in zip(p,(1.5,1.1))))

    def test_missing_baseline_or_stale_model_blocks_candidate(self):
        r,l=build(self.source(),self.season(),
                  {'generated_at':'2026-09-01T00:00:00+00:00','leagues':{}},now=self.now)
        self.assertEqual(len(l['predictions']),0)
        self.assertEqual(r['leagues']['pt']['blocked_missing_model'],1)
        self.assertGreater(REVIEW_MIN,30)


if __name__=='__main__':
    unittest.main()
