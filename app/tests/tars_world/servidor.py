"""Servidor local das páginas da bateria TARS-World (só 127.0.0.1).

Uso: python3 servidor.py PORTA LOG.txt
Serve a pasta web/ e registra cada GET /ev?e=EVENTO&v=VALOR como a linha "web<TAB>EVENTO<TAB>VALOR" no LOG.
"""
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PASTA = Path(__file__).with_name("web")
porta, log = int(sys.argv[1]), open(sys.argv[2], "a", buffering=1, encoding="utf-8")


class Pagina(SimpleHTTPRequestHandler):
    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/ev":
            q = parse_qs(u.query)
            log.write("\t".join(["web", q.get("e", [""])[0], q.get("v", [""])[0].replace("\t", " ").replace("\n", " ")]) + "\n")
            self.send_response(204)
            self.end_headers()
            return
        super().do_GET()

    def log_message(self, *a):
        pass


ThreadingHTTPServer(("127.0.0.1", porta), partial(Pagina, directory=str(PASTA))).serve_forever()
