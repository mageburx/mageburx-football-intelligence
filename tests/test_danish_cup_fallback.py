import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from scripts.collect_danish_cup_fallback import parse_fixture_page,collect

HTML='''<!DOCTYPE html><html><body>
<section id="kommende">
<a href="https://fodboldzone.dk/kamp/2000/" class="fdh-match-card">
<span class="fdh-match-card__date">02. dec 18:00</span>
<span class="fdh-match-card__team">FC København</span>
<span class="fdh-match-card__team">Brøndby IF</span></a>
</section>
<section id="resultater" class="fdh-entity__section">
<h2>Resultater</h2><div class="fdh-matches-grid">
<a href="https://fodboldzone.dk/kamp/1640479/" class="fdh-match-card">
<span class="fdh-match-card__date">03. nov 18:00</span>
<span class="fdh-match-card__teams"><span class="fdh-match-card__team">
<img alt="" src="test">Lyngby BK</span><span class="fdh-match-card__team">Randers FC</span></span>
<span class="fdh-match-card__score">1 - 0</span></a>
<a href="https://fodboldzone.dk/kamp/1456/" class="fdh-match-card">
<span class="fdh-match-card__date">19. feb 20:00</span>
<span class="fdh-match-card__team">FC København</span>
<span class="fdh-match-card__team">OB</span>
<span class="fdh-match-card__score">3 - 2</span></a></div></section></body></html>'''

class DanishCupFallbackTests(unittest.TestCase):
    def test_extracts_only_finished_cards_with_season_boundary(self):
        matches=parse_fixture_page(HTML,2026)
        self.assertEqual(len(matches),2)
        self.assertEqual(matches[0]['date'],'2026-11-03')
        self.assertEqual(matches[1]['date'],'2027-02-19')
        self.assertEqual(matches[1]['home'],'FC Copenhagen')
        self.assertEqual(matches[1]['away'],'Odense BK')
        self.assertTrue(all(e['league_model_eligible'] is False for e in matches))
        self.assertTrue(all(e['competition_id']=='dk_cup' for e in matches))

    def test_fails_closed_on_empty_or_redesigned_page(self):
        with self.assertRaisesRegex(ValueError,'No scored result cards'):
            parse_fixture_page('<html>'+'No results'*80+'</html>',2026)

    def test_sources_provenance_idempotence_and_cooldown(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'cross.json'
            path.write_text(json.dumps({'schema':1,'coverage':'partial','events':[]}),encoding='utf8')
            calls=[]
            def fetch(url):
                calls.append(url)
                return HTML
            now=dt.datetime(2026,11,6,2,0,tzinfo=dt.timezone.utc)
            first=collect(path=path,fetcher=fetch,now=now,max_seasons=2)
            self.assertEqual(len(calls),2)
            self.assertEqual(len(first['events']),3) # 2026 Nov; 2025 Nov and 2026 Feb
            self.assertEqual(first['danish_cup_fallback']['2026']['scored_cards'],2)
            self.assertTrue(all(e['date']<'2026-11-06' for e in first['events']))
            second=collect(path=path,fetcher=fetch,now=now+dt.timedelta(hours=1),max_seasons=2)
            self.assertEqual(len(calls),2)
            self.assertEqual(len(second['events']),3)

    def test_failures_preserve_existing_matches(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'cross.json'
            initial={'schema':1,'events':[{'id':'pre','date':'2025-08-01'}]}
            path.write_text(json.dumps(initial),encoding='utf8')
            def broken(_):raise PermissionError('robots.txt disallowed')
            result=collect(path=path,fetcher=broken,
                           now=dt.datetime(2026,11,6,tzinfo=dt.timezone.utc))
            self.assertEqual(len(result['events']),1)
            self.assertEqual(result['danish_cup_fallback']['2026']['status'],
                             'source_unavailable_or_not_allowed')

if __name__=='__main__':
    unittest.main()
