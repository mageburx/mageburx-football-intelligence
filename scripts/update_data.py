#!/usr/bin/env python3
"""Afonso OS Football Lab: recolha legal através dos endpoints oficiais TheSportsDB.

Sem scraping de sites de apostas, sem credenciais, sem envio de apostas.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import random
import time
import urllib.error
import urllib.parse
import urllib.request
try:
    from scripts.match_status import final_confirmed, normalize_status
except ModuleNotFoundError:
    from match_status import final_confirmed, normalize_status

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / 'data' / 'season.json'
API = 'https://www.thesportsdb.com/api/v1/json/123/eventsround.php'
SEASON = '2026-2027'
LEAGUES = {
    'pt': {'id': 4344, 'name': 'Liga Portugal Betclic', 'country': 'Portugal', 'rounds': 34},
    'dk': {'id': 4340, 'name': '3F Superliga', 'country': 'Dinamarca', 'rounds': 32},
}


def parse_event(event, league_id):
    """Restringir os campos e validar a época antes de guardar."""
    if str(event.get('strSeason', SEASON)) != SEASON:
        return None
    if str(event.get('idLeague')) != str(LEAGUES[league_id]['id']):
        return None
    date = str(event.get('dateEvent') or '')[:10]
    try:
        dt.date.fromisoformat(date)
    except ValueError:
        return None
    home = str(event.get('strHomeTeam') or '').strip()
    away = str(event.get('strAwayTeam') or '').strip()
    if not home or not away:
        return None
    def score(v):
        try:
            n = int(v)
            return n if 0 <= n < 100 else None
        except (ValueError, TypeError):
            return None
    hs, aws = score(event.get('intHomeScore')), score(event.get('intAwayScore'))
    completed = hs is not None and aws is not None and final_confirmed(event)
    status = normalize_status(event.get('strStatus'))
    live_hs, live_as = hs, aws
    if not completed:
        hs, aws = None, None
    try:
        rnd = int(event.get('intRound') or 0)
    except (ValueError, TypeError):
        rnd = 0
    return {
        'id': str(event.get('idEvent') or f'{league_id}:{date}:{home}:{away}'),
        'date': date,
        'utc': str(event.get('strTimestamp') or ''),
        'round': rnd,
        'home': home,
        'away': away,
        'home_score': hs,
        'away_score': aws,
        'finished': completed,
        'result_verified': completed,
        'match_status': status,
        'progress': str(event.get('strProgress') or ''),
        'live_home_score': live_hs if not completed else None,
        'live_away_score': live_as if not completed else None,
    }


def fetch_round(league_id, round_num, timeout=25, retries=3):
    params = {'id': LEAGUES[league_id]['id'], 'r': round_num, 's': SEASON}
    url = API + '?' + urllib.parse.urlencode(params)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'AfonsoOSFootballLab/1.0 (public sports data; github actions)', 'Accept': 'application/json'})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = json.load(resp)
            if not isinstance(raw, dict):
                raise ValueError('Payload inesperado')
            events = raw.get('events') or []
            if not isinstance(events, list):
                raise ValueError('Eventos inválidos')
            return [x for e in events if (x := parse_event(e, league_id))]
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            if attempt == retries - 1:
                raise RuntimeError(f'{league_id} jornada {round_num}: {exc}') from exc
            time.sleep((attempt + 1) * 6 + random.random())
    return []


def load_previous(path):
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding='utf-8'))
        return obj if isinstance(obj, dict) else {}
    except (ValueError, OSError):
        return {}


def collect(out, pause=3.5, max_round=None, fetcher=fetch_round):
    """Atualização incremental: jornadas em falta e jogos recentes, sem esgotar a API gratuita."""
    old = load_previous(out)
    now = dt.datetime.now(dt.timezone.utc)
    today = now.date()
    result = {'schema': 1, 'season': SEASON,
              'source': {'name': 'TheSportsDB', 'url': 'https://www.thesportsdb.com/', 'api': 'v1 gratuita'},
              'updated_at': now.replace(microsecond=0).isoformat(),
              'leagues': {key:value for key,value in (old.get('leagues') or {}).items()
                          if key in ('nl','dk2','no') and isinstance(value,dict)}}
    any_data = False
    for lid, lg in LEAGUES.items():
        prev = old.get('leagues', {}).get(lid, {})
        saved = {str(e.get('id')): e for e in prev.get('events', []) if isinstance(e, dict) and e.get('id')}
        fixtures_per_round = 9 if lid == 'pt' else 6
        known = list(saved.values())
        past_rounds = [int(e.get('round') or 0) for e in known
                       if e.get('date') and e['date'] <= today.isoformat()]
        current_round = max(past_rounds, default=1)
        # Os jogos futuros da fase final podem não estar calendarizados.
        # Não requisitar 34/32 jornadas diariamente: a API limita pedidos (429).
        ceiling = min(lg['rounds'], max_round or lg['rounds'], current_round + 2)
        by_round = {}
        for e in known:
            by_round.setdefault(int(e.get('round') or 0), []).append(e)
        missing = [i for i in range(1, ceiling + 1)
                   if len(by_round.get(i, [])) < fixtures_per_round]
        recent = []
        for round_num, group in by_round.items():
            if not (1 <= round_num <= ceiling):
                continue
            if any(e.get('date') and (today - dt.timedelta(days=10)).isoformat() <=
                   e['date'] <= (today + dt.timedelta(days=15)).isoformat()
                   for e in group):
                recent.append(round_num)
        targets = sorted(set(missing + recent), key=lambda i: (i not in missing, i))
        failed = []
        ok = 0
        for round_num in targets:
            try:
                group = fetcher(lid, round_num)
                if len(group) < fixtures_per_round:
                    failed.append(round_num)
                    print(f'AVISO {lid} jornada {round_num}: apenas {len(group)}/{fixtures_per_round} jogos', flush=True)
                else:
                    ok += 1
                for e in group:
                    saved[e['id']] = e
                print(f'{lid}: jornada {round_num}: {len(group)} jogos', flush=True)
            except Exception as exc:
                failed.append(round_num)
                print('AVISO', exc, flush=True)
            if pause and round_num != targets[-1]:
                time.sleep(pause)
        events = sorted(saved.values(), key=lambda e: (e['date'], e.get('utc',''), e['id']))
        any_data |= bool(events)
        by_round_final = {}
        for e in events:
            by_round_final.setdefault(int(e.get('round') or 0), []).append(e)
        missing_past = [i for i in range(1, current_round + 1)
                        if len(by_round_final.get(i, [])) < fixtures_per_round]
        # Não apresentar classificação como completa se faltarem jogos já disputados.
        partial = bool(missing_past or failed)
        result['leagues'][lid] = {'name': lg['name'], 'country': lg['country'], 'id': lg['id'],
                                  'events': events, 'rounds_ok': ok, 'rounds_failed': failed,
                                  'missing_past_rounds': missing_past,
                                  'partial': partial, 'last_attempt_at': result['updated_at']}
        print(f'{lid}: atuais {current_round}; alvos {targets}; jornadas em falta {missing_past}', flush=True)
    if not any_data:
        raise RuntimeError('Nenhuma informação foi recolhida — dados antigos preservados')
    out.parent.mkdir(parents=True, exist_ok=True)
    temp = out.with_suffix('.tmp')
    temp.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    temp.replace(out)
    print(f'Atualizado: {out} (PT: {len(result["leagues"]["pt"]["events"])}; DK: {len(result["leagues"]["dk"]["events"])}; novas ligas preservadas)')
    return result

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, default=DEFAULT_OUT)
    p.add_argument('--pause', type=float, default=3.5)
    p.add_argument('--max-round', type=int, default=None, help='Só para testes; deixa snapshot incompleto')
    args = p.parse_args()
    collect(args.output, args.pause, args.max_round)
