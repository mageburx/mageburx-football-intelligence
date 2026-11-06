import copy
import unittest

from scripts.reconcile_danish_history import PLAYOFFS, canonical, reconcile
from scripts.build_model import finished
from scripts.backfill_history import ROUND_COUNTS

def empty_history():
    return {'schema':1,'leagues':{'dk':{'seasons':{}},'pt':{'seasons':{}}}}

class DanishReconciliationTests(unittest.TestCase):
    def test_all_playoffs_are_referenced_but_excluded_from_models(self):
        history=reconcile(empty_history())
        for season, src in PLAYOFFS.items():
            e=history['leagues']['dk']['seasons'][season]['events'][0]
            self.assertEqual(e['date'], src['date'])
            self.assertEqual(e['home_score'], src['home_score'])
            self.assertEqual(e['away_score'], src['away_score'])
            self.assertTrue(e['source_url'].startswith('https://'))
            self.assertEqual(e['stage'],'european_playoff')
            self.assertFalse(finished(e))
            self.assertFalse(history['leagues']['dk']['seasons'][season]['complete'])

    def test_can_complete_2024_25_exactly_193(self):
        src=PLAYOFFS['2024-2025']
        history=empty_history()
        old=[{'id':f'legacy:{i}', 'date':f'2024-08-{(i%28)+1:02d}',
              'home':f'Team{i}', 'away':f'Team{i+1}',
              'home_score':1, 'away_score':0, 'finished':True} for i in range(192)]
        history['leagues']['dk']['seasons']['2024-2025']={
            'events':old, 'actual_games':192,'expected_games':193,'complete':False}
        fixed=reconcile(history)
        season=fixed['leagues']['dk']['seasons']['2024-2025']
        self.assertEqual(season['actual_games'],193)
        self.assertEqual(season['expected_games'],193)
        self.assertTrue(season['complete'])
        self.assertEqual(sum(e.get('stage')=='european_playoff' for e in season['events']),1)
        again=reconcile(fixed)
        self.assertEqual(len(again['leagues']['dk']['seasons']['2024-2025']['events']),193)

    def test_conflicting_official_result_blocks_audit(self):
        p=PLAYOFFS['2022-2023']
        history=empty_history()
        history['leagues']['dk']['seasons']['2022-2023']={
            'events':[{'id':'wrong','date':p['date'],'home':p['home'],
                      'away':p['away'],'home_score':7,'away_score':0,'finished':True}]}
        with self.assertRaisesRegex(ValueError,'Conflicting'):
            reconcile(history)

    def test_canonical_names_and_22_rounds_for_old_seasons(self):
        self.assertEqual(canonical('FC Copenhagen'),'FC København')
        self.assertEqual(canonical('Brøndby'),'Brøndby IF')
        self.assertEqual(canonical('AGF Aarhus'),'Aarhus GF')
        self.assertEqual(ROUND_COUNTS['2021-2022'],22)
        self.assertEqual(ROUND_COUNTS['2022-2023'],22)
        self.assertEqual(ROUND_COUNTS['2025-2026'],32)

if __name__ == '__main__':
    unittest.main()
