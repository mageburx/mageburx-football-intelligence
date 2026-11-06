import copy
import datetime as dt
import json
import math
import tempfile
import unittest
from pathlib import Path

from scripts.collect_danish_first_official import collect,normalize
from scripts.parse_dbu_schedule import future_schedule
from scripts.record_expansion_1x2 import run,summary
from scripts.build_expansion_reliability import build as build_report

NOW=dt.datetime(2026,11,6,18,0,tzinfo=dt.timezone.utc)

HTML='''<html><h2>Kampprogram for Betinia Liga</h2><table>
<tr><th></th><th>Kampnr</th><th>Dato</th><th>Tid</th><th>Hjemme</th><th>Ude</th><th>Resultat</th></tr>
<tr><td></td><td>169493</td><td><div class="matchprogram-date"><span>fre.</span>18-09 2026</div></td><td>19:00</td><td>Kolding IF</td><td>Hillerød Fodbold</td><td>1 - 1</td></tr>
<tr><td></td><td>176297</td><td><div class="matchprogram-date"><span>lør.</span>07-11 2026</div></td><td>13:00</td><td>Hillerød Fodbold</td><td>Kolding IF</td><td></td></tr>
<tr><td></td><td>177771</td><td><div class="matchprogram-date"><span>lør.</span>13-03 2027</div></td><td></td><td>Esbjerg fB</td><td>Hillerød Fodbold</td><td></td></tr>
<tr><td></td><td>176300</td><td>06-11 2026</td><td>19:00</td><td>AaB</td><td>Vejle Boldklub</td><td></td></tr>
<tr><td></td><td>176400</td><td>08-11 2026</td><td>19:00</td><td>Unknown FC</td><td>Vejle Boldklub</td><td></td></tr>
</table></html>'''


def season():
    return {'schema':1,'season':'2026-2027',
            'leagues':{'dk2':{'source_season':'2026-2027','events':[{
                'id':'api-1','date':'2026-09-18','home':'Kolding',
                'away':'Hillerød','finished':True,
                'home_score':1,'away_score':1
            }]},
            'no':{'events':[{'id':'fantasy-no:2026:203','date':'2026-11-07',
                'home':'Kristiansund','away':'Vålerenga','finished':False,
                'home_score':None,'away_score':None}]},
            'nl':{'events':[]}}}


def model():
    return {'generated_at':'2026-11-06T17:30:00+00:00','leagues':{
        'no':{'predictions':{'fantasy-no:2026:203':{
            'p1':0.5,'px':0.3,'p2':0.2,'model':'poisson'}}},
        'dk2':{'predictions':{'dbu:176297':{
            'p1':0.4,'px':0.3,'p2':0.3,'model':'poisson'}}},
        'nl':{'predictions':{}}}}


class OfficialFixtureTests(unittest.TestCase):
    def test_future_dbu_fixture_time_and_missing_time(self):
        games,unknown=future_schedule(HTML,NOW,normalize)
        self.assertEqual(len(games),2)
        self.assertIn('Unknown official Danish club: Unknown FC',unknown)
        self.assertEqual(games[0]['id'],'dbu:176297')
        self.assertEqual(games[0]['date'],'2026-11-07')
        self.assertEqual(games[0]['utc'],'2026-11-07T12:00:00Z')
        self.assertFalse(games[0]['finished'])
        self.assertIsNone(games[0]['home_score'])
        self.assertEqual(games[1]['date'],'2027-03-13')
        self.assertEqual(games[1]['utc'],'')
        self.assertFalse(games[1]['kickoff_time_confirmed'])
        self.assertNotIn('176300',str(games))

    def test_existing_score_preserved_and_future_fixtures_deduped(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'season.json'
            path.write_text(json.dumps(season()),encoding='utf8')
            calls=[]
            def source(_):
                calls.append(1)
                return HTML
            value=collect(path,source,NOW)
            league=value['leagues']['dk2']
            self.assertEqual(len(league['events']),3)
            self.assertEqual(league['events'][0]['id'],'api-1')
            self.assertEqual(league['events'][0]['home_score'],1)
            self.assertEqual(league['dbu_official']['added'],0)
            self.assertEqual(league['dbu_official']['matched'],1)
            self.assertEqual(league['dbu_official']['upcoming_added'],2)
            self.assertEqual(league['dbu_official']['conflicts'],0)
            self.assertEqual(league['dbu_official']['unknown_future_clubs'][0],
                             'Unknown official Danish club: Unknown FC')
            again=collect(path,source,NOW+dt.timedelta(hours=1))
            self.assertEqual(len(again['leagues']['dk2']['events']),3)
            self.assertEqual(len(calls),1)

    def test_upgrade_fetches_future_schedule_even_after_recent_results_check(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'season.json'
            prior=season()
            prior['leagues']['dk2']['dbu_official']={
                'checked_at':'2026-11-06T17:00:00+00:00',
                'status':'sample_available','added':18,'matched':60,
                'conflicts':0,'error':None}
            path.write_text(json.dumps(prior),encoding='utf8')
            calls=[]
            def fetch(_):
                calls.append(1)
                return HTML
            first=collect(path,fetch,NOW)
            self.assertEqual(len(calls),1)
            self.assertEqual(first['leagues']['dk2']['dbu_official']['upcoming_added'],2)
            collect(path,fetch,NOW+dt.timedelta(hours=1))
            self.assertEqual(len(calls),1)

    def test_full_schedule_only_future_is_accepted(self):
        text=HTML.replace('1 - 1','')
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'season.json'
            path.write_text(json.dumps(season()),encoding='utf8')
            out=collect(path,lambda _:text,NOW)
            self.assertEqual(out['leagues']['dk2']['dbu_official']['upcoming_added'],2)

    def test_unknown_schema_rejected(self):
        with self.assertRaises(ValueError):
            future_schedule('<div>Hello</div>',NOW,normalize)


class ProspectiveTests(unittest.TestCase):
    def test_freeze_without_backfill_then_settle_after_match(self):
        initial=run(season(),model(),now=NOW)
        self.assertEqual(len(initial['predictions']),1)
        self.assertEqual(initial['predictions'][0]['league'],'no')
        self.assertEqual(initial['predictions'][0]['probabilities_1x2'],[0.5,0.3,0.2])
        first=initial['predictions'][0]['sha256']
        changed=model()
        changed['leagues']['no']['predictions']['fantasy-no:2026:203']['p1']=0.8
        changed['leagues']['no']['predictions']['fantasy-no:2026:203']['p2']=0.0
        # Forecasts are frozen and not recalculated.
        next_run=run(season(),changed,initial,now=NOW+dt.timedelta(minutes=10))
        self.assertEqual(len(next_run['predictions']),1)
        self.assertEqual(next_run['predictions'][0]['sha256'],first)
        actual=season()
        actual['leagues']['no']['events'][0].update({
            'finished':True,'home_score':2,'away_score':1})
        result=run(actual,changed,next_run,now=NOW+dt.timedelta(days=2))
        self.assertEqual(len(result['settlements']),1)
        measured=summary(result,'no')
        self.assertEqual(measured['issued'],1)
        self.assertEqual(measured['settled'],1)
        self.assertAlmostEqual(measured['brier'],0.38)
        self.assertAlmostEqual(measured['log_loss'],-math.log(0.5),places=5)
        self.assertEqual(measured['status'],'preliminary_only')
        again=run(actual,changed,result,now=NOW+dt.timedelta(days=3))
        self.assertEqual(again,result)

    def test_add_danish_fixture_only_if_model_has_valid_forecast(self):
        data=season()
        data['leagues']['dk2']['events'].append({
            'id':'dbu:176297','date':'2026-11-07','home':'Hillerød',
            'away':'Kolding','finished':False})
        first=run(data,model(),now=NOW)
        self.assertEqual({e['league'] for e in first['predictions']},
                         {'no','dk2'})
        m=model()
        m['leagues']['dk2']['predictions']['dbu:176297']['p1']=float('nan')
        rejected=run(data,m,now=NOW)
        self.assertEqual(len(rejected['predictions']),1)

    def test_does_not_settle_same_day_or_retroactive_unlogged_match(self):
        recorded=run(season(),model(),now=NOW)
        happened=season()
        happened['leagues']['no']['events'][0].update({
            'finished':True,'home_score':2,'away_score':1})
        self.assertEqual(len(run(happened,model(),recorded,now=NOW+dt.timedelta(hours=1))['settlements']),0)
        nohistory=run(happened,model(),now=NOW+dt.timedelta(days=2))
        self.assertEqual(len(nohistory['predictions']),0)
        self.assertEqual(len(nohistory['settlements']),0)

    def test_reliability_report_separates_1x2_from_market_forecasts(self):
        ledger=run(season(),model(),now=NOW)
        report=build_report(season(),{},one_x_two_ledger=ledger,now=NOW)
        self.assertEqual(report['leagues']['no']['prospective_1x2']['issued'],1)
        self.assertEqual(report['leagues']['no']['prospective_1x2']['settled'],0)
        self.assertIsNone(report['leagues']['no']['prospective_1x2']['brier'])


if __name__=='__main__':
    unittest.main()
