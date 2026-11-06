import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from scripts.collect_portugal_cup_archive import parse_archive,collect,ARCHIVES

def sample(n,year,score='*2-1'):
    body=[f'<html><body><div class="score-date">Tisdag 17 september {year}</div>']
    for i in range(n):
        body.append(f'<div class="score-game"><div class="m1">Team{i}</div>'+
                    f'<div class="m2">{score}</div><div class="m3">Opponent{i}</div></div>')
    return ''.join(body)+'</body></html>'

class PortugalArchiveTests(unittest.TestCase):
    def test_date_and_starred_extra_time_scores_not_usable_for_goal_model(self):
        for name,ref in ARCHIVES.items():
            events=parse_archive(sample(ref['expected'],ref['year']),ref)
            self.assertEqual(len(events),ref['expected'])
            self.assertTrue(all(not e['league_model_eligible'] for e in events))
            self.assertTrue(all(e['date']==f"{ref['year']}-09-17" for e in events))
            self.assertEqual(len(set(e['id'] for e in events)),len(events))

    def test_missing_or_truncated_archive_is_rejected(self):
        ref=ARCHIVES['pt_cup:2024-2025']
        with self.assertRaisesRegex(ValueError,'Incomplete archive'):
            parse_archive(sample(30,2024),ref)

    def test_three_fixed_archives_and_monthly_cooldown(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'cross.json'
            path.write_text(json.dumps({'schema':1,'events':[]}),encoding='utf8')
            urls=[]
            def fetch(url):
                urls.append(url)
                ref=next(x for x in ARCHIVES.values() if x['url']==url)
                return sample(ref['expected'],ref['year'])
            now=dt.datetime(2026,11,6,tzinfo=dt.timezone.utc)
            out=collect(path=path,fetcher=fetch,now=now)
            self.assertEqual(len(urls),3)
            self.assertEqual(len(out['events']),148+111+7)
            self.assertTrue(all(x['status']=='historical_sample_available'
                                for x in out['portugal_cup_archive'].values()))
            after=collect(path=path,fetcher=fetch,now=now+dt.timedelta(days=1))
            self.assertEqual(len(urls),3)
            self.assertEqual(len(after['events']),266)

    def test_conflicting_match_never_imports_partial_batch(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'cross.json'
            ref=ARCHIVES['pt_cup:2024-2025']
            first=parse_archive(sample(148,2024),ref)[0]
            wrong={**first,'id':'other-source-55','home_score':10}
            path.write_text(json.dumps({'schema':1,'events':[wrong]}),encoding='utf8')
            def fetch(url):
                ref=next(x for x in ARCHIVES.values() if x['url']==url)
                return sample(ref['expected'],ref['year'])
            report=collect(path=path,fetcher=fetch,
                           now=dt.datetime(2026,11,6,tzinfo=dt.timezone.utc))
            self.assertEqual(report['portugal_cup_archive']['pt_cup:2024-2025']['status'],
                             'source_unavailable_or_conflicted')
            self.assertEqual(report['events'][0]['home_score'],10)
            self.assertTrue(report['conflicts'])

if __name__=='__main__':
    unittest.main()
