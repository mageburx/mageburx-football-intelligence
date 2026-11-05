"""Iniciar dashboard local com dados guardados, sem dependências externas."""
from __future__ import annotations
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import argparse
import functools
import shutil
import webbrowser
import threading

ROOT = Path(__file__).resolve().parents[1]

def build():
    public=ROOT/'public'
    (public/'data').mkdir(parents=True,exist_ok=True)
    for name in ('index.html','style.css','app.js'):
        shutil.copy2(ROOT/'app'/name,public/name)
    for name in ('season.json','intelligence.json'):
        shutil.copy2(ROOT/'data'/name,public/'data'/name)
    return public

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8742)
    parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args()
    root=build()
    handler=functools.partial(SimpleHTTPRequestHandler,directory=str(root))
    server=ThreadingHTTPServer(('127.0.0.1',args.port),handler)
    url=f'http://127.0.0.1:{args.port}/'
    print(f'Dashboard disponível em {url} [Ctrl+C para terminar]',flush=True)
    if not args.no_browser: threading.Timer(.7,lambda:webbrowser.open(url)).start()
    try: server.serve_forever()
    except KeyboardInterrupt: print('A terminar.')
    finally: server.server_close()
