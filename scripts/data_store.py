#!/usr/bin/env python3
"""Git-backed durable snapshot store on the dedicated football-data branch.

Unlike a 90-day Actions artifact or the most recent Pages deployment, commits
on the data branch are retained in normal repository history until deliberately
deleted by a repository administrator. This is not WORM/cryptographic immutability.
Use the least-privilege GitHub Actions token (contents:write).
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BRANCH = 'football-data'
TRACKED = ('history.json', 'ledger.json', 'season.json', 'model.json',
           'reliability.json', 'quality.json', 'validation.json', 'scrape_report.json', 'stats_coverage.json', 'value_engine.json', 'feature_impact.json',
           'cross_competitions.json', 'schedule_context.json', 'prematch_lineups.json',
           'multi_competition_impact.json', 'ledger_health.json', 'european_coverage.json', 'advanced_signals.json', 'shots_research.json', 'xg_experiment.json', 'xg_shadow_ledger.json', 'nl_history.json', 'expansion_reliability.json', 'expansion_1x2_ledger.json', 'expansion_1x2_audit.json','league_comparison.json','validation_center.json','data_coverage.json','expanded_history.json')

def git(*args, cwd=ROOT, check=True):
    return subprocess.run(['git', *args], cwd=cwd, check=check,
                          text=True, capture_output=True)

def read_remote(branch_file):
    data = git('show', f'origin/{BRANCH}:data/{branch_file}', check=False)
    if data.returncode:
        return None
    try:
        return json.loads(data.stdout)
    except json.JSONDecodeError:
        raise ValueError(f'Invalid saved JSON: data/{branch_file}')

def restore(root=ROOT):
    fetch = git('fetch', '--no-tags', 'origin', f'+refs/heads/{BRANCH}:refs/remotes/origin/{BRANCH}', check=False)
    if fetch.returncode:
        raise RuntimeError('Could not fetch persistent state branch: ' + fetch.stderr[-500:])
    try:
        from scripts.restore_published_state import merge_history, merge_ledger
    except ModuleNotFoundError:
        from restore_published_state import merge_history, merge_ledger
    for name, merger in (('history.json', merge_history), ('ledger.json', merge_ledger)):
        prior = read_remote(name)
        if prior is None:
            print(f'{name}: no persistent snapshot on branch yet')
            continue
        path = root / 'data' / name
        local = json.loads(path.read_text(encoding='utf-8')) if path.exists() else (
            {'schema': 1, 'predictions': [], 'settlements': []} if name == 'ledger.json' else None)
        if local is None:
            raise RuntimeError('Missing bundled baseline historical data')
        result = merger(local, prior)
        path.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
        print(f'Restored {name} from Git branch {BRANCH}', flush=True)

    # The expanded leagues are stored in season.json, not in their own feed.
    # Restore the full latest fixture snapshot before the PT/DK hourly refresh.
    previous_season=read_remote('season.json')
    if (isinstance(previous_season,dict) and previous_season.get('schema')==1
        and previous_season.get('season')=='2026-2027'
        and all(k in previous_season.get('leagues',{}) for k in ('pt','dk'))):
        path=root/'data'/'season.json'
        path.write_text(json.dumps(previous_season,ensure_ascii=False,separators=(',',':'))+'\n',
                        encoding='utf-8')
        print('Restored current-season PT/DK and expansion fixtures from persistent branch',flush=True)

    # For the new partially collected metadata feeds, the data branch is
    # authoritative. Do not accidentally reset the previous successful
    # season-round collection on the next hourly workflow.
    for filename in ('cross_competitions.json','prematch_lineups.json','advanced_signals.json','xg_shadow_ledger.json','nl_history.json','expansion_1x2_ledger.json', 'expansion_1x2_audit.json','league_comparison.json','expanded_history.json'):
        prior=read_remote(filename)
        if prior is None:continue
        if not isinstance(prior,dict) or prior.get('schema')!=1:
            raise RuntimeError('Corrupt persistent contextual feed: '+filename)
        target=root/'data'/filename
        target.write_text(json.dumps(prior,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
        print('Restored context state:',filename,flush=True)

def save(root=ROOT):
    fetch = git('fetch', '--no-tags', 'origin', f'+refs/heads/{BRANCH}:refs/remotes/origin/{BRANCH}', check=False)
    if fetch.returncode:
        raise RuntimeError('Persistent branch not reachable: ' + fetch.stderr[-500:])
    for filename in ('history.json', 'ledger.json', 'reliability.json', 'quality.json', 'stats_coverage.json', 'value_engine.json', 'feature_impact.json',
                     'cross_competitions.json', 'schedule_context.json', 'prematch_lineups.json',
                     'multi_competition_impact.json', 'ledger_health.json', 'european_coverage.json', 'advanced_signals.json', 'shots_research.json', 'xg_experiment.json', 'xg_shadow_ledger.json', 'nl_history.json', 'expansion_reliability.json', 'expansion_1x2_ledger.json', 'expansion_1x2_audit.json','league_comparison.json','validation_center.json','data_coverage.json','expanded_history.json'):
        filepath=root/'data'/filename
        if not filepath.is_file():
            raise RuntimeError('Missing required persistent data file: '+str(filepath))
        json.loads(filepath.read_text(encoding='utf-8'))
    with tempfile.TemporaryDirectory(prefix='football-store-') as temp:
        workspace=Path(temp)/'repo'
        add=git('worktree','add','--detach',str(workspace),f'origin/{BRANCH}',check=False)
        if add.returncode:
            raise RuntimeError('Cannot mount data branch: '+add.stderr[-500:])
        try:
            (workspace/'data').mkdir(exist_ok=True)
            for name in TRACKED:
                file=root/'data'/name
                if file.is_file():
                    shutil.copy2(file, workspace/'data'/name)
            git('config','user.name','github-actions[bot]',cwd=workspace)
            git('config','user.email','41898282+github-actions[bot]@users.noreply.github.com',cwd=workspace)
            git('add','--',*[f'data/{name}' for name in TRACKED if (root/'data'/name).is_file()],cwd=workspace)
            diff=git('diff','--cached','--quiet',cwd=workspace,check=False)
            if diff.returncode == 0:
                print('Persistent branch already up-to-date',flush=True)
                return {'saved':True,'changed':False}
            commit=git('commit','-m','data: verified football research snapshot',cwd=workspace,check=False)
            if commit.returncode:
                raise RuntimeError('Unable to commit data snapshot: '+commit.stderr[-500:])
            push=git('push','origin',f'HEAD:refs/heads/{BRANCH}',cwd=workspace,check=False)
            if push.returncode:
                raise RuntimeError('Cannot persist data on branch (check ruleset/token): '+push.stderr[-800:])
            sha=git('rev-parse','HEAD',cwd=workspace).stdout.strip()
            print(f'Persistent snapshot saved to {BRANCH}: {sha}',flush=True)
            return {'saved':True,'changed':True,'sha':sha}
        finally:
            git('worktree','remove','--force',str(workspace),check=False)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('mode',choices=['restore','save'])
    args=p.parse_args()
    if args.mode=='restore':restore()
    else:save()

if __name__=='__main__':
    main()
