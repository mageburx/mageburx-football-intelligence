#!/usr/bin/env python3
"""Reconcile Danish Superliga historic results against documented European play-offs.

TheSportsDB older seasons re-use round numbers 1–10 in the post-season.
Canonical team names match OpenFootball historic seasons.
Five European play-off fixtures are independently source-documented. They are
counted for season completeness but excluded from ordinary 90-minute match
probability training, because competition context and extra-time vary.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / 'data' / 'history.json'
TEAM_ALIASES = {
    'AGF Aarhus':'Aarhus GF',
    'AaB':'Aalborg BK',
    'Brøndby':'Brøndby IF',
    'FC Copenhagen':'FC København',
    'Lyngby':'Lyngby BK',
    'Viborg':'Viborg FF',
    'Sønderjyske':'SønderjyskE',
    'Vejle Boldklub':'Vejle BK',
    'Vejle':'Vejle BK',
    'Fredericia':'FC Fredericia',
    'Aalborg':'Aalborg BK',
    'AGF':'Aarhus GF',
    'Odense':'Odense BK',
}
# Official DBU unless noted. Score after extra time in 2021/22, 2025/26.
PLAYOFFS = {
    '2021-2022': {
        'date':'2022-05-29','home':'Aalborg BK','away':'Viborg FF',
        'home_score':1,'away_score':1,'result_basis':'after_extra_time',
        'source_url':'https://fbref.com/en/comps/50/2021-2022/schedule/2021-2022-Danish-Superliga-Scores-and-Fixtures',
        'source_name':'FBref: Danish Superliga fixture listing'},
    '2022-2023': {
        'date':'2023-06-09','home':'Viborg FF','away':'FC Midtjylland',
        'home_score':0,'away_score':1,'result_basis':'regulation',
        'source_url':'https://www.dbu.dk/resultater/kamp/499250_413331/kampinfo',
        'source_name':'DBU official match record'},
    '2023-2024': {
        'date':'2024-05-31','home':'FC København','away':'Randers FC',
        'home_score':2,'away_score':1,'result_basis':'regulation',
        'source_url':'https://www.dbu.dk/resultater/kamp/281960_437002/kampinfo',
        'source_name':'DBU official match record'},
    '2024-2025': {
        'date':'2025-06-01','home':'Randers FC','away':'Silkeborg IF',
        'home_score':1,'away_score':3,'result_basis':'regulation',
        'source_url':'https://www.dbu.dk/resultater/kamp/640962_472802/kampinfo',
        'source_name':'DBU official match record'},
    '2025-2026': {
        'date':'2026-05-21','home':'Brøndby IF','away':'FC København',
        'home_score':1,'away_score':3,'result_basis':'after_extra_time',
        'source_url':'https://www.dbu.dk/resultater/pulje/503898/opslagstavle',
        'source_name':'DBU official match record'},
}
REQUIRED_ROUNDS={'2021-2022':22,'2022-2023':22,
                 '2025-2026':32}

def canonical(name):
    return TEAM_ALIASES.get(name,name)

def reconcile(history):
    seasons = history['leagues']['dk']['seasons']
    for year,playoff in PLAYOFFS.items():
        season=seasons.setdefault(year,{'events':[],'complete':False,'expected_games':193})
        raw=season.get('events',[])
        for event in raw:
            event['home']=canonical(event['home'])
            event['away']=canonical(event['away'])
            if event['home']==event['away']:
                raise ValueError(f'Same club plays itself: {year} {event}')
        match=[x for x in raw if (x['date'],x['home'],x['away'])==(
            playoff['date'],playoff['home'],playoff['away'])]
        if len(match)>1:
            raise ValueError(f'Duplicate European play-off fixture: {year}')
        if match:
            event=match[0]
            if (event['home_score'],event['away_score'])!=(
                playoff['home_score'],playoff['away_score']):
                raise ValueError(f'Conflicting European play-off result: {year}')
        else:
            event={'id':f'official-playoff:dk:{year}','date':playoff['date'],
                   'round':33,'home':playoff['home'],'away':playoff['away'],
                   'home_score':playoff['home_score'],
                   'away_score':playoff['away_score'],'finished':True}
            raw.append(event)
        event['stage']='european_playoff'
        event['model_eligible']=False
        event['result_basis']=playoff['result_basis']
        event['source_url']=playoff['source_url']
        event['source_name']=playoff['source_name']
        season['events']=sorted(raw,key=lambda e:(e['date'],str(e['id'])))
        season['actual_games']=len(raw)
        season['expected_games']=193
        rounds=set(int(x) for x in season.get('fetched_rounds',[]))
        all_rounds=(len(rounds)==REQUIRED_ROUNDS[year] and
                    rounds==set(range(1,REQUIRED_ROUNDS[year]+1))) if year in REQUIRED_ROUNDS else True
        complete=bool(season['actual_games']==193 and
                      (year not in REQUIRED_ROUNDS or all_rounds))
        season['complete']=complete
        print(f'{year}: {season["actual_games"]}/193, '
              f'{len(rounds)}/{REQUIRED_ROUNDS.get(year,0)} API rounds, '
              f'complete={complete}',flush=True)
    return history

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--input',type=Path,default=PATH)
    args=p.parse_args()
    data=json.loads(args.input.read_text(encoding='utf8'))
    changed=reconcile(data)
    args.input.write_text(json.dumps(changed,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf8')

if __name__=='__main__':
    main()
