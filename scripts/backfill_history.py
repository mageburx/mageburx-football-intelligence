#!/usr/bin/env python3
"""Backfill five Danish Superliga seasons with TheSportsDB free round API.

The full five Portuguese seasons and two Danish seasons are sourced from
OpenFootball CC0 and stored independently in data/history.json. Remaining
Danish seasons are filled gradually, without mislabeling missing rounds as done.
No result is fabricated; API errors preserve already downloaded matches.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / 'data' / 'history.json'
NEEDED = ('2021-2022', '2022-2023', '2025-2026')
API = 'https://www.thesportsdb.com/api/v1/json/123/eventsround.php'
LEAGUE_ID = '4340'
ROUNDS = range(1, 33)

def get_round(season: str, round_number: int, retries: int = 2):
    url = API + '?' + urllib.parse.urlencode({'id': LEAGUE_ID, 's': season, 'r': round_number})
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'FootballIntelligenceResearch/1.0 (public data)', 'Accept': 'application/json'})
            with urllib.request.urlopen(req, timeout=20) as response:
                payload = json.load(response)
            if not isinstance(payload, dict) or not isinstance(payload.get('events'), list):
                raise ValueError('Resposta de eventos incompleta')
            result = []
            for e in payload['events']:
                if str(e.get('idLeague')) != LEAGUE_ID or e.get('strSeason') != season:
                    continue
                date = str(e.get('dateEvent') or '')[:10]
                try:
                    day = dt.date.fromisoformat(date)
                    if not (int(season[:4]) <= day.year <= int(season[:4]) + 1):
                        continue
                    h, a = int(e.get('intHomeScore')), int(e.get('intAwayScore'))
                    assert 0 <= h < 30 and 0 <= a < 30
                except (ValueError, TypeError, AssertionError):
                    continue
                home, away = str(e.get('strHomeTeam') or '').strip(), str(e.get('strAwayTeam') or '').strip()
                if not home or not away or home == away:
                    continue
                result.append({'id': 'tsdb:' + str(e.get('idEvent')), 'date': date,
                               'round': int(e.get('intRound') or round_number),
                               'home': home, 'away': away, 'home_score': h,
                               'away_score': a, 'finished': True})
            return result
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            if attempt + 1 >= retries:
                raise RuntimeError(f'{season} jornada {round_number}: {exc}') from exc
            time.sleep(10 * (attempt + 1) + random.random())
    return []

def collect(path=PATH, max_calls=18, pause=4.0, fetcher=get_round):
    if not path.exists():
        raise RuntimeError('data/history.json não existe — importar primeiro OpenFootball')
    history = json.loads(path.read_text(encoding='utf-8'))
    dk = history['leagues']['dk']['seasons']
    needed = []
    for season in NEEDED:
        item = dk.setdefault(season, {'events': [], 'actual_games': 0, 'expected_games': 192,
                                      'complete': False, 'verified_from': 'TheSportsDB eventsround API',
                                      'fetched_rounds': []})
        known = set(item.get('fetched_rounds', []))
        for round_number in ROUNDS:
            if round_number not in known:
                needed.append((season, round_number))
    # Stagger season requests, rather than 32 consecutive calls to one season.
    needed.sort(key=lambda x: (x[1], x[0]))
    attempted = ok = 0
    changed = False
    for season, round_number in needed[:max_calls]:
        attempted += 1
        try:
            matches = fetcher(season, round_number)
            if not matches:
                print(f'AVISO {season}: jornada {round_number} vazia; será repetida', flush=True)
            else:
                old = dk[season]
                merged = {m['id']: m for m in old['events']}
                for event in matches:
                    merged[event['id']] = event
                old['events'] = sorted(merged.values(), key=lambda e: (e['date'], e['id']))
                old['fetched_rounds'] = sorted(set(old.get('fetched_rounds', []) + [round_number]))
                old['actual_games'] = len(old['events'])
                # Completeness also requires all 32 rounds checked successfully.
                old['complete'] = (len(old['fetched_rounds']) == 32 and
                                   old['actual_games'] >= 192)
                ok += 1
                changed = True
                print(f'{season} J{round_number}: {len(matches)} jogos; total {old["actual_games"]}', flush=True)
        except RuntimeError as exc:
            print('AVISO', exc, flush=True)
        if pause and attempted < min(len(needed), max_calls):
            time.sleep(pause)
    if changed:
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(history, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
        temp.replace(path)
    print(json.dumps({'attempted': attempted, 'successful_rounds': ok,
                      'coverage': {s: {'rounds': len(dk[s].get('fetched_rounds', [])),
                                       'games': dk[s]['actual_games'],
                                       'complete': dk[s]['complete']} for s in NEEDED}}))
    return history

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--max-calls', type=int, default=18)
    p.add_argument('--pause', type=float, default=4.0)
    args = p.parse_args()
    collect(max_calls=args.max_calls, pause=args.pause)
