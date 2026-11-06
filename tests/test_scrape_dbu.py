import copy
import datetime as dt
import tempfile
import unittest
from pathlib import Path
import json

from scripts.scrape_dbu import parse_page, merge_matches, collect, fetch_allowed

PAGE='''<!DOCTYPE html><html lang="da"><body><h1>3F Superliga Kampprogram</h1><table>
<thead><tr><th>Kampnr</th><th>Dato</th><th>Tid</th><th>Hjemme</th><th>Ude</th><th>Spillested</th><th>TV</th><th>Resultat</th></tr></thead>
<tbody>
<tr><td>622054</td><td>søn.02-04 2023</td><td>16:00</td><td>Brøndby IF</td><td>Viborg</td><td>Stadion</td><td>TV</td><td>0 - 3</td></tr>
<tr><td>622052</td><td>søn.02-04 2023</td><td>18:00</td><td>F.C. København</td><td>FC Nordsjælland</td><td>Stadion</td><td>TV</td><td>2 - 1</td></tr>
</tbody></table></body></html>'''

def base():
    return {'leagues':{'dk':{'seasons':{'2022-2023':{
        'events':[],'actual_games':0,'expected_games':193,'complete':False}}}}}

class ScraperTests(unittest.TestCase):
    def test_html_table_parser(self):
        rows=parse_page(PAGE,'2022-2023','championship',409107,'https://www.dbu.dk/resultater/pulje/409107/kampprogramFuld')
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]['date'],'2023-04-02')
        self.assertEqual(rows[0]['home'],'Brøndby IF')
        self.assertEqual(rows[0]['away'],'Viborg FF')
        self.assertEqual(rows[1]['home'],'FC København')
        self.assertEqual((rows[1]['home_score'],rows[1]['away_score']),(2,1))

    def test_conflicts_go_to_quarantine(self):
        rows=parse_page(PAGE,'2022-2023','championship',409107,'https://www.dbu.dk/resultater/pulje/409107/kampprogramFuld')
        history=base()
        first=merge_matches(history,'2022-2023',rows)
        self.assertEqual(first['new'],2)
        again=merge_matches(history,'2022-2023',rows)
        self.assertEqual(again['new'],0)
        self.assertEqual(again['confirmed'],2)
        self.assertEqual(len(history['leagues']['dk']['seasons']['2022-2023']['events']),2)
        bad=copy.deepcopy(rows)
        bad[0]['home_score']=9
        conflict=merge_matches(history,'2022-2023',bad)
        self.assertEqual(len(conflict['conflicts']),1)
        self.assertEqual(history['leagues']['dk']['seasons']['2022-2023']['events'][0]['home_score'],0)

    def test_temp_unavailability_is_not_empty_season(self):
        with self.assertRaisesRegex(ValueError,'temporarily unavailable'):
            parse_page('<html><h1>Der er ekstraordinært travlt</h1></html>','2022-2023','regular',387486,'url')

    def test_robots_enforcement_fails_closed(self):
        url='https://www.dbu.dk/resultater/pulje/409107/kampprogramFuld'
        def denied(uri):
            if uri.endswith('robots.txt'):
                return 'User-agent: *\\nDisallow: /resultater/'
            return PAGE
        with self.assertRaises(PermissionError):
            fetch_allowed(url,reader=denied)
        def unavailable(uri):
            raise TimeoutError('network blocked')
        with self.assertRaisesRegex(RuntimeError,'robots'):
            fetch_allowed(url,reader=unavailable)

    def test_safe_collection_logs_failures(self):
        with tempfile.TemporaryDirectory() as d:
            history=Path(d)/'history.json'
            report=Path(d)/'report.json'
            before=base()
            history.write_text(json.dumps(before),encoding='utf-8')
            def blocked(url):
                raise RuntimeError('Cannot verify DBU robots')
            result=collect(path=history,report_path=report,max_pages=1,pause=0,getter=blocked,
                           now=dt.datetime(2026,11,6,tzinfo=dt.timezone.utc))
            self.assertEqual(result['imported'],0)
            self.assertEqual(json.loads(history.read_text()),before)
            self.assertTrue(report.exists())

if __name__=='__main__':
    unittest.main()
