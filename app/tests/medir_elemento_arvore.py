"""Medição (não entra no run_all): achar e clicar elemento pela árvore de acessibilidade, com o modelo real.
Abre uma janela GTK com botões conhecidos na tela virtual, pede "clique no botão X" e confere qual botão recebeu o clique.
Também conta quantas vezes o modelo usou list_elements e click_element com #N.
Uso (só em tela virtual): xvfb-run -a dbus-run-session -- env TARS_TESTE_TELA_VIRTUAL=1 HOME=$(mktemp -d) TARS_SEM_ATALHOS=1 /usr/share/opentars/venv/bin/python3 -u tests/medir_elemento_arvore.py [MODELO] [RODADAS=1]"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ["TARS_TESTE_OLLAMA_REAL"] = "1"
os.environ.setdefault("TARS_SEM_ATALHOS", "1")
from _util import carregar_tars  # noqa: E402

# Cliques e teclas reais: só em tela virtual, nunca no desktop da pessoa.
if os.environ.get("TARS_TESTE_TELA_VIRTUAL") != "1":
    sys.exit("Recusado: rode com `xvfb-run -a dbus-run-session -- env TARS_TESTE_TELA_VIRTUAL=1 python3 ...`")

BOTOES = ["Salvar", "Cancelar", "Enviar", "Abrir", "Fechar", "Imprimir", "Exportar", "Importar", "Atualizar", "Ajuda"]
PEDIDOS = [("Clique no botão {n}.", 1), ("Click the {n} button.", 1)]

APP = r'''
import sys, gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
log = open(sys.argv[1], "a", buffering=1)
w = Gtk.Window(title="Teste de elementos"); w.set_default_size(420, 260)
g = Gtk.Grid(column_spacing=8, row_spacing=8, margin=12); w.add(g)
for i, n in enumerate(sys.argv[2:]):
    b = Gtk.Button(label=n); b.connect("clicked", lambda _b, n=n: log.write(n + "\n")); g.attach(b, i % 4, i // 4, 1, 1)
w.connect("destroy", Gtk.main_quit); w.show_all(); Gtk.main()
'''

modelo = sys.argv[1] if len(sys.argv) > 1 else "ProjectOpenTARS/Gargantua-2.5:latest"
modelo = modelo if ":" in modelo else modelo + ":latest"
rodadas = int(sys.argv[2]) if len(sys.argv) > 2 else 1
tars = carregar_tars()
tars.catalogar_modelos()
tmp = Path(tempfile.mkdtemp())
(tmp / "app.py").write_text(APP)
log = tmp / "cliques.txt"
log.touch()
proc = subprocess.Popen([sys.executable, str(tmp / "app.py"), str(log), *BOTOES])
time.sleep(3)

def _fechar_outras():
    """Fecha toda janela que não seja a de teste (o modelo pode ter aberto outras) e foca a de teste."""
    ids = subprocess.run(["xdotool", "search", "--onlyvisible", "--name", "."], capture_output=True, text=True).stdout.split()
    for i in ids:
        nome = subprocess.run(["xdotool", "getwindowname", i], capture_output=True, text=True).stdout.strip()
        if nome and nome != "Teste de elementos":
            subprocess.run(["xdotool", "windowclose", i])
    teste = subprocess.run(["xdotool", "search", "--name", "Teste de elementos"], capture_output=True, text=True).stdout.split()
    if teste:
        subprocess.run(["xdotool", "windowactivate", teste[0]])
    time.sleep(0.5)


chamadas = []
original = tars.executar_ferramenta


def gravar(nome, argumentos):
    r = original(nome, argumentos)
    chamadas.append((nome, dict(argumentos or {})))
    return r


tars.executar_ferramenta = gravar
tars.modo_modelo, tars.modelo_manual = "MANUAL", modelo
acertos = total = usou_lista = usou_ref = 0
try:
    for _ in range(rodadas):
        for alvo in BOTOES:
            for modelo_pedido, _x in PEDIDOS:
                _fechar_outras()
                tars.conversa[:] = [{"role": "system", "content": ""}]
                chamadas.clear()
                antes = len(log.read_text().splitlines())
                try:
                    tars.processar_mensagem(modelo_pedido.format(n=alvo))
                except Exception as e:  # noqa: BLE001
                    print("erro:", e)
                cliques = log.read_text().splitlines()[antes:]
                ok = bool(cliques) and cliques[0] == alvo and len(cliques) == 1
                acertos += ok
                total += 1
                lista = any(n == "list_elements" for n, _a in chamadas)
                ref = any(n == "click_element" and str(a.get("name", "")).strip().startswith(("#", "[")) for n, a in chamadas)
                usou_lista += lista
                usou_ref += ref
                print(f"  {'OK ' if ok else 'ERRO'} {alvo:10} cliques={cliques} chamadas={[n for n, _a in chamadas]}", flush=True)
finally:
    proc.terminate()
print(f"Achar elemento pela árvore: {acertos}/{total} ({modelo}); list_elements em {usou_lista}, click_element com #N em {usou_ref}")
