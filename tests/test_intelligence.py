import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from update_intelligence import identify_team,classify,news_from_xml,parse_absences,collect,canonical_team

NOW=dt.datetime(2026,11,5,12,0,tzinfo=dt.timezone.utc)
RSS=b'''<?xml version="1.0"?><rss><channel><item>
 <title>Benfica confirma lesao apos treino - Jornal Exemplo</title>
 <link>https://news.google.com/rss/articles/ABC</link>
 <pubDate>Thu, 05 Nov 2026 11:00:00 GMT</pubDate><source>Jornal Exemplo</source>
 </item><item><title>Noticia antiga Sporting</title><link>https://news.google.com/rss/articles/OLDER</link><pubDate>Wed, 07 Oct 2026 11:00:00 GMT</pubDate></item>
 <item><title>HTML injection</title><link>javascript:alert(1)</link><pubDate>Thu, 05 Nov 2026 11:00:00 GMT</pubDate></item>
 </channel></rss>'''

def test_headlines_only_and_safe_links():
    rows=news_from_xml(RSS,'pt',NOW)
    assert len(rows)==1
    assert rows[0]['teams']==['Benfica']
    assert rows[0]['category']=='lesao'
    assert rows[0]['verification']=='headline_only'


def test_aliases_and_categories():
    assert identify_team('Skade hos Brøndby IF og FC København','dk')==['Brøndby','FC Copenhagen']
    assert classify('Karantæne til spilleren')=='castigo'
    assert canonical_team('FC Porto','pt')=='Porto'
    assert canonical_team('Unknown team','pt') is None


def test_provider_filters_future_matching():
    payload={'response':[{'fixture':{'id':42,'date':'2026-11-09T19:30:00Z'},'team':{'name':'FC Porto'},'player':{'id':11,'name':'Jogador A','type':'Missing Fixture','reason':'Suspended'}},
                         {'fixture':{'id':13,'date':'2026-08-09T19:30:00Z'},'team':{'name':'FC Porto'},'player':{'id':12,'name':'Jogador B','type':'Missing Fixture','reason':'Injury'}}]}
    rows=parse_absences(payload,'pt',NOW)
    assert len(rows)==1
    assert rows[0]['category']=='castigo'
    assert rows[0]['team']=='Porto'
    assert rows[0]['verified_as']=='reported_by_provider'


def test_collection_fails_gracefully_without_network(tmp_path,monkeypatch):
    monkeypatch.delenv('API_FOOTBALL_KEY',raising=False)
    def fake_news(_):raise OSError('offline')
    result=collect(tmp_path/'intelligence.json',news_fetch=fake_news,now=NOW,override_path=tmp_path/'no.json')
    assert result['news_status']=='feed_unavailable'
    assert result['absences_status']=='not_connected_or_unavailable'
    assert result['news']==[] and result['absences']==[]
    assert json.loads((tmp_path/'intelligence.json').read_text())['warnings']
