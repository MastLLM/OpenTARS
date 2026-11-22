"""5.3.5: a troca de motor. O Colibri inteiro de ponta a ponta, com um coli falso (sem rede de fora e sem modelo de verdade):
a Release baixada e conferida pelo SHA-256, o catálogo próprio na biblioteca, o /api/pull pelo coli, o /api/tags só com os
modelos do Colibri e a conversa traduzida de Ollama para OpenAI."""
import hashlib
import http.server
import json
import os
import socket
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

casa = Path(tempfile.mkdtemp(prefix="opentars-motores-"))
with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    porta = s.getsockname()[1]
os.environ.update(HOME=str(casa), XDG_DATA_HOME=str(casa / "dados"), XDG_CONFIG_HOME=str(casa / "config"), TARS_MOTOR="colibri",
                  TARS_COLIBRI_MODELOS=str(casa / "colibri-models"), TARS_MOTOR_PORTA=str(porta))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tars_mais_modelos as mm  # noqa: E402
import tars_motor_local as m  # noqa: E402
import tars_motores as tm  # noqa: E402

COLI = r'''#!/usr/bin/env python3
import json, os, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
a = sys.argv[1:]
def arg(n): return a[a.index(n) + 1]
if a[:1] == ["setup"] and "--list" in a:
    print(json.dumps([{"id": "tiny", "name": "Tiny 1B", "download_gb": 0.5, "kind": "text"}, {"id": "img", "kind": "image"}]))
elif a[:1] == ["setup"]:
    os.makedirs(os.path.join(arg("--dir"), arg("--model")), exist_ok=True)
    open(os.path.join(arg("--dir"), arg("--model"), "config.json"), "w").write("{}")
    print("downloading", arg("--model"))
elif a[:1] == ["serve"]:
    nome = arg("--model-id")
    class H(BaseHTTPRequestHandler):
        def log_message(self, *x): pass
        def _env(self, corpo, tipo="application/json"):
            self.send_response(200); self.send_header("Content-Type", tipo); self.send_header("Content-Length", str(len(corpo)))
            self.end_headers(); self.wfile.write(corpo)
        def do_GET(self): self._env(json.dumps({"status": "ok"}).encode())
        def do_POST(self):
            p = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            texto = "oi de " + nome + " ultima=" + p["messages"][-1]["content"]
            if p.get("stream"):
                pedacos = [{"choices": [{"delta": {"content": texto}, "finish_reason": None}]}, {"choices": [{"delta": {}, "finish_reason": "stop"}]}]
                self._env(b"".join(b"data: " + json.dumps(x).encode() + b"\n\n" for x in pedacos) + b"data: [DONE]\n\n", "text/event-stream")
            else:
                self._env(json.dumps({"choices": [{"message": {"content": texto}, "finish_reason": "stop"}]}).encode())
    HTTPServer(("127.0.0.1", int(arg("--port"))), H).serve_forever()
'''

# a Release falsa, servida por um servidor local, com o SHA-256 de verdade dela
release = casa / "release"
release.mkdir()
pacote = release / "colibri-teste.zip"
with zipfile.ZipFile(pacote, "w") as z:
    z.writestr("colibri-v9/coli", COLI)
servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), lambda *a: http.server.SimpleHTTPRequestHandler(*a, directory=str(release)))
threading.Thread(target=servidor.serve_forever, daemon=True).start()
chave = ("colibri", *m.sistema_e_maquina())
tm._URLS["colibri"] = f"http://127.0.0.1:{servidor.server_address[1]}/"
tm.PACOTES[chave] = ("colibri-teste.zip", "0" * 64, 0.01)
try:
    tm.instalar("colibri")
    raise AssertionError("SHA-256 errado tinha de recusar")
except (OSError, ValueError):
    pass
assert tm.binario("colibri") is None or not str(tm.binario("colibri")).startswith(str(casa)), "nada extraído com SHA errado"
tm.PACOTES[chave] = ("colibri-teste.zip", hashlib.sha256(pacote.read_bytes()).hexdigest(), 0.01)
exe = tm.instalar("colibri")
assert exe == tm.pasta("colibri") / "colibri-v9" / "coli", exe
print("OK: a Release do motor vem para a pasta do app só com o SHA-256 certo")

assert m.escolhido() == "colibri" and m.PORTA == porta
assert [g for g, _ in mm.grupos()] == ["colibri"] and mm.grupos()[0][1] == (("tiny", "Tiny 1B", 0.5, ("tools",)),), mm.grupos()
assert m._nome("tiny:latest") == "tiny" and m._conhecido("tiny") and not m._conhecido("ProjectOpenTARS/Gargantua-2.5:lite")
print("OK: a biblioteca do Colibri é o catálogo dele (só os de texto); os Gargantua não existem nele")

import atexit  # noqa: E402
import subprocess  # noqa: E402
proxy = subprocess.Popen([sys.executable, m.__file__, "--servir"], cwd=os.path.dirname(m.__file__),   # o servir() arma sinais: só no processo dele
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
atexit.register(proxy.terminate)
for _ in range(100):
    if m.respondendo(0.2):
        break
    time.sleep(0.1)


def pedir(caminho, corpo=None):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    with urllib.request.urlopen(urllib.request.Request(m.URL + caminho, dados, method="POST" if dados else "GET"), timeout=30) as r:
        return r.read().decode()


assert json.loads(pedir("/api/tags"))["models"] == []
assert json.loads(pedir("/api/pull", {"model": "tiny", "stream": False})) == {"status": "success"}
assert [x["name"] for x in json.loads(pedir("/api/tags"))["models"]] == ["tiny"]
resposta = json.loads(pedir("/api/chat", {"model": "tiny", "stream": False, "messages": [{"role": "user", "content": "ola"}]}))
assert resposta["message"]["content"] == "oi de tiny ultima=ola", resposta
linhas = [json.loads(x) for x in pedir("/api/chat", {"model": "tiny", "messages": [{"role": "user", "content": "x"}]}).splitlines() if x]
assert "".join(x["message"]["content"] for x in linhas) == "oi de tiny ultima=x" and linhas[-1]["done"], linhas
print("OK: o proxy baixa pelo coli, lista só os modelos do Colibri e conversa com o coli serve")

pedir("/api/delete", {"model": "tiny"})
assert json.loads(pedir("/api/tags"))["models"] == [] and not (casa / "colibri-models" / "tiny").exists()
print("OK: apagar tira o modelo da pasta do Colibri")
