"""Regression: licensed archive audit and read-only authenticated source checks."""
import datetime as dt
import unittest
import sys
import types
from unittest.mock import patch
from scripts.collect_schochastics_no import build as norway_build,refresh as norway_refresh,prepare_rows
from scripts.collect_secondary_football_data import compare,collect,normalized

NOW=dt.datetime(2026,11,8,8,0,tzinfo=dt.timezone.utc)

def norway_row(year,home,away,goals=(1,0),ft='F',competition='Norway'):
    return {'date':dt.datetime(year,5,10,tzinfo=dt.timezone.utc),
            'home':home,'away':away,'gh':goals[0],'ga':goals[1],
            'full_time':ft,'competition':competition,'level':'national'}

class SchochasticsTests(unittest.TestCase):
    def test_parquet_projection_uses_supported_list_not_tuple(self):
        parent=types.ModuleType('pyarrow')
        parent.__path__=[]
        reader=types.ModuleType('pyarrow.parquet')
        class Table:
            num_rows=100001
            def select(self,cols):
                self._cols=cols
                return self
            def to_pylist(self):
                return [{'columns_valid':isinstance(self._cols,list)}]
        def read_table(data,columns):
            self.assertIsInstance(columns,list)
            return Table()
        reader.read_table=read_table
        parent.parquet=reader
        with patch.dict(sys.modules,{'pyarrow':parent,'pyarrow.parquet':reader}):
            rows=prepare_rows(b'synthetic-parquet')
        self.assertTrue(rows[0]['columns_valid'])

    def test_no_wrong_competition_and_non_ninety_minute_scores(self):
        data=[norway_row(2021,'Molde','Brann'),
              norway_row(2021,'Odd','Viking',ft='P'),
              norway_row(2021,'HamKam','Tromsø',competition='Norway Cup'),
              norway_row(2022,'Bodø','Sandefjord')]
        out=norway_build(data,NOW)
        self.assertEqual(out['seasons']['2021']['actual_games'],1)
        self.assertEqual(out['seasons']['2022']['actual_games'],1)
        self.assertFalse(out['seasons']['2021']['complete'])
        self.assertTrue(out['seasons']['2021']['events'][0]['id'].startswith('odc:'))
        self.assertEqual(out['license'],'ODC-BY-1.0')
    def test_complete_requires_240_unique_with_16_clubs_30_appearances_each(self):
        teams=[f'Club {i}' for i in range(16)]
        rows=[]
        # 16-team double round robin => 240 matches, 30 each.
        for i in range(16):
            for j in range(16):
                if i==j:continue
                d=dt.datetime(2021,1,1,tzinfo=dt.timezone.utc)+dt.timedelta(days=len(rows))
                rows.append({'date':d,'home':teams[i],'away':teams[j],
                             'gh':2,'ga':1,'competition':'Norway','level':'national',
                             'full_time':'F'})
        out=norway_build(rows,NOW)
        self.assertEqual(out['seasons']['2021']['actual_games'],240)
        self.assertEqual(out['seasons']['2021']['team_count'],16)
        self.assertTrue(out['seasons']['2021']['complete'])
        rows.append(dict(rows[0]))
        out=norway_build(rows,NOW)
        self.assertFalse(out['seasons']['2021']['complete'])
        self.assertEqual(out['seasons']['2021']['duplicate_pairs'],1)
    def test_cached_archive_performs_no_more_downloads(self):
        cache={'schema':1,'seasons':{str(y):{'complete':True} for y in (2021,2022)}}
        def fail():raise AssertionError('Must not fetch')
        report,meta=norway_refresh(cache,fail,NOW)
        self.assertEqual(meta['requests'],0)
        self.assertEqual(report,cache)
    def test_source_unavailable_never_overwrites_prior_matches(self):
        old={'schema':1,'seasons':{'2021':{'events':[{'id':'1'}]}}}
        def fail():raise OSError('network offline')
        new,result=norway_refresh(old,fail,NOW)
        self.assertEqual(new['seasons']['2021']['events'],[{'id':'1'}])
        self.assertEqual(result['status'],'source_unavailable')

class SecondaryTests(unittest.TestCase):
    def test_alias_matching_and_score_disagreement_no_mutation(self):
        current={'id':'100','date':'2026-11-06','home':'Famalicão','away':'Arouca',
                 'finished':True,'home_score':2,'away_score':0}
        raw={'competition':{'code':'PPL'},'matches':[{
            'status':'FINISHED','utcDate':'2026-11-06T20:45:00Z',
            'homeTeam':{'name':'FC Famalicão'},'awayTeam':{'name':'FC Arouca'},
            'score':{'fullTime':{'home':3,'away':0}}}]}
        result=compare('pt',[current],raw)
        self.assertEqual(normalized('F.C. Famalicão'),'famalicao')
        self.assertEqual(result['matched_fixtures'],1)
        self.assertEqual(result['disagreements'],1)
        self.assertEqual(result['examples'][0]['stored_score'],[2,0])
        self.assertEqual(current['home_score'],2)
    def test_partial_scores_never_count_as_confirmed(self):
        raw={'competition':{'code':'DED'},'matches':[{
            'status':'IN_PLAY','utcDate':'2026-11-06T20:45:00Z',
            'homeTeam':{'name':'Ajax'},'awayTeam':{'name':'PSV'},
            'score':{'fullTime':{'home':2,'away':2}}}]}
        self.assertEqual(compare('nl',[],raw)['provider_final'],0)
    def test_no_token_never_calls_network(self):
        report=collect({'leagues':{}},'',fetcher=lambda *x: (_ for _ in ()).throw(
            AssertionError('network must not be called')),now=NOW)
        self.assertEqual(report['status'],'not_configured')
        self.assertFalse(report['token_configured'])
    def test_token_probes_two_competitions_max_once_a_day(self):
        calls=[]
        def fetch(code,token,year):
            calls.append(code)
            return {'competition':{'code':code},'matches':[]}
        doc={'leagues':{'pt':{'events':[]},'nl':{'events':[]}}}
        report=collect(doc,'fake-token',fetcher=fetch,now=NOW)
        self.assertEqual(calls,['PPL','DED'])
        again=collect(doc,'fake-token',previous=report,fetcher=fetch,
                      now=NOW+dt.timedelta(hours=1))
        self.assertEqual(calls,['PPL','DED'])
        self.assertEqual(again['leagues']['pt']['status'],'audited')

if __name__=='__main__':
    unittest.main()
