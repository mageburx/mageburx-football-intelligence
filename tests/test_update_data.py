import json
from pathlib import Path
from scripts.update_data import parse_event, collect, SEASON


def make_event(id='10', season=SEASON, date='2026-08-09', hs='3', aws='1'):
    return {'idEvent': id, 'strSeason': season, 'idLeague': '4344', 'dateEvent': date, 'strHomeTeam': 'Casa', 'strAwayTeam': 'Fora', 'intHomeScore': hs, 'intAwayScore': aws, 'intRound': '1', 'strTimestamp': date + 'T19:00:00'}


def test_parse_scores():
    e = parse_event(make_event(), 'pt')
    assert e['finished'] and e['home_score'] == 3
    assert parse_event(make_event(season='2025-2026'), 'pt') is None
    assert parse_event(make_event(hs=None), 'pt')['finished'] is False


def test_future_not_finished():
    e = parse_event(make_event(date='2027-05-01', hs=None, aws=None), 'pt')
    assert e['home_score'] is None


def test_merge_keeps_old_on_errors(tmp_path):
    path = tmp_path / 'season.json'
    path.write_text(json.dumps({'leagues': {'pt': {'events': [{'id': 'saved', 'date': '2026-08-01'}]}}}), encoding='utf8')
    def fetcher(lid, n):
        if lid == 'dk':
            raise RuntimeError('sem rede')
        return [parse_event(make_event(), 'pt')]
    out = collect(path, pause=0, max_round=1, fetcher=fetcher)
    assert len(out['leagues']['pt']['events']) == 2
    assert out['leagues']['dk']['partial'] is True
    assert out['leagues']['dk']['rounds_failed'] == [1]
