"""Dashboard autónomo para abrir diretamente sem servidor de Internet."""
from pathlib import Path
import json
import re
ROOT=Path(__file__).resolve().parents[1]
index=(ROOT/'app'/'index.html').read_text(encoding='utf8')
style=(ROOT/'app'/'style.css').read_text(encoding='utf8')
script=(ROOT/'app'/'app.js').read_text(encoding='utf8')
data=json.loads((ROOT/'data'/'season.json').read_text(encoding='utf8'))
intelligence=json.loads((ROOT/'data'/'intelligence.json').read_text(encoding='utf8'))
# Evitar terminação involuntária do elemento script por dados externos.
json_data=json.dumps(data,ensure_ascii=False).replace('</','<\\/')
intel_data=json.dumps(intelligence,ensure_ascii=False).replace('</','<\\/')
index=index.replace('<link rel="stylesheet" href="style.css" />','<style>'+style+'</style>')
index=index.replace('<script src="app.js" defer></script>', '<script>window.FOOTBALL_LAB_DATA = '+json_data+';window.FOOTBALL_INTELLIGENCE_DATA = '+intel_data+';</script><script>'+script+'</script>')
out=ROOT/'Afonso_OS_Football_Intelligence_PREVIEW.html'
out.write_text(index,encoding='utf8')
print('Preview autónomo:',out,'bytes:',out.stat().st_size)
