#!/usr/bin/env python3
"""Afonso OS Football Intelligence — notícias RSS + ausências opcionais API-Football.

A mera manchete NUNCA é tratada como lesão confirmada. A ausência de entradas
NÃO significa que a equipa esteja completa. Dados sem fonte não são publicados.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'data' / 'intelligence.json'
OVERRIDES = ROOT / 'data' / 'verified_absences.json'
API_BASE = 'https://v3.football.api-sports.io'
SEASON = 2026
# Identificadores API-Football: podem ser substituídos por vars de ambiente.
API_LEAGUES = {'pt': 94, 'dk': 119}
LEAGUES = {'pt': 'Liga Portugal', 'dk': '3F Superliga'}

ALIASES = {
    'pt': {
        'Benfica': ['benfica', 'slb'], 'Porto': ['fc porto', 'f.c. porto', 'fcp'],
        'Sporting CP': ['sporting cp', 'sporting clube', 'sporting lisbon', 'sporting lisboa'],
        'Braga': ['sc braga', 'sporting braga'],
        'Vitória de Guimarães': ['vitoria sc', 'vitoria guimaraes', 'vitória guimarães'],
        'Famalicao': ['famalicao', 'famalicão'], 'Estoril Praia': ['estoril'],
        'Moreirense': ['moreirense'], 'Gil Vicente': ['gil vicente'],
        'Rio Ave': ['rio ave'], 'Arouca': ['arouca'], 'Alverca': ['alverca'],
        'Casa Pia': ['casa pia'], 'Marítimo': ['maritimo', 'marítimo'],
        'Santa Clara': ['santa clara'], 'Nacional de Madeira': ['nacional da madeira', 'cd nacional', 'nacional madeira'],
        'Académico de Viseu': ['academico de viseu', 'académico de viseu'],
        'Estrela Amadora': ['estrela da amadora', 'estrela amadora'],
    },
    'dk': {
        'FC Copenhagen': ['fc copenhagen', 'f.c. københavn', 'fc københavn', 'fck', 'kobenhavn', 'københavn'],
        'FC Midtjylland': ['midtjylland', 'fcm'], 'Brøndby': ['brøndby', 'brondby', 'brøndby if'],
        'AGF Aarhus': ['agf aarhus', 'agf århus', 'aarhus gf'],
        'Silkeborg IF': ['silkeborg'], 'Viborg': ['viborg'],
        'Sønderjyske': ['sonderjyske', 'sønderjyske'], 'FC Nordsjælland': ['nordsjælland', 'nordsjaelland'],
        'Odense BK': ['odense bk', 'ob odense'], 'Lyngby': ['lyngby'],
        'AC Horsens': ['horsens'], 'Randers FC': ['randers fc'],
    }
}
# Manchetes: categorização indicativa, não confirmação de disponibilidade nem causalidade.
KEYWORDS = [
    ('lesao', ('lesao','lesion','lesionado','lesionado','injury','injured','skade','skadet','muskel','operation','fratura')),
    ('castigo', ('castigo','suspenso','suspensão','suspension','suspended','karantaene','karantæne','red card','expulso')),
    ('onze', ('onze inicial','alinhamento','starting xi','lineup','opstilling','titular')),
    ('treinador', ('treinador','coach','manager','træner','afskediget','despedido')),
    ('mercado', ('transfer','transferência','transferencia','contratação','signing','solgt')),
    ('descanso', ('descanso','rotacao','rotação','rotation','rested','træthed','fatigue')),
]
RSS_QUERIES = {
    'pt': [
        '"liga portugal" (lesão OR lesões OR castigo OR suspenso OR treinador) when:7d',
        '("Benfica" OR "FC Porto" OR "Sporting CP" OR "SC Braga") (lesão OR castigo OR onze inicial) when:7d',
    ],
    'dk': [
        '"3F Superliga" (skade OR skadet OR karantæne OR træner) when:7d',
        '("FC København" OR "Midtjylland" OR "Brøndby" OR "AGF") (skade OR karantæne OR opstilling) when:7d',
    ],
}


def normalise(s):
    s = unicodedata.normalize('NFKD', str(s or '')).lower()
    return ''.join(c for c in s if not unicodedata.combining(c))


def identify_team(title, league):
    t = normalise(title)
    result = []
    for team, names in ALIASES[league].items():
        if any(re.search(r'(?<!\w)' + re.escape(normalise(alias)) + r'(?!\w)', t) for alias in names):
            result.append(team)
    return sorted(set(result))


def classify(title):
    t = normalise(title)
    for category, words in KEYWORDS:
        if any(re.search(r'(?<!\w)' + re.escape(normalise(w)) + r'(?!\w)', t) for w in words):
            return category
    return 'geral'


def feed_url(query, league):
    loc = {'pt': ('pt-PT', 'PT', 'PT:pt-150'), 'dk': ('da', 'DK', 'DK:da')}[league]
    return 'https://news.google.com/rss/search?' + urllib.parse.urlencode({'q':query,'hl':loc[0],'gl':loc[1],'ceid':loc[2]})


def news_from_xml(xml_bytes, league, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    root = ET.fromstring(xml_bytes)
    results=[]
    for i in root.findall('./channel/item'):
        title=(i.findtext('title') or '').strip()[:250]
        link=(i.findtext('link') or '').strip()
        published=(i.findtext('pubDate') or '').strip()
        source_tag=i.find('source')
        source=(source_tag.text or '').strip()[:80] if source_tag is not None else 'Google Notícias'
        if not title or not link.startswith('https://news.google.com/'):
            continue
        try:
            date=parsedate_to_datetime(published).astimezone(dt.timezone.utc)
        except (TypeError, ValueError, IndexError):
            continue
        if not (dt.timedelta(days=-1) <= now-date <= dt.timedelta(days=14)):
            continue
        ident=hashlib.sha256((title.casefold()+'|'+link).encode()).hexdigest()[:18]
        results.append({'id':ident,'league':league,'teams':identify_team(title,league),
                        'title':title,'url':link,'source':source,'published_at':date.isoformat(),
                        'category':classify(title),'verification':'headline_only',
                        'note':'Título recolhido por RSS; abrir artigo e confirmar antes de considerar uma baixa.'})
    return results


def get(url, headers=None, timeout=18):
    req=urllib.request.Request(url,headers={'User-Agent':'AfonsoOSFootballIntelligence/2.0 (RSS reader; aggregated headlines)',
                                             'Accept':'application/rss+xml,application/xml,application/json',**(headers or {})})
    with urllib.request.urlopen(req,timeout=timeout) as response:
        return response.read(3_000_000)


def get_news(fetch=get, now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    news=[]; errors=[]; sources_ok=0
    for lid, queries in RSS_QUERIES.items():
        for q in queries:
            try:
                raw=fetch(feed_url(q,lid))
                news.extend(news_from_xml(raw,lid,now))
                sources_ok+=1
            except (urllib.error.URLError,TimeoutError,ValueError,ET.ParseError,OSError) as e:
                errors.append(f'RSS {lid}: {type(e).__name__}')
    by_id={x['id']:x for x in news}
    return sorted(by_id.values(),key=lambda n:n['published_at'],reverse=True)[:160],errors,sources_ok


def canonical_team(api_name, league):
    n=normalise(api_name)
    if not n:
        return None
    for team, aliases in ALIASES[league].items():
        if n == normalise(team) or n in [normalise(a) for a in aliases]:
            return team
    return None


def parse_absences(payload, league, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    if not isinstance(payload,dict) or not isinstance(payload.get('response'),list):
        raise ValueError('Resposta da API-Football inválida')
    result=[]
    for item in payload['response']:
        fixture=item.get('fixture') or {}; team_obj=item.get('team') or {};player=item.get('player') or {}
        date=str(fixture.get('date') or '')[:10]
        try: dateobj=dt.date.fromisoformat(date)
        except (ValueError,TypeError):continue
        if not now.date() <= dateobj <= (now+dt.timedelta(days=15)).date():continue
        team=canonical_team(team_obj.get('name'),league)
        if not team:continue
        player_name=str(player.get('name') or '').strip()[:120]
        if not player_name:continue
        status=str(player.get('type') or 'Indisponibilidade reportada')[:100]
        reason=str(player.get('reason') or 'Não especificada')[:160]
        kind='castigo' if any(x in normalise(reason) for x in ('suspend','ban','suspens','castig','red card')) else 'lesao/outra'
        ident=hashlib.sha256((league+str(fixture.get('id'))+str(player.get('id'))+status).encode()).hexdigest()[:18]
        result.append({'id':ident,'league':league,'team':team,'player':player_name,
                       'fixture_date':date,'fixture_id':fixture.get('id'),
                       'status':status,'reason':reason,'category':kind,
                       'source':'API-Football','source_url':'https://www.api-football.com/',
                       'verified_as':'reported_by_provider','retrieved_at':now.isoformat()})
    return result


def get_api_absences(fetch=get, now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    key=os.getenv('API_FOOTBALL_KEY','').strip()
    if not key:
        return [],['API-Football não configurada: ausências não verificadas automaticamente.'],0
    result=[];warnings=[];success=0
    for lid, league_id in API_LEAGUES.items():
        league_id=os.getenv('API_FOOTBALL_LEAGUE_'+lid.upper(),str(league_id))
        params={'league':league_id,'season':SEASON}
        url=API_BASE+'/injuries?'+urllib.parse.urlencode(params)
        try:
            data=json.loads(fetch(url,headers={'x-apisports-key':key,'Accept':'application/json'}))
            if data.get('errors'):
                warnings.append(f'API-Football {lid}: indisponível ou sem cobertura para 2026/27.')
                continue
            success+=1
            result.extend(parse_absences(data,lid,now))
        except (urllib.error.URLError,TimeoutError,OSError,ValueError,KeyError,json.JSONDecodeError) as e:
            warnings.append(f'API-Football {lid}: {type(e).__name__}')
    return result,warnings,success


def validated_overrides(path, now):
    try:entries=json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:return []
    except (OSError,ValueError):return []
    valid=[]
    if not isinstance(entries,list):return []
    for item in entries:
        if not isinstance(item,dict):continue
        lid=item.get('league');team=item.get('team');player=item.get('player')
        if lid not in ALIASES or team not in ALIASES[lid] or not isinstance(player,str):continue
        url=item.get('source_url','')
        if not isinstance(url,str) or not url.startswith('https://'):continue
        date=item.get('fixture_date','')
        try:d=dt.date.fromisoformat(date)
        except (ValueError,TypeError):continue
        if not now.date()<=d<=(now+dt.timedelta(days=15)).date():continue
        valid.append({'id':hashlib.sha256((lid+team+player+date).encode()).hexdigest()[:18],
                      'league':lid,'team':team,'player':player[:120],'fixture_date':date,
                      'status':str(item.get('status','Por confirmar'))[:80],
                      'reason':str(item.get('reason','Não especificada'))[:160],
                      'category':str(item.get('category','outra'))[:30],
                      'source':str(item.get('source','Fonte indicada'))[:80],
                      'source_url':url,'verified_as':'editorial_with_source',
                      'retrieved_at':now.isoformat()})
    return valid


def collect(out=OUTPUT, news_fetch=get, api_fetch=get, now=None, override_path=OVERRIDES):
    now = now or dt.datetime.now(dt.timezone.utc)
    old={}
    if out.exists():
        try: old=json.loads(out.read_text(encoding='utf-8'))
        except (ValueError,OSError):old={}
    news, errors, feeds_ok=get_news(news_fetch,now)
    if feeds_ok==0 and old.get('news'):
        news=[x for x in old['news'] if x.get('published_at','')[:10] >= (now-dt.timedelta(days=14)).date().isoformat()]
        errors.append('Todos os RSS falharam: mantidos títulos antigos (verificar datas).')
    absences, warnings, api_ok=get_api_absences(api_fetch,now)
    manual=validated_overrides(override_path,now)
    absence_ids={x['id']:x for x in (absences+manual)}
    # Sem ligação autenticada, não preservar ausências antigas: podem já não se aplicar.
    availability='provider_available' if api_ok else 'not_connected_or_unavailable'
    result={'schema':2,'season':'2026-2027','updated_at':now.replace(microsecond=0).isoformat(),
            'news_updated_at':now.isoformat() if feeds_ok else old.get('news_updated_at'),
            'news_status':'feed_ok' if feeds_ok else 'feed_unavailable',
            'news':news,'absences':list(absence_ids.values()),
            'absences_status':availability,'manual_entries':len(manual),
            'sources':{'news':'Google News RSS — manchetes, não factos confirmados','absences':'API-Football opcional; registos manuais com URL'},
            'warnings':errors+warnings}
    out.parent.mkdir(parents=True,exist_ok=True)
    tmp=out.with_suffix('.tmp')
    tmp.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    tmp.replace(out)
    print('Notícias:',len(news),'RSS disponíveis:',feeds_ok,'Ausências fonte:',len(absences),'Manuais:',len(manual),'Avisos:',len(errors+warnings))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description='Atualizar notícias + indisponibilidades verificáveis')
    p.add_argument('--output',type=Path,default=OUTPUT)
    x=p.parse_args()
    collect(out=x.output)
