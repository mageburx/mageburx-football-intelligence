import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_reliability import audit_league, build, summary
from scripts.record_predictions import write_ledger

def games(season, n):
    year=int(season[:4])
    return [
        {'id':f'{season}-{i}', 'date':(dt.date(year,8,1)+dt.timedelta(days=i//10)).isoformat(),
         'home':'Home' if i%2 else 'Away','away':'Away' if i%2 else 'Home',
         'home_score':i%3,'away_score':i%2,'finished':True}
        for i in range(n)
    ]

class ReliabilityTests(unittest.TestCase):
    def test_summary_calibration_and_ci(self):
        records=[('2025-08-04',.70,1,.5),('2025-08-05',.30,0,.5),
                 ('2025-09-04',.60,0,.5),('2025-09-05',.40,1,.5)]
        s=summary(records)
        self.assertEqual(s['n'],4)
        self.assertEqual(sum(x['n'] for x in s['calibration_bins']),4)
        self.assertEqual(len(s['monthly']),2)
        self.assertLess(s['brier'],1)
        self.assertEqual(len(s['brier_gain_ci95']),2)

    def test_holdout_only_late_complete_season(self):
        seasons={'2024-2025':{'events':games('2024-2025',180),'complete':True,'expected_games':180},
                 '2025-2026':{'events':games('2025-2026',200),'complete':True,'expected_games':200}}
        a=audit_league(seasons)
        self.assertEqual(a['holdout']['season'],'2025-2026')
        self.assertEqual(a['holdout']['train_games'],180)
        self.assertEqual(a['metrics']['over_2_5']['n'],200)
        self.assertNotEqual(a['metrics']['over_2_5']['status'],'historico_parcial')
        b=audit_league({**seasons,'2026-2027':{'events':games('2026-2027',200),'complete':True}})
        self.assertEqual(a,b)  # future season never informs historical evaluation

    def test_holdout_includes_january_to_june_of_following_year(self):
        old=games('2024-2025',180)
        test=games('2025-2026',200)
        extra={'id':'jan-extra','date':'2026-01-15','home':'Home','away':'Away',
               'home_score':1,'away_score':1,'finished':True}
        seasons={'2024-2025':{'events':old,'complete':True,'expected_games':180},
                 '2025-2026':{'events':test+[extra],'complete':True,'expected_games':201}}
        audit=audit_league(seasons)
        self.assertEqual(audit['metrics']['over_2_5']['n'],201)

    def test_partial_danish_history_cannot_be_trusted(self):
        seasons={'2023-2024':{'events':games('2023-2024',180),'complete':True},
                 '2024-2025':{'events':games('2024-2025',192),'complete':False,'expected_games':193}}
        a=audit_league(seasons)
        self.assertEqual(a['metrics']['btts_yes']['status'],'historico_parcial')
        self.assertFalse(a['holdout']['complete'])

    def test_ledger_is_append_only_and_no_same_day_records(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'ledger.json'
            now=dt.datetime(2026,11,5,10,0,tzinfo=dt.timezone.utc)
            season={'season':'2026-2027','leagues':{'dk':{'events':[
                {'id':'a','date':'2026-11-06','home':'H','away':'A','finished':False},
                {'id':'b','date':'2026-11-05','home':'H','away':'A','finished':False}]}}}
            model={'leagues':{'dk':{'predictions':{
                'a':{'model':'dc','markets':{'over_2_5':.55,'double_1x':.68}},
                'b':{'model':'dc','markets':{'over_2_5':.85}}}}}}
            first=write_ledger(season,model,path,now)
            self.assertEqual(len(first['predictions']),1)
            fingerprint=first['predictions'][0]['sha256']
            model['leagues']['dk']['predictions']['a']['markets']['over_2_5']=.10
            again=write_ledger(season,model,path,now)
            self.assertEqual(again['predictions'][0]['sha256'],fingerprint)
            self.assertEqual(len(again['predictions']),1)
            season['leagues']['dk']['events'][0].update({'finished':True,'home_score':2,'away_score':1,'result_verified':True,'match_status':'FT'})
            settled=write_ledger(season,model,path,now)
            self.assertEqual(len(settled['settlements']),1)
            repeated=write_ledger(season,model,path,now)
            self.assertEqual(len(repeated['settlements']),1)
            self.assertEqual(repeated['predictions'][0]['sha256'],fingerprint)

if __name__ == '__main__':
    unittest.main()
