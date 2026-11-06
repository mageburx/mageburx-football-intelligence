import datetime as dt
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from scripts.collect_norwegian_fantasy import parse,reconcile,download
from scripts.collect_danish_first_official import collect as collect_dbu,normalize
from scripts.collect_expanded_leagues import collect as collect_rounds


NOW=dt.datetime(2026,11,6,17,tzinfo=dt.timezone.utc)


def csvfile():
    header='fixture_id,gameweek,team_h_name,team_a_name,team_h_score,team_a_score,kickoff_time,finished\n'
    names=['HamKam','Viking','Molde','Rosenborg','Kristiansund','Brann','Aalesund',
           'Lillestrøm','KFUM Oslo','Start','Vålerenga','Sandefjord','Tromsø',
           'Fredrikstad','Sarpsborg 08','Bodø/Glimt']
    rows=[]
    for n in range(112):
        home=names[n%16]
        away=names[(n+1)%16]
        stamp=(dt.date(2026,3,1)+dt.timedelta(days=n)).isoformat()+'T15:00:00Z'
        rows.append(f'{n+1},{n%30+1},{home},{away},2,1,{stamp},True')
    return header+'\n'.join(rows)+'\n'


def season():
    return {'schema':1,'season':'2026-2027','leagues':{
        'pt':{'events':[]},'dk':{'events':[]},
        'no':{'source_season':'2026','events':[{
            'id':'tsdb-1','date':'2026-03-01',
            'home':'Hamarkameratene','away':'Viking',
            'home_score':2,'away_score':1,'finished':True}]},
        'dk2':{'source_season':'2026-2027','events':[]},
        'nl':{'source_season':'2026-2027','events':[]},
    }}


class NorwaySourceTests(unittest.TestCase):
    def test_parse_reconciles_norwegian_team_aliases(self):
        values=parse(csvfile(),NOW)
        self.assertEqual(len(values),112)
        self.assertEqual(values[0]['home'],'Hamarkameratene')
        self.assertEqual(values[8]['home'],'KFUM-Kameratene Oslo')
        self.assertEqual(values[0]['home_score'],2)

    def test_merge_preserves_original_id_no_duplicates_and_daily_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'season.json'
            path.write_text(json.dumps(season()),encoding='utf8')
            calls=[]
            def fake():
                calls.append(1)
                return csvfile()
            r=reconcile(path,fake,NOW)
            self.assertEqual(len(r['leagues']['no']['events']),112)
            self.assertEqual(r['leagues']['no']['events'][0]['id'],'tsdb-1')
            self.assertEqual(r['leagues']['no']['fantasy_research']['confirmed'],1)
            self.assertEqual(r['leagues']['no']['fantasy_research']['conflicts'],0)
            self.assertEqual(len(calls),1)
            second=reconcile(path,fake,NOW+dt.timedelta(hours=1))
            self.assertEqual(len(second['leagues']['no']['events']),112)
            self.assertEqual(len(calls),1)

    def test_conflicting_score_quarantined(self):
        raw=season()
        raw['leagues']['no']['events'][0]['home_score']=9
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'season.json'
            path.write_text(json.dumps(raw),encoding='utf8')
            r=reconcile(path,csvfile,NOW)
            self.assertEqual(r['leagues']['no']['fantasy_research']['conflicts'],1)
            existing=[e for e in r['leagues']['no']['events'] if e['id']=='tsdb-1']
            self.assertEqual(existing[0]['home_score'],9)

    def test_lookahead_score_not_used_for_future_kickoff(self):
        data=csvfile().replace('2026-03-01T15:00:00Z','2026-12-01T15:00:00Z')
        # Duplicate date is allowed if same teams are on different dates,
        # but a future provider score is never entered as a known result.
        parsed=parse(data,NOW)
        self.assertFalse(parsed[0]['finished'])
        self.assertIsNone(parsed[0]['home_score'])

    def test_download_decodes_utf8_with_bom(self):
        class Response:
            status=200
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self,n):return b'\xef\xbb\xbf'+csvfile().encode('utf8')
        with patch('scripts.collect_norwegian_fantasy.urllib.request.urlopen',
                   return_value=Response()):
            self.assertEqual(download(),csvfile())

    def test_unavailable_supplement_preserves_prior_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'season.json'
            path.write_text(json.dumps(season()),encoding='utf8')
            def unavailable():
                raise OSError('Remote source temporarily inaccessible')
            r=reconcile(path,unavailable,NOW)
            self.assertEqual(len(r['leagues']['no']['events']),1)
            self.assertEqual(r['leagues']['no']['fantasy_research']['status'],
                             'source_unavailable')
            self.assertIn('temporarily inaccessible',
                          r['leagues']['no']['fantasy_research']['last_error'])

    def test_invalid_fixture_count_rejected(self):
        tiny=csvfile().splitlines()
        with self.assertRaises(ValueError):
            parse('\n'.join(tiny[:4]),NOW)


class DanishDBUTests(unittest.TestCase):
    def test_official_aliases_match_thesportsdb_names(self):
        self.assertEqual(normalize('Aalborg BK'),'AaB')
        self.assertEqual(normalize('Vejle BK'),'Vejle')
        self.assertEqual(normalize('Hobro IK'),'Hobro')
        with self.assertRaises(ValueError):
            normalize('Unverified Team')

    def test_robots_denied_fails_without_changing_existing_fixtures(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'season.json'
            data=season()
            data['leagues']['dk2']['events']=[{'id':'persist','date':'2026-08-01',
                'home':'Esbjerg','away':'Kolding','finished':True,'home_score':1,'away_score':1}]
            path.write_text(json.dumps(data),encoding='utf8')
            def forbidden(_):
                raise PermissionError('disallowed by robots')
            result=collect_dbu(path,forbidden,NOW)
            self.assertEqual(result['leagues']['dk2']['events'][0]['id'],'persist')
            self.assertEqual(result['leagues']['dk2']['dbu_official']['status'],
                             'unavailable_or_unverified')
            self.assertIn('robots',result['leagues']['dk2']['dbu_official']['error'])

    def test_official_finished_score_can_be_added_and_cached(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'season.json'
            path.write_text(json.dumps(season()),encoding='utf8')
            called=[]
            def html(_):
                called.append(1)
                return '''<html><body><h1>Kampprogram Kampnr</h1><table>
                <tr><th>Kampnr</th><th>Dato</th><th>Tid</th><th>Hjemme</th><th>Ude</th><th>Resultat</th></tr>
                <tr><td>169493</td><td>18-09 2026</td><td>19:00</td>
                <td>Kolding IF</td><td>Hillerød Fodbold</td><td>1 - 1</td></tr>
                </table></body></html>'''
            result=collect_dbu(path,html,NOW)
            self.assertEqual(result['leagues']['dk2']['dbu_official']['added'],1)
            self.assertEqual(result['leagues']['dk2']['events'][0]['home'],'Kolding')
            self.assertEqual(result['leagues']['dk2']['events'][0]['away'],'Hillerød')
            self.assertEqual(result['leagues']['dk2']['events'][0]['home_score'],1)
            collect_dbu(path,html,NOW+dt.timedelta(hours=1))
            self.assertEqual(len(called),1)


if __name__=='__main__':
    unittest.main()
