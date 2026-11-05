import copy
import unittest
from scripts.audit_history import audit, audit_season
from scripts.validate_models import audit_league

def fake_game(i,year):
    return {'id':f'match-{year}-{i}','date':f'{year}-08-{(i%28)+1:02d}',
            'home':f'Home{i}','away':f'Away{i}','home_score':i%3,'away_score':i%2,'finished':True}

class IntegrityV41Tests(unittest.TestCase):
    def test_missing_results_not_marked_complete(self):
        a=audit_season('dk','2024-2025',{'events':[fake_game(i,2024) for i in range(192)],
                                        'complete':True,'expected_games':193})
        self.assertFalse(a['complete'])
        self.assertEqual(a['coverage'],round(192/193,4))
        self.assertTrue(a['integrity_ok'])
    def test_duplicate_fixture_and_ids_found(self):
        match=fake_game(1,2022)
        s=audit_season('dk','2022-2023',{'events':[match,copy.deepcopy(match)],
                                         'complete':False,'expected_games':193})
        self.assertFalse(s['integrity_ok'])
        self.assertTrue(any('duplicat' in v.lower() for v in s['diagnostics']))
    def test_out_of_season_results_blocked(self):
        bad=fake_game(1,2024)
        bad['date']='2026-01-01'
        r=audit_season('pt','2024-2025',{'events':[bad], 'complete':True})
        self.assertFalse(r['complete'])
        self.assertFalse(r['integrity_ok'])
    def test_full_audit_reports_missing_years(self):
        h={'leagues':{'pt':{'seasons':{}},'dk':{'seasons':{}}}}
        report=audit(h)
        self.assertFalse(report['all_complete'])
        for league in ('pt','dk'):
            self.assertEqual(len(report['leagues'][league]['seasons']),5)
    def test_three_way_validation_refuses_incomplete_periods(self):
        seasons={'2021-2022':{'events':[fake_game(1,2021)]}}
        quality={'seasons':{'2021-2022':{'complete':True}}}
        result=audit_league(seasons,quality)
        self.assertEqual(result['status'],'insufficient_historical_coverage')
        self.assertIn('2025-2026',result['incomplete_seasons'])

if __name__=='__main__':
    unittest.main()
