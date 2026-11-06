import copy
import datetime as dt
import math
import unittest
from scripts.build_value_engine import (
    MIN_VALIDATION, adjusted, fit_calibrator, logit, sigmoid,
    evaluate_league, build, match_market_probs,
)

def event(i,season):
    start=int(season[:4])
    day=dt.date(start,8,1)+dt.timedelta(days=i//8)
    h=f'Team{i%8}'
    a=f'Team{(i+3)%8}'
    return {'id':f'{season}:{i}', 'date':day.isoformat(),
            'home':h,'away':a,'home_score':i%3,'away_score':(i//4)%3,
            'finished':True}

class ValueEngineTests(unittest.TestCase):
    def test_logit_sigmoid_and_probability_bounds(self):
        for p in (.01,.2,.5,.8,.99):
            self.assertAlmostEqual(sigmoid(logit(p)),p,places=9)
            self.assertAlmostEqual(adjusted(p,0,1),p,places=6)
            self.assertTrue(0<adjusted(p,1,1.5)<1)

    def test_regularized_calibrator_requires_validation_sample(self):
        self.assertIsNone(fit_calibrator([(.5,1)]*(MIN_VALIDATION-1)))
        values=[(.62,1 if i%3 else 0) for i in range(170)]
        fit=fit_calibrator(values)
        self.assertEqual(fit['fit_n'],170)
        self.assertGreater(fit['slope'],0)
        self.assertLess(abs(fit['intercept']),1)
        self.assertEqual(fit['fit_season'],'2024-2025')

    def test_fixed_calibrator_is_deterministic(self):
        examples=[(.4+(i%4)*.1,i%2) for i in range(140)]
        self.assertEqual(fit_calibrator(examples),fit_calibrator(list(examples)))

    def test_incomplete_history_blocks_all_calibration(self):
        audit=evaluate_league({'2025-2026':{'events':[]}},
          {'seasons':{'2025-2026':{'complete':True}}})
        self.assertEqual(audit['status'],'incomplete_historical_coverage')
        self.assertFalse(audit['markets'])

    def test_holdout_outcomes_never_change_fitted_params(self):
        years=['2021-2022','2022-2023','2023-2024','2024-2025','2025-2026']
        seasons={s:{'events':[event(i,s) for i in range(160 if int(s[:4])<2024 else 200)]} for s in years}
        quality={'seasons':{s:{'complete':True} for s in years}}
        original=evaluate_league(seasons,quality)
        changed=copy.deepcopy(seasons)
        for e in changed['2025-2026']['events']:
            e['home_score']=0
            e['away_score']=8
        rerun=evaluate_league(changed,quality)
        self.assertEqual(original['markets']['over_2_5']['params'],
                         rerun['markets']['over_2_5']['params'])
        self.assertEqual(original['markets']['btts_yes']['params'],
                         rerun['markets']['btts_yes']['params'])
        self.assertNotEqual(original['markets']['over_2_5']['holdout']['raw']['brier'],
                            rerun['markets']['over_2_5']['holdout']['raw']['brier'])

    def test_same_day_results_cannot_leak_into_fitted_predictions(self):
        years=['2021-2022','2022-2023','2023-2024','2024-2025','2025-2026']
        history=[event(i,s) for s in years for i in range(100)]
        first=match_market_probs(history)
        modified=copy.deepcopy(history)
        # Change an event's result on the same date, leave all earlier dates alone
        target=next(e for e in modified if e['date']=='2025-08-01')
        target['home_score']=12
        target['away_score']=0
        a=next((p for stage,e,p,_ in first if e['date']=='2025-08-01'),None)
        b=next((p for stage,e,p,_ in match_market_probs(modified) if e['date']=='2025-08-01'),None)
        self.assertEqual(a,b)

if __name__=='__main__':
    unittest.main()
