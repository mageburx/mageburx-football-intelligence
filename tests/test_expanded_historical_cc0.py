"""No fabricated historical completeness and no edits to signed/current data."""
import datetime as dt
import unittest
from scripts.collect_expanded_historical_cc0 import parse_archive,refresh,SOURCES,EXPECTED

NOW=dt.datetime(2026,11,7,1,45,tzinfo=dt.timezone.utc)
STAMP=NOW.isoformat()

def sample(lid,year):
    if lid=='no':
        return (f'= Norway Eliteserien {year}\n\n# Teams 16\n# Matches 240\n'
            f'▪ Matchday 1\n  Mon Apr 10 {year}\n'
            '    17:00  Rosenborg BK  v Viking FK  1-0 (0-0)\n'
            '           Hamarkameratene v Sandefjord Fotball 2-0\n'
            '  Wed Apr 19\n    18:30 Lillestrøm SK v Strømsgodset IF 4-3 (2-2)\n')
    return ('= Denmark 1. Division 2024/25\n\n# Teams 12\n# Matches 192\n'
            '▪ Matchday 1\n  Fri Jul 19 2024\n'
            '    19:00  B.93 København v Kolding IF 0-0\n'
            '  Sat Jul 20\n    16:00 Esbjerg fB v Odense BK 1-2 (0-1)\n'
            '▪ Promotion, Matchday 7\n  Sat May 3\n'
            '    12:30 Odense BK v FC Fredericia 1-1 (1-1)\n')

class HistoricalCC0Tests(unittest.TestCase):
    def test_norwegian_calendar_years_do_not_appear_as_cross_year_seasons(self):
        self.assertEqual(EXPECTED['no'],('2021','2022','2023','2024','2025'))
        row=parse_archive(sample('no','2023'),'no','2023',STAMP)
        self.assertEqual(row['actual_games'],3)
        self.assertEqual(row['status'],'source_partial')
        self.assertFalse(row['complete'])
        self.assertEqual(row['events'][2]['date'],'2023-04-19')
        self.assertTrue(all(e['result_verified'] and e['match_status']=='FT' for e in row['events']))
        self.assertTrue(all(e['id'].startswith('cc0:') for e in row['events']))
    def test_split_stage_danish_games_date_after_new_year(self):
        row=parse_archive(sample('dk2','2024-2025'),'dk2','2024-2025',STAMP)
        self.assertEqual(row['actual_games'],3)
        self.assertEqual(row['expected_games'],192)
        self.assertEqual(row['events'][-1]['date'],'2025-05-03')
        self.assertTrue(any(e['stage']=='Promotion' for e in row['events']))
        self.assertFalse(row['complete'])
    def test_no_scores_invented_for_unplayed_games(self):
        raw=sample('no','2023')+'\n  Sun Dec 3\n  Viking FK v Rosenborg BK\n'
        self.assertEqual(parse_archive(raw,'no','2023',STAMP)['actual_games'],3)
    def test_wrong_competition_and_count_rejected(self):
        with self.assertRaises(ValueError):
            parse_archive(sample('no','2023').replace('Eliteserien','OBOS-ligaen'),
                          'no','2023',STAMP)
        with self.assertRaises(ValueError):
            parse_archive(sample('no','2023').replace('# Matches 240','# Matches 239'),
                          'no','2023',STAMP)
    def test_source_ambiguous_or_duplicated_scores_fail_closed(self):
        repeated=sample('no','2023')+'  Wed Apr 19\n  Lillestrøm SK v Strømsgodset IF 4-3\n'
        with self.assertRaises(ValueError):
            parse_archive(repeated,'no','2023',STAMP)
        garbage=sample('no','2023')+'  Wed Apr 19\n  Team A v Team B 2-1 (2-1) after extra time\n'
        with self.assertRaises(ValueError):
            parse_archive(garbage,'no','2023',STAMP)
    def test_bounded_allowed_paths_and_weekly_cache(self):
        called=[]
        def fake(path):
            called.append(path)
            if path.startswith('norway/'):
                return sample('no',path.split('/')[-1][:4])
            return sample('dk2','2024-2025')
        a,log=refresh(reader=fake,now=NOW)
        self.assertEqual(len(called),4)
        self.assertEqual(log['no']['downloaded'],3)
        self.assertEqual(log['dk2']['downloaded'],1)
        self.assertEqual(sum(v['complete'] for l in a['leagues'].values()
                  for v in l['seasons'].values()),0)
        b,log2=refresh(previous=a,reader=fake,now=NOW+dt.timedelta(hours=1))
        self.assertEqual(len(called),4)
        self.assertEqual(log2['no']['cached'],3)
        self.assertEqual(a['leagues']['no']['seasons']['2023']['events'],
                         b['leagues']['no']['seasons']['2023']['events'])
    def test_failure_preserves_last_good_snapshot(self):
        a,_=refresh(reader=lambda path:sample('no',path[-12:-8])
                     if path.startswith('norway/') else sample('dk2','2024-2025'),now=NOW)
        old=a['leagues']['no']['seasons']['2023']['events']
        b,log=refresh(a,reader=lambda path: (_ for _ in ()).throw(OSError('offline')),
                      now=NOW+dt.timedelta(days=8))
        self.assertEqual(b['leagues']['no']['seasons']['2023']['events'],old)
        self.assertGreater(log['no']['errors'],0)

if __name__=='__main__':
    unittest.main()
