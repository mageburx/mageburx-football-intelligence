"""Regression: never fabricate matches, source coverage, xG or final scores."""
import datetime as dt
import unittest
from scripts.build_data_coverage import build

NOW=dt.datetime(2026,11,7,0,15,tzinfo=dt.timezone.utc)
LIDS=('pt','dk','nl','dk2','no')

def fixture(id,date,finished=False,result_verified=False,score=None):
    h,a=score if score else (None,None)
    return {'id':id,'date':date,'home':'Home','away':'Away','round':1,
            'finished':finished,'result_verified':result_verified,
            'match_status':'FT' if result_verified else '2H' if finished else 'NS',
            'home_score':h,'away_score':a}

def inputs():
    leagues={lid:{'source_season':'2026-2027','events':[],
                  'partial':True,'collection':{'verified_rounds':[1,2]},
                  'openfootball':{},'dbu_official':{},'fantasy_research':{}}
             for lid in LIDS}
    leagues['no']['source_season']='2026'
    leagues['nl']['events']=[fixture('one','2026-11-05',True,True,(2,0)),
                            fixture('two','2026-11-05',True,False,(1,0))]
    leagues['nl']['openfootball']={'superseded':[{'id':'old','replacement_id':'one'}],
                                    'conflicts':0,'source_fixture_count':306}
    seasons={str(y)+'-'+str(y+1):{'events':[fixture(str(i),'2025-05-04') for i in range(2)],
                                   'expected_games':2,'complete':True}
             for y in range(2021,2026)}
    return ({'schema':1,'season':'2026-2027','updated_at':NOW.isoformat(),'leagues':leagues},
            {'leagues':{'pt':{'seasons':seasons},'dk':{'seasons':seasons}}},
            {'seasons':{'2021-2022':{'events':[],'expected_games':306,'complete':False}}},
            {'leagues':{'pt':{'sample_checked':2,'match_count':91,
                              'stats_fields_validated':{'Shots':1}}}},
            {'leagues':{'pt':{'shots_recorded':1,'xg_recorded':0}}})

class CoverageTests(unittest.TestCase):
    def test_partial_score_cannot_count_as_verified(self):
        args=inputs()
        result=build(*args,now=NOW)
        nl=result['leagues']['nl']
        self.assertEqual(nl['inventory']['observed_unique'],2)
        self.assertEqual(nl['inventory']['verified_final'],1)
        self.assertEqual(nl['inventory']['past_unverified'],1)
        self.assertEqual(nl['rounds']['verified'],2)
        self.assertEqual(nl['rounds']['unverified_count'],32)
        self.assertEqual(nl['sources']['superseded_signed_ids_preserved'],1)
        self.assertEqual(nl['history']['complete_seasons'],0)
        self.assertEqual(result['production_model_changed'],False)
    def test_reference_count_is_not_automatic_full_coverage(self):
        args=list(inputs())
        args[0]['leagues']['nl']['events']=[
           {**fixture(str(i),'2026-12-01'),'home':f'Home {i}','away':f'Away {i}'}
           for i in range(306)]
        result=build(*args,now=NOW)
        nl=result['leagues']['nl']
        self.assertEqual(nl['inventory']['expected_reference'],306)
        self.assertEqual(nl['inventory']['difference_reference'],0)
        self.assertEqual(nl['inventory']['status'],'reference_count_reached_not_verified_complete')
        self.assertEqual(nl['status'],'partial')
    def test_sampled_shots_not_certified_complete_xg(self):
        a=inputs()
        result=build(*a,now=NOW)
        pt=result['leagues']['pt']
        self.assertEqual(pt['stats']['status'],'small_sample_only')
        self.assertEqual(pt['stats']['research_xg_recorded'],0)
        self.assertEqual(pt['history']['complete_seasons'],5)
        self.assertIsNone(pt['rounds']['verified'])
        self.assertEqual(pt['rounds']['verification'],'not_persisted')
    def test_source_conflicts_trigger_review_without_mutating_scores(self):
        args=list(inputs())
        orig=args[0]['leagues']['nl']['events'][0].copy()
        args[0]['leagues']['nl']['openfootball']['conflicts']=2
        result=build(*args,now=NOW)
        self.assertEqual(result['leagues']['nl']['status'],'requires_review')
        self.assertEqual(result['leagues']['nl']['sources']['conflicts'],2)
        self.assertEqual(args[0]['leagues']['nl']['events'][0],orig)
        self.assertTrue(any(q['code']=='source_result_conflicts' and q['league']=='nl'
                            for q in result['queue']))
    def test_duplicate_same_day_two_ids_flagged_not_merged(self):
        args=list(inputs())
        args[0]['leagues']['no']['events']=[fixture('a','2026-11-08'),
                                              fixture('b','2026-11-08')]
        result=build(*args,now=NOW)
        no=result['leagues']['no']
        self.assertEqual(no['inventory']['observed_unique'],2)
        self.assertEqual(len(no['inventory']['potential_duplicate_pairs']),1)
        self.assertEqual(no['status'],'partial')
    def test_no_unavailable_league_silently_accepted(self):
        args=list(inputs())
        del args[0]['leagues']['dk2']
        with self.assertRaises(ValueError):
            build(*args,now=NOW)

if __name__=='__main__':
    unittest.main()
