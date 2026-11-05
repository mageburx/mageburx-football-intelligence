"""Snapshot PARCIAL de arranque: jogos reais obtidos da API TheSportsDB a 05/11/2026.
Usar apenas como pré-visualização; a rotina update_data.py importa a época toda.
"""
import datetime as dt
import json
from pathlib import Path
from update_data import SEASON, LEAGUES, parse_event

# id|round|date|home|away|score; resultados verificados contra API a 05/11/2026.
RAW = {
'pt': '''
2513940|1|2026-08-07|Estoril Praia|Famalicao|1-1
2513936|1|2026-08-08|Marítimo|Casa Pia|1-0
2513938|1|2026-08-08|Vitória de Guimarães|Arouca|0-1
2513942|1|2026-08-08|Estrela Amadora|Sporting CP|2-2
2513934|1|2026-08-09|Benfica|Académico de Viseu|2-2
2513935|1|2026-08-09|Porto|Alverca|2-0
2513937|1|2026-08-09|Moreirense|Braga|2-2
2513941|1|2026-08-09|Gil Vicente|Rio Ave|1-0
2513939|1|2026-08-10|Santa Clara|Nacional de Madeira|2-2
2513946|2|2026-08-14|Sporting CP|Vitória de Guimarães|3-2
2513945|2|2026-08-15|Rio Ave|Porto|0-2
2513947|2|2026-08-15|Académico de Viseu|Santa Clara|0-1
2513951|2|2026-08-15|Alverca|Estrela Amadora|2-2
2513944|2|2026-08-16|Nacional de Madeira|Estoril Praia|2-0
2513948|2|2026-08-16|Arouca|Moreirense|4-0
2514023|10|2026-10-30|Casa Pia|Sporting CP|0-2
2514016|10|2026-10-31|Porto|Estoril Praia|4-0
2514018|10|2026-10-31|Moreirense|Estrela Amadora|2-1
2514017|10|2026-11-01|Marítimo|Santa Clara|0-2
2514019|10|2026-11-01|Braga|Famalicao|3-0
2514020|10|2026-11-01|Académico de Viseu|Rio Ave|2-1
2514021|10|2026-11-01|Arouca|Nacional de Madeira|1-0
2514015|10|2026-11-02|Benfica|Alverca|1-0
2514022|10|2026-11-02|Gil Vicente|Vitória de Guimarães|0-0
2514030|11|2026-11-06|Famalicao|Arouca|
2514025|11|2026-11-07|Nacional de Madeira|Académico de Viseu|
2514028|11|2026-11-07|Sporting CP|Moreirense|
2514031|11|2026-11-07|Alverca|Casa Pia|
2514024|11|2026-11-08|Vitória de Guimarães|Porto|
2514026|11|2026-11-08|Rio Ave|Braga|
2514027|11|2026-11-08|Santa Clara|Gil Vicente|
2514029|11|2026-11-08|Estoril Praia|Marítimo|
2514032|11|2026-11-08|Estrela Amadora|Benfica|
''',
'dk': '''
2481792|1|2026-07-24|Viborg|Odense BK|1-0
2481793|1|2026-07-25|AGF Aarhus|Brøndby|1-1
2481794|1|2026-07-26|Sønderjyske|FC Midtjylland|2-3
2481796|1|2026-07-26|AC Horsens|FC Nordsjælland|1-1
2481797|1|2026-07-26|FC Copenhagen|Lyngby|3-2
2481795|1|2026-07-27|Randers FC|Silkeborg IF|1-1
2481798|2|2026-08-01|Lyngby|AGF Aarhus|2-2
2481799|2|2026-08-02|FC Midtjylland|AC Horsens|2-1
2481800|2|2026-08-02|FC Nordsjælland|Randers FC|1-0
2481801|2|2026-08-02|Brøndby|Viborg|1-0
2481802|2|2026-08-02|Silkeborg IF|FC Copenhagen|1-3
2481803|2|2026-08-03|Odense BK|Sønderjyske|1-0
2481804|3|2026-08-07|Sønderjyske|Viborg|0-0
2481805|3|2026-08-09|Randers FC|Lyngby|2-0
2481806|3|2026-08-09|AC Horsens|Brøndby|0-2
2481868|13|2026-10-30|Lyngby|Randers FC|2-1
2481865|13|2026-11-01|FC Nordsjælland|FC Midtjylland|2-3
2481866|13|2026-11-01|Odense BK|Silkeborg IF|4-1
2481867|13|2026-11-01|Brøndby|AGF Aarhus|2-0
2481869|13|2026-11-01|Viborg|AC Horsens|1-0
2481864|13|2026-11-02|Sønderjyske|FC Copenhagen|0-2
2481875|14|2026-11-06|Silkeborg IF|Lyngby|
2481873|14|2026-11-07|Odense BK|Viborg|
2481870|14|2026-11-08|FC Midtjylland|Sønderjyske|
2481871|14|2026-11-08|FC Copenhagen|Brøndby|
2481872|14|2026-11-08|Randers FC|FC Nordsjælland|
2481874|14|2026-11-08|AGF Aarhus|AC Horsens|
'''
}

def generate(out):
    result={'schema':1,'season':SEASON,
            'source':{'name':'TheSportsDB','url':'https://www.thesportsdb.com/','api':'v1 gratuita'},
            'updated_at':None,
            'preview_retrieved_at':'2026-11-05',
            'leagues':{}}
    for lid, raw in RAW.items():
        events=[]
        for line in raw.strip().splitlines():
            ident,rnd,date,home,away,score=line.split('|')
            hs,aws=score.split('-') if score else (None,None)
            e=parse_event({'idEvent':ident,'strSeason':SEASON,'idLeague':LEAGUES[lid]['id'],'dateEvent':date,'strHomeTeam':home,'strAwayTeam':away,'intHomeScore':hs,'intAwayScore':aws,'intRound':rnd},lid)
            assert e is not None
            events.append(e)
        result['leagues'][lid]={'id':LEAGUES[lid]['id'], 'name':LEAGUES[lid]['name'], 'country':LEAGUES[lid]['country'], 'events':events,
                                'rounds_ok':0,'rounds_failed':[],'partial':True,'preview_only':True}
    out.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf8')
    return result

if __name__=='__main__':
    x=generate(Path(__file__).resolve().parents[1]/'data'/'season.json')
    print('Snapshot inicial PARCIAL:', {k: len(v['events']) for k,v in x['leagues'].items()})
