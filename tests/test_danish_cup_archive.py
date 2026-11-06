import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from scripts.collect_danish_cup_archive import ArchiveParser,parse_archive,collect
from scripts.collect_cross_competitions import canonical, normal

def sample_page(n=109,score='2-1'):
    lines=['<html><body><div class="game-wrapper"><div class="score-date">Tisdag 17 september 2024</div>']
    for k in range(n):
        lines.append(f'<div class="score-game"><div class="m1">Club {k}</div>'
                     f'<div class="m2">{score}</div><div class="m3">Other {k}</div></div>')
    lines.append('</div></body></html>')
    return ''.join(lines)

class HistoricalDanishCupTests(unittest.TestCase):
    def test_archive_date_parse_and_strict_coverage(self):
        matches=parse_archive(sample_page())
        self.assertEqual(len(matches),109)
        self.assertTrue(all(e['date']=='2024-09-17' for e in matches))
        self.assertTrue(all(e['competition_id']=='dk_cup' and not e['league_model_eligible'] for e in matches))
        self.assertEqual(matches[0]['source_name'],'ECST historical Danish cup results')
        self.assertEqual(len(set(e['id'] for e in matches)),109)

    def test_rejects_empty_or_truncated_page(self):
        with self.assertRaisesRegex(ValueError,'HTML unavailable'):
            parse_archive('<h1>Unavailable</h1>')
        with self.assertRaisesRegex(ValueError,'Unexpected number'):
            parse_archive(sample_page(3))

    def test_historical_club_aliases_cover_portugal_and_denmark(self):
        pairs=[
            ('Sport Lisboa e Benfica','Benfica'),
            ('Sporting Clube de Portugal','Sporting CP'),
            ('Sporting Clube de Braga','Braga'),
            ('FC København','FC Copenhagen'),
            ('Aarhus GF','AGF Aarhus'),
            ('Viborg FF','Viborg'),
            ('SønderjyskE','Sønderjyske'),
            ('Vitória Guimarães','Guimaraes')]
        for old,new in pairs:
            self.assertEqual(normal(canonical(old)),normal(canonical(new)))

    def test_research_data_import_is_idempotent_with_month_cache(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'cross.json'
            path.write_text(json.dumps({'schema':1,'events':[]}),encoding='utf8')
            calls=[]
            def read():
                calls.append(True)
                return sample_page()
            now=dt.datetime(2026,11,6,tzinfo=dt.timezone.utc)
            first=collect(path=path,fetcher=read,now=now)
            self.assertEqual(first['danish_cup_archive']['status'],'historical_sample_available')
            self.assertEqual(first['danish_cup_archive']['parsed'],109)
            self.assertEqual(len(first['events']),109)
            again=collect(path=path,fetcher=read,now=now+dt.timedelta(days=1))
            self.assertEqual(len(again['events']),109)
            self.assertEqual(len(calls),1)

    def test_conflicting_archive_never_overwrites_existing(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'cross.json'
            p=parse_archive(sample_page())
            current={**p[0],'id':'dbu:555','home_score':4}
            path.write_text(json.dumps({'schema':1,'events':[current]}),encoding='utf8')
            out=collect(path=path,fetcher=sample_page,
                        now=dt.datetime(2026,11,6,tzinfo=dt.timezone.utc))
            self.assertEqual(len(out['events']),1)
            self.assertEqual(out['events'][0]['home_score'],4)
            self.assertEqual(out['danish_cup_archive']['status'],'unavailable_or_conflicted')
            self.assertTrue(out['conflicts'])

if __name__=='__main__':
    unittest.main()
