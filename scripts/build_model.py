#!/usr/bin/env python3
"""Football Intelligence v3: pre-match probabilistic forecasts & leakage-safe walk-forward audit.

No odds, xG, or injury adjustments are inferred. Output is exploratory, not calibrated
unless supported by an adequately sized chronological holdout.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TODAY = dt.datetime.now(dt.timezone.utc).date()
HALF_LIFE = 150.0
PRIOR_MATCHES = 5.0
DC_RHO = -0.06  # heuristic, NOT fitted; tested against independent Poisson
HOME_ELO = 60.0
ELO_K = 22.0
MIN_TRAIN = 30
MIN_EVAL = 30

def finished(e):
    return (e.get('finished') is True and isinstance(e.get('home_score'), int)
            and not isinstance(e['home_score'], bool)
            and isinstance(e.get('away_score'), int)
            and not isinstance(e['away_score'], bool))

def normalise(p):
    vals = [max(1e-9, float(x)) for x in p]
    z = sum(vals)
    return [x / z for x in vals]

def poisson(k, lam):
    return math.exp(-lam) * lam ** k / math.factorial(k)

def outcome(e):
    return 0 if e['home_score'] > e['away_score'] else (1 if e['home_score'] == e['away_score'] else 2)

def match_key(e):
    return str(e.get('id') or f"{e.get('date')}:{e['home']}:{e['away']}")

def usable(events):
    # A single result per id; never use outcomes after TODAY.
    by_id = {}
    for e in events:
        if e.get('date') and e.get('home') and e.get('away'):
            by_id[match_key(e)] = e
    return sorted(by_id.values(), key=lambda e: (e['date'], str(e.get('utc') or ''), match_key(e)))

def goal_rates(history, asof, home, away, dc=True):
    """Smoothed home/away team attack and defence using exponentially decayed past only."""
    before = [e for e in history if finished(e) and e['date'] < asof]
    if len(before) < MIN_TRAIN:
        return None
    sums = defaultdict(float)
    teams = defaultdict(lambda: defaultdict(float))
    for e in before:
        age = max(0, (dt.date.fromisoformat(asof) - dt.date.fromisoformat(e['date'])).days)
        weight = 2 ** (-age / HALF_LIFE)
        sums['weight'] += weight
        sums['home'] += weight * e['home_score']
        sums['away'] += weight * e['away_score']
        for t, role, scored, conceded in ((e['home'], 'home', e['home_score'], e['away_score']),
                                          (e['away'], 'away', e['away_score'], e['home_score'])):
            a = teams[t]
            a[role + '_n'] += weight
            a[role + '_gf'] += weight * scored
            a[role + '_ga'] += weight * conceded
            a['n'] += 1
    mh = max(.3, sums['home'] / sums['weight'])
    ma = max(.3, sums['away'] / sums['weight'])
    h, a = teams[home], teams[away]
    if h['n'] < 2 or a['n'] < 2:
        return None
    def avg(v, n, baseline):
        return (v + PRIOR_MATCHES * baseline) / (n + PRIOR_MATCHES)
    lh = (avg(h['home_gf'], h['home_n'], mh) *
          avg(a['away_ga'], a['away_n'], mh)) / mh
    la = (avg(a['away_gf'], a['away_n'], ma) *
          avg(h['home_ga'], h['home_n'], ma)) / ma
    return max(.15, min(4.0, lh)), max(.15, min(4.0, la))

def score_probs(lh, la, dc=True):
    """Dixon-Coles low-score dependence correction for Poisson score grid."""
    probs = [0.0, 0.0, 0.0]
    over = btts = mass = 0.0
    rho = DC_RHO if dc else 0.0
    for h in range(13):
        for a in range(13):
            tau = 1.0
            if h == 0 and a == 0:
                tau = 1 - lh * la * rho
            elif h == 0 and a == 1:
                tau = 1 + lh * rho
            elif h == 1 and a == 0:
                tau = 1 + la * rho
            elif h == 1 and a == 1:
                tau = 1 - rho
            p = poisson(h, lh) * poisson(a, la) * max(0.0, tau)
            mass += p
            probs[0 if h > a else 1 if h == a else 2] += p
            if h + a >= 3:
                over += p
            if h > 0 and a > 0:
                btts += p
    return {'p': normalise(probs), 'over': over / mass, 'btts': btts / mass,
            'lambdaH': lh, 'lambdaA': la}

def elo_probs(history, asof, home, away):
    """Elo updated in date batches; no same-day or future leakage."""
    ratings = defaultdict(lambda: 1500.0)
    before = [e for e in history if finished(e) and e['date'] < asof]
    if len(before) < MIN_TRAIN:
        return None
    dates = sorted({e['date'] for e in before})
    for date in dates:
        changes = defaultdict(float)
        for e in (x for x in before if x['date'] == date):
            h, a = ratings[e['home']], ratings[e['away']]
            ph = 1.0 / (1.0 + 10 ** (-(h + HOME_ELO - a) / 400.0))
            y = 1.0 if e['home_score'] > e['away_score'] else .5 if e['home_score'] == e['away_score'] else 0.0
            changes[e['home']] += ELO_K * (y - ph)
            changes[e['away']] -= ELO_K * (y - ph)
        for t, delta in changes.items():
            ratings[t] += delta
    decisive_home = 1.0 / (1.0 + 10 ** (-(ratings[home] + HOME_ELO - ratings[away]) / 400.0))
    observed_draws = sum(e['home_score'] == e['away_score'] for e in before)
    draw = (observed_draws + 25 * .26) / (len(before) + 25)
    draw *= (1 - .36 * abs(decisive_home - .5) * 2)
    return normalise([(1 - draw) * decisive_home, draw, (1 - draw) * (1 - decisive_home)])

def variants(history, asof, match):
    rates = goal_rates(history, asof, match['home'], match['away'])
    if rates is None:
        return None
    baseline = score_probs(*rates, dc=False)
    dc = score_probs(*rates, dc=True)
    elo = elo_probs(history, asof, match['home'], match['away'])
    mix = normalise([.8 * x + .2 * y for x, y in zip(dc['p'], elo)]) if elo else dc['p']
    return {'poisson': baseline['p'], 'dc': dc['p'], 'blend': mix, 'extra': dc}

def brier(p, y):
    return sum((v - float(j == y)) ** 2 for j, v in enumerate(p))

def logloss(p, y):
    return -math.log(max(1e-9, p[y]))

def evaluate(events):
    """Strict walk-forward: evaluate date's matches using only earlier dates."""
    played = [e for e in usable(events) if finished(e) and e['date'] <= TODAY.isoformat()]
    scored = defaultdict(list)
    for e in played:
        pred = variants(played, e['date'], e)
        if pred is None:
            continue
        for name in ('poisson', 'dc', 'blend'):
            p = pred[name]
            scored[name].append((brier(p, outcome(e)), logloss(p, outcome(e))))
    summary = {}
    for name, values in scored.items():
        n = len(values)
        summary[name] = {'n': n, 'brier': round(sum(x[0] for x in values)/n, 4),
                         'log_loss': round(sum(x[1] for x in values)/n, 4)}
    # No claim of improvement with tiny samples. Compare to the independent Poisson.
    selected = 'poisson'
    if summary.get('blend', {}).get('n', 0) >= MIN_EVAL:
        best = min(('poisson', 'dc', 'blend'), key=lambda n: summary[n]['brier'])
        if summary['poisson']['brier'] - summary[best]['brier'] >= .005:
            selected = best
    return summary, selected

def build(data, asof=None):
    asof = asof or TODAY.isoformat()
    result = {'schema': 3, 'method': 'Poisson independente; Dixon-Coles (rho fixo); Elo; mistura 80/20',
              'generated_at': dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
              'note': 'Avaliação walk-forward na época atual; seleção exploratória, não teste independente. Sem xG, lesões ou notícias quantificados.',
              'leagues': {}}
    for lid, info in data['leagues'].items():
        events = usable(info.get('events', []))
        played = [e for e in events if finished(e) and e['date'] < asof]
        stats, chosen = evaluate(events)
        forecasts = {}
        for m in events:
            if finished(m) or m['date'] < asof:
                continue
            v = variants(played, asof, m)
            if v is None:
                continue
            p = v[chosen]
            extras = v['extra']
            forecasts[match_key(m)] = {'p1': round(p[0], 5), 'px': round(p[1], 5),
                                        'p2': round(p[2], 5), 'over': round(extras['over'], 5),
                                        'btts': round(extras['btts'], 5),
                                        'lambdaH': round(extras['lambdaH'], 3),
                                        'lambdaA': round(extras['lambdaA'], 3),
                                        'leagueMatches': len(played),
                                        'model': chosen,
                                        'note': 'Modelo experimental: sem validação independente fora da amostra.'}
        result['leagues'][lid] = {'played': len(played), 'evaluations': stats,
                                   'selected': chosen, 'predictions': forecasts,
                                   'sample_warning': len(played) < 150,
                                   'data_partial': bool(info.get('partial', True))}
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, default=ROOT / 'data' / 'season.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'data' / 'model.json')
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding='utf-8'))
    model = build(data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(model, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Modelo v3:', json.dumps({k: {'n': v['played'], 'selected': v['selected'], 'backtest': v['evaluations'],
                                        'upcoming': len(v['predictions'])} for k, v in model['leagues'].items()}))

if __name__ == '__main__':
    main()
