#!/usr/bin/env python3
"""Zero-cost scouting of public match-stat coverage (metadata only).

This explicitly does NOT copy/rehost match records from third-party feeds.
Cornerflick's compilation is CC BY 4.0, but underlying data providers have
separate rights. Evaluate *small samples* and license compatibility before
considering paid services, bulk collection, or predictive markets.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import math
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'data' / 'stats_coverage.json'
SOURCE = 'https://cornerflick.com'
FEEDS = {
    'pt': '/football/leagues/primeira-liga/results/season.json',
    'dk': '/football/leagues/danish-superliga/results/season.json',
}
FIELDS = ('Corners', 'Yellow Cards', 'Red Cards', 'Shots', 'Shots on Target')
USER_AGENT = 'MageburxFootballResearch/1.0 (+https://github.com/mageburx/mageburx-football-intelligence)'
MAX_MATCHES = 2

def fetch_json(url):
    if not url.startswith(SOURCE + '/'):
        raise ValueError('Refusing request outside declared source')
    req = urllib.request.Request(url, headers={
        'User-Agent': USER_AGENT,
        'Accept': 'application/json',
    })
    with urllib.request.urlopen(req, timeout=17) as resp:
        if resp.status != 200:
            raise ValueError(f'HTTP {resp.status}')
        return json.load(resp)

def stat_is_valid(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and 0 <= x <= 200

def assess(fetcher=fetch_json, sleep=time.sleep, sample_per_league=MAX_MATCHES):
    report = {
        'schema': 1,
        'generated_at': dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        'source': {'name': 'Cornerflick', 'url': SOURCE, 'license': 'CC BY 4.0 (published compilation)',
                   'attribution': 'Data by Cornerflick — cornerflick.com',
                   'rights_note': 'Original match facts originate from other providers. Commercial scale redistribution requires further permission review.'},
        'purpose': 'Limited non-commercial feasibility test; no live markets or raw third-party match data.',
        'leagues': {}
    }
    for league, path in FEEDS.items():
        item = {'status': 'not_checked', 'match_count': 0, 'coverage_dates': None,
                'sample_checked': 0, 'valid_match_samples': 0,
                'stats_fields_validated': {field: 0 for field in FIELDS},
                'sample_missing_fields': [], 'reason': None}
        report['leagues'][league] = item
        try:
            data = fetcher(SOURCE + path)
            meta = data.get('meta') or {}
            matches = data.get('matches') or []
            if meta.get('license') != 'CC BY 4.0' or not matches:
                raise ValueError('License or season format changed')
            ids = [m.get('id') for m in matches]
            if len(set(ids)) != len(ids):
                raise ValueError('Duplicate source match IDs')
            item['match_count'] = len(matches)
            item['coverage_dates'] = meta.get('temporal_coverage')
            # sample spread across the available season instead of cherry picking
            selected = [matches[round(i*(len(matches)-1)/max(1,sample_per_league-1))]
                        for i in range(min(len(matches),sample_per_league))]
            seen = set()
            for match in selected:
                if match['id'] in seen:
                    continue
                seen.add(match['id'])
                url = match.get('dataset_url', '')
                if not url.startswith(SOURCE+'/football/'):
                    raise ValueError('Unexpected match dataset URL')
                sleep(1.5)
                raw = fetcher(url)
                item['sample_checked'] += 1
                meta_match = raw.get('meta') or {}
                stat_list = raw.get('statistics') or []
                if meta_match.get('license') != 'CC BY 4.0':
                    continue
                if not isinstance(stat_list, list):
                    continue
                stats = {s.get('label'): s for s in stat_list if isinstance(s, dict)}
                ok_fields = 0
                for field in FIELDS:
                    value = stats.get(field, {})
                    if stat_is_valid(value.get('home')) and stat_is_valid(value.get('away')):
                        item['stats_fields_validated'][field] += 1
                        ok_fields += 1
                    else:
                        item['sample_missing_fields'].append(field)
                if ok_fields == len(FIELDS):
                    item['valid_match_samples'] += 1
            item['status'] = 'sample_available' if item['valid_match_samples'] else 'sample_incomplete'
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            item['status'] = 'unavailable'
            item['reason'] = str(exc)[:200]
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output',type=Path,default=OUTPUT)
    p.add_argument('--sample',type=int,default=MAX_MATCHES)
    args=p.parse_args()
    sample=max(0,min(MAX_MATCHES,args.sample))
    result=assess(sample_per_league=sample)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print('Source coverage:',json.dumps(result['leagues'],ensure_ascii=False))

if __name__=='__main__':
    main()
