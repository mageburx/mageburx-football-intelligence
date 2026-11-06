import json
import tempfile
import unittest
from pathlib import Path

from scripts.backfill_history import collect, expected_round_matches

class HistoricalRoundTests(unittest.TestCase):
    def test_expected_fixture_count_per_round(self):
        for season in ('2021-2022','2022-2023'):
            self.assertEqual(expected_round_matches(season,1),12)
            self.assertEqual(expected_round_matches(season,10),12)
            self.assertEqual(expected_round_matches(season,11),6)
            self.assertEqual(expected_round_matches(season,22),6)
        self.assertEqual(expected_round_matches('2025-2026',1),6)
        self.assertEqual(expected_round_matches('2025-2026',32),6)
        with self.assertRaises(ValueError):
            expected_round_matches('2022-2023',23)

    def test_reject_partial_round_without_marking_fetched(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'history.json'
            data={'leagues':{'dk':{'seasons':{}}}}
            for season in ('2021-2022','2022-2023','2025-2026'):
                data['leagues']['dk']['seasons'][season]={
                    'events':[],'actual_games':0,'complete':False,'expected_games':193,'fetched_rounds':[]}
            path.write_text(json.dumps(data),encoding='utf8')
            def stub(season,r):
                return [self.match(season,r,i) for i in range(6)]
            done=collect(path=path,max_calls=1,pause=0,fetcher=stub)
            entry=done['leagues']['dk']['seasons']['2021-2022']
            self.assertEqual(entry['events'],[])
            self.assertEqual(entry['fetched_rounds'],[])
            self.assertFalse(entry['complete'])

    def test_complete_round_accepted_only_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'history.json'
            data={'leagues':{'dk':{'seasons':{}}}}
            for season in ('2021-2022','2022-2023','2025-2026'):
                n=22 if season!='2025-2026' else 32
                data['leagues']['dk']['seasons'][season]={
                    'events':[], 'fetched_rounds':list(range(1,n+1)),
                    'expected_games':193,'complete':False}
            data['leagues']['dk']['seasons']['2025-2026']['fetched_rounds']=[]
            path.write_text(json.dumps(data),encoding='utf8')
            def stub(season,r):
                return [self.match(season,r,i) for i in range(6)]
            done=collect(path=path,max_calls=1,pause=0,fetcher=stub)
            entry=done['leagues']['dk']['seasons']['2025-2026']
            self.assertEqual(len(entry['events']),6)
            self.assertEqual(entry['fetched_rounds'],[1])
            self.assertFalse(entry['complete'])

    @staticmethod
    def match(season,r,i):
        return {'id':f'tsdb:{season}:{r}:{i}','date':season[:4]+'-08-07',
                'home':f'H{i}','away':f'A{i}','home_score':i%3,
                'away_score':i%2,'finished':True}

if __name__=='__main__':
    unittest.main()
