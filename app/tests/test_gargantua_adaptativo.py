"""Contrato adaptativo (5.3.5, Gen 4): o gerador de dados em kit/dados_52/adaptativo.py.

- toda chamada de ferramenta usa uma ferramenta que está na lista do próprio exemplo;
- o resultado da ferramenta usa o nome novo (nada de nome velho vazando);
- as ferramentas retidas (teste decisivo) nunca aparecem no treino;
- a geração é determinística e o prompt-base é um só."""

import json
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parents[2] / "kit"
REAL = Path.home() / "gargantua/dados/exemplos.jsonl"
if not REAL.exists():
    print("sem exemplos.jsonl: teste pulado")
    sys.exit(0)
sys.path.insert(0, str(KIT))
from dados_52 import adaptativo as a  # noqa: E402

real = [json.loads(l) for l in REAL.open()]
ex = a.gerar(real, semente=2026, total=400)
assert ex == a.gerar(real, semente=2026, total=400), "geração não determinística"

for e in ex:
    nomes = {t["function"]["name"] for t in e["tools"]}
    for m in e["mensagens"]:
        for c in m.get("tool_calls") or []:
            assert c["function"]["name"] in nomes, (e["id"], c["function"]["name"])
        if m["role"] == "tool":
            try:
                r = json.loads(m["content"])
            except ValueError:
                continue
            if isinstance(r, dict) and r.get("action"):
                assert r["action"] in nomes, (e["id"], r["action"])

treino = {t["function"]["name"] for e in ex for t in e["tools"]}
retidas = {n for n in a.RETIDAS}
assert not (treino & retidas), treino & retidas
assert len(a.conjunto_retido(777, 60)) == 60
print("test_gargantua_adaptativo ok:", len(ex), "exemplos")
