import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from scripts.collect_danish_cup import collect

class DanishCupSourceTests(unittest.TestCase):
    def test_unavailable_source_preserves_prior_events(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'cross.json'
            old={'schema':1,'events':[{'id':'uefa:123','date':'2026-10-22','competition_id':'uefa_cl'}],
                 'coverage':'partial'}
            p.write_text(json.dumps(old),encoding='utf8')
            def blocked(_):raise RuntimeError('DBU temporarily unavailable')
            out=collect(path=p,fetcher=blocked,
                        now=dt.datetime(2026,11,6,tzinfo=dt.timezone.utc))
            self.assertEqual(len(out['events']),1)
            self.assertEqual(out['coverage'],'partial')
            self.assertEqual(out['danish_cup_source']['2026-2027']['status'],
                             'temporarily_unavailable_or_not_allowed')

    def test_official_fixture_added_once_and_never_in_league_model(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'cross.json'
            p.write_text(json.dumps({'schema':1,'events':[]}),encoding='utf8')
            def fetcher(_):return 'DBU fixture table'
            def parser(html,season,stage,pool,url):
                return [{'id':f'dbu:{season}:999','date':'2026-09-03' if season=='2026-2027' else '2025-10-02',
                         'home':'Viborg','away':'Sønderjyske Fodbold',
                         'home_score':2,'away_score':1,'finished':True}]
            now=dt.datetime(2026,11,6,tzinfo=dt.timezone.utc)
            first=collect(path=p,fetcher=fetcher,parser=parser,now=now)
            self.assertEqual(len(first['events']),2)
            self.assertTrue(all(not e['league_model_eligible'] for e in first['events']))
            second=collect(path=p,fetcher=fetcher,parser=parser,now=now)
            self.assertEqual(len(second['events']),2)
            self.assertEqual(second['danish_cup_source']['2026-2027']['added'],0)

if __name__=='__main__':
    unittest.main()
