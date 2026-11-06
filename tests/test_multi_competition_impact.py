import datetime as dt
import unittest
from scripts.build_multi_competition_impact import (
    date_year_season,extra_games_before,recent_context,candidate_rates,
    source_coverage,evaluate_league
)

class MultiCompetitionImpactTests(unittest.TestCase):
    @staticmethod
    def league(date,home='Porto',away='Benfica',id='l'):
        return {'id':id,'date':date,'home':home,'away':away,
                'home_score':1,'away_score':0,'finished':True}
    @staticmethod
    def cup(date,home='FC Porto',away='Inter',id='cup'):
        return {'id':id,'date':date,'home':home,'away':away,
                'home_score':2,'away_score':1,'finished':True,
                'competition_type':'european'}
    def test_season_boundaries(self):
        self.assertEqual(date_year_season('2024-08-17'),'2024-2025')
        self.assertEqual(date_year_season('2025-03-12'),'2024-2025')
        self.assertEqual(date_year_season('2025-07-01'),'2025-2026')

    def test_future_and_same_day_fixtures_do_not_affect_fatigue(self):
        base=[self.league('2025-10-01')]
        cross=[self.cup('2025-10-08')]
        current=recent_context(base,cross,'2025-10-10','Porto','Benfica')
        self.assertEqual(current['porto']['rest'],2)
        self.assertEqual(current['porto']['additional_14'],1)
        future=cross+[self.cup('2025-10-10',id='same'),self.cup('2025-10-11',id='future')]
        self.assertEqual(current,recent_context(base,future,'2025-10-10','Porto','Benfica'))
        self.assertEqual(candidate_rates((1.5,1.2),current,'Porto','Benfica','baseline'),(1.5,1.2))

    def test_replicated_dbu_and_fallback_fixture_count_once(self):
        a=self.cup('2025-10-08',id='dbu:111')
        b={**a,'id':'fodboldzone:555','home':'Porto','away':'Inter'}
        records=extra_games_before([a,b],'2025-10-10','Porto','Benfica')
        self.assertEqual(len(records['porto']),1)

    def test_no_cross_matches_never_imply_effect(self):
        teams=[self.league(f'2024-08-{(i%28)+1:02d}',
                           home=f'Team{i}',away=f'Team{i+30}',id=str(i)) for i in range(24)]
        coverage=source_coverage(teams,[],'2024-2025')
        self.assertFalse(coverage['adequate_minimum_sample'])
        self.assertEqual(coverage['known_cross_matches'],0)

    def test_cup_and_uefa_coverage_are_separate_and_deduplicated(self):
        events=[self.league('2024-10-01')]
        euro=self.cup('2024-10-08')
        duplicate={**euro,'id':'alternate:111','home':'Porto'}
        domestic={**self.cup('2024-10-09',away='Braga',id='domestic'),
                  'competition_type':'domestic_cup'}
        irrelevant=self.cup('2024-10-10',home='Unrelated A',away='Unrelated B')
        coverage=source_coverage(events,[euro,duplicate,domestic,irrelevant],'2024-2025')
        self.assertEqual(coverage['known_cross_matches'],2)
        self.assertEqual(coverage['known_domestic_cup_matches'],1)
        self.assertEqual(coverage['known_european_matches'],1)
        self.assertFalse(coverage['coverage_certified_complete'])

    def test_missing_2024_source_blocks_holdout_claim(self):
        years=['2021-2022','2022-2023','2023-2024','2024-2025','2025-2026']
        seasons={y:{'events':[self.league(f'{y[:4]}-10-01',id=y)]} for y in years}
        quality={'seasons':{y:{'complete':True} for y in years}}
        outcome=evaluate_league(seasons,quality,[self.cup('2025-10-10')])
        self.assertEqual(outcome['status'],'blocked_sparse_cross_competition_history')
        self.assertEqual(outcome['coverage']['2024-2025']['known_cross_matches'],0)
        self.assertEqual(outcome['models'],{})

if __name__=='__main__':
    unittest.main()
