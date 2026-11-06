import copy
import datetime as dt
import unittest

from scripts.build_feature_impact import (
    CANDIDATES, clamp, elo_surprises, features, predict_rates,
    multiclass_brier, gain_interval, evaluate_league, outcome_points,
)

def game(day,home,away,hs,aws,ident):
    return {'id':ident,'date':day,'home':home,'away':away,
            'home_score':hs,'away_score':aws,'finished':True}

class FeatureImpactTests(unittest.TestCase):
    def test_rest_is_only_prior_league_matches(self):
        previous=[
            game('2026-10-10','Home','A',2,1,'1'),
            game('2026-10-14','Away','B',0,2,'2'),
            game('2026-10-17','Home','C',3,1,'3'),
            game('2026-10-21','Away','D',1,0,'4'),
            game('2026-10-25','Home','E',1,0,'5'),
            game('2026-10-28','Away','F',2,1,'6'),
        ]
        surpr=elo_surprises(previous)
        x=features(previous,'2026-11-01','Home','Away',surpr)
        self.assertEqual(x['rest_days_home'],7)
        self.assertEqual(x['rest_days_away'],4)
        self.assertAlmostEqual(x['rest_edge'],3/7,places=5)
        self.assertTrue(x['form_available'])
        self.assertEqual(x['league_matches_last14_home'],1)
        self.assertEqual(x['league_matches_last14_away'],2)

    def test_no_same_day_or_future_leakage(self):
        old=[
            game('2026-08-01','Home','A',1,0,'a'),
            game('2026-08-10','Away','B',2,1,'b'),
            game('2026-08-11','Home','C',2,2,'c'),
            game('2026-08-12','Away','D',1,1,'d'),
            game('2026-08-15','Home','E',3,0,'e'),
            game('2026-08-20','Away','F',0,0,'f'),
        ]
        target='2026-08-23'
        base=features(old,target,'Home','Away',elo_surprises(old))
        mod=copy.deepcopy(old)+[
            game('2026-08-23','Home','Away',22,0,'today'),
            game('2026-08-24','A','B',5,0,'future')]
        now=features(mod,target,'Home','Away',elo_surprises(mod))
        self.assertEqual(base,now)

    def test_missing_data_is_neutral_not_fake_fatigue(self):
        result=features([], '2026-08-01','A','B',{})
        self.assertEqual(result['rest_edge'],0)
        self.assertEqual(result['form_edge'],0)
        self.assertFalse(result['rest_available'])
        self.assertFalse(result['form_available'])

    def test_fixed_candidates_and_probability_calculations(self):
        f={'rest_edge':.5,'form_edge':-.3}
        lh,la=predict_rates(1.5,1.1,f,'baseline')
        self.assertEqual((lh,la),(1.5,1.1))
        adjusted=predict_rates(1.5,1.1,f,'rest')
        self.assertGreater(adjusted[0],lh)
        self.assertLess(adjusted[1],la)
        self.assertEqual(set(CANDIDATES),{'baseline','rest','strength_adjusted_form','rest_plus_form'})
        self.assertAlmostEqual(multiclass_brier([1,0,0],0),0)
        self.assertAlmostEqual(multiclass_brier([0,1,0],0),2)
        a=[('2026-09-01',[.5,.3,.2],0)]
        b=[('2026-09-01',[.6,.25,.15],0)]
        self.assertEqual(len(gain_interval(a,b)),2)

    def test_split_selection_never_reads_holdout_results(self):
        years=['2021-2022','2022-2023','2023-2024','2024-2025','2025-2026']
        seasons={}
        for year in years:
            start=dt.date(int(year[:4]),8,1)
            events=[]
            for i in range(145):
                date=(start+dt.timedelta(days=i//4)).isoformat()
                events.append(game(date,f'Team{i%8}',f'Team{(i+3)%8}',
                                   (i//2)%3,(i//3)%3,f'{year}:{i}'))
            seasons[year]={'events':events}
        quality={'seasons':{year:{'complete':True} for year in years}}
        original=evaluate_league(seasons,quality)
        changed=copy.deepcopy(seasons)
        for e in changed['2025-2026']['events']:
            e['home_score']=0
            e['away_score']=8
        rerun=evaluate_league(changed,quality)
        self.assertEqual(original['selected_on_2024_25'],rerun['selected_on_2024_25'])
        self.assertEqual(original['variants']['rest']['fit'],rerun['variants']['rest']['fit'])
        self.assertEqual(original['feature_coverage']['fit'],rerun['feature_coverage']['fit'])
        self.assertNotEqual(original['variants']['baseline']['holdout']['brier'],
                            rerun['variants']['baseline']['holdout']['brier'])

if __name__=='__main__':
    unittest.main()
