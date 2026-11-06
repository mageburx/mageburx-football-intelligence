"""Five-league forward 1X2 comparison; do not use historical reconstruction."""
import datetime as dt
import math
import unittest

from scripts.record_expansion_1x2 import run,summary
from scripts.audit_expansion_1x2 import calculate
from scripts.build_league_comparison import build,LEAGUE_NAMES

LIDS=('pt','dk','nl','dk2','no')
ISSUED=dt.datetime(2026,11,6,21,0,tzinfo=dt.timezone.utc)
NEXT='2026-11-07'


def source(finished=False,date=NEXT):
    return {'schema':1,'season':'2026-2027',
            'leagues':{lid:{'events':[{'id':f'{lid}-fixture-1','date':date,
                                       'home':f'{lid} Home','away':f'{lid} Away',
                                       'finished':finished,
                                       'home_score':2 if finished else None,
                                       'away_score':0 if finished else None}]}
                       for lid in LIDS}}


def model():
    return {'generated_at':(ISSUED-dt.timedelta(minutes=5)).isoformat(),
            'leagues':{lid:{'predictions':{f'{lid}-fixture-1':{
                'p1':.5,'px':.3,'p2':.2,'model':'poisson'
            }}} for lid in LIDS}}


class FiveLeagueComparisonTests(unittest.TestCase):
    def test_forward_only_five_leagues_and_no_rewrites(self):
        created=run(source(),model(),now=ISSUED)
        self.assertEqual(len(created['predictions']),5)
        self.assertEqual(set(x['league'] for x in created['predictions']),set(LIDS))
        unchanged=run(source(),model(),created,ISSUED+dt.timedelta(minutes=30))
        self.assertEqual(len(unchanged['predictions']),5)
        self.assertEqual(unchanged['settlements'],[])
        # Actual future match day cannot be scored as an historical tip.
        self.assertEqual(len(run(source(),model(),None,
                ISSUED+dt.timedelta(days=2))['predictions']),0)

    def test_valid_settled_games_reported_separately_all_five(self):
        ledger=run(source(),model(),now=ISSUED)
        settled_source=source(True)
        ledger=run(settled_source,model(),ledger,
                   dt.datetime(2026,11,8,12,tzinfo=dt.timezone.utc))
        audit=calculate(ledger,settled_source,
                        dt.datetime(2026,11,8,12,tzinfo=dt.timezone.utc))
        self.assertEqual(len(ledger['settlements']),5)
        self.assertEqual(audit['warning_count'],0)
        result=build(audit,dt.datetime(2026,11,8,12,tzinfo=dt.timezone.utc))
        self.assertEqual(list(result['leagues']),list(LEAGUE_NAMES))
        self.assertEqual(result['totals']['issued'],5)
        self.assertEqual(result['totals']['settled_valid'],5)
        self.assertEqual(result['totals']['leagues_with_results'],5)
        self.assertEqual(result['ranking_status'],
                         'not_rankable_insufficient_or_nonuniform_evidence')
        for lid in LIDS:
            x=result['leagues'][lid]
            self.assertEqual(x['issued'],1)
            self.assertEqual(x['valid_settled'],1)
            self.assertAlmostEqual(x['brier'],.38)
            self.assertAlmostEqual(x['log_loss'],-math.log(.5),places=5)
            self.assertIsNone(x['brier_ci95'])
            self.assertEqual(x['sample_status'],'preliminary_only')

    def test_empty_ledgers_do_not_invent_prediction_scores(self):
        empty={'schema':1,'predictions':[],'settlements':[]}
        result=build(calculate(empty,source(),ISSUED),ISSUED)
        self.assertEqual(result['totals']['settled_valid'],0)
        for x in result['leagues'].values():
            self.assertIsNone(x['brier'])
            self.assertIsNone(x['log_loss'])
            self.assertEqual(x['sample_status'],'awaiting_first_valid_result')

    def test_invalid_signature_is_excluded_from_comparison(self):
        ledger=run(source(),model(),now=ISSUED)
        ledger['predictions'][0]['probabilities_1x2']=[.98,.01,.01]
        after=dt.datetime(2026,11,8,12,tzinfo=dt.timezone.utc)
        ledger=run(source(True),model(),ledger,after)
        audit=calculate(ledger,source(True),after)
        self.assertTrue(audit['leagues']['pt']['invalid'])
        result=build(audit,after)
        self.assertEqual(result['leagues']['pt']['valid_settled'],0)
        self.assertIsNone(result['leagues']['pt']['brier'])
        self.assertTrue(result['leagues']['pt']['quality_warning'])
        self.assertEqual(result['totals']['settled_valid'],4)

    def test_comparison_rejects_missing_or_inconsistent_audit(self):
        audit={'schema':1,'leagues':{lid:{
            'issued':0,'settled':0,'settled_valid':0,'invalid':0
        } for lid in LIDS}}
        del audit['leagues']['dk']
        with self.assertRaises(ValueError):build(audit,ISSUED)
        audit['leagues']['dk']={'issued':1,'settled':2,'settled_valid':2,'invalid':0}
        with self.assertRaises(ValueError):build(audit,ISSUED)

if __name__=='__main__':
    unittest.main()
