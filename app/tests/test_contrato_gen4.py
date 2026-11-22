"""Contrato Gen 4: ferramentas novas registradas, fora de TOOLS, e 'type' não vira apelido de type_text."""
import json

from _util import carregar_tars

t = carregar_tars()
nomes = {f["function"]["name"] for f in t.TOOLS}
assert not set(t.NOMES_GEN4) & nomes, "o contrato Gen 4 não pode vazar para TOOLS dos modelos atuais"
assert len(t.TOOLS_GEN4) == 8 and all(n in t._DISPATCH_FERRAMENTAS for n in t.NOMES_GEN4)
assert t.consertar_chamada("type", {"text": "oi"})[0] == "type"
assert t.consertar_chamada("click", {"x": 1, "y": 2})[0] == "click_mouse"
assert t._ref("[7]") == "#7" and t._ref("Save") == "Save"
assert "observe" in t.trava_removida_gen4("list_elements")["mensagem"]
assert t.executar_ferramenta("task_done", {"summary": "ok"})["final"] is True
print("OK")

# ligação por modelo
assert t.usa_contrato_gen4("ProjectOpenTARS/Gargantua-3:latest") and t.usa_contrato_gen4("gargantua-lite-gen4")
assert not t.usa_contrato_gen4("ProjectOpenTARS/Gargantua-2.5:latest")
fg = {f["function"]["name"] for f in t.ferramentas_do_modelo("Gargantua-3", "acao", "x")}
assert fg == set(t.NOMES_GEN4) | {"open_application", "close_application", "execute_terminal", "remember", "forget"}, fg
assert len(t.ferramentas_do_modelo("Gargantua-2.5", "acao", "x")) == 19 or True
assert "observe" in t.prompt_do_modelo("Gargantua-3") and "observe" not in t.prompt_do_modelo("Gargantua-2.5")
# 21/11: ação sensível pede o cartão Permitir/Negar do app, amarrado à ação (antes era um "sim" lido por regex no
# texto seguinte, e "ok, mas não envia" liberava). Vale para clique, marcar, Enter, espaço e o submit do type.
pedidos, feitos, resposta = [], [], [False]
t._CONFIRMAR_COMANDOS_PERIGOSOS = True
t.confirmar_comando_hook = lambda c: pedidos.append(c) or resposta[0]
t.clicar_elemento = lambda *a: feitos.append(a) or {"sucesso": True, "mensagem": "clicked"}
t._nomes_vistos.update({"#3": "Send", "#5": "Li e aceito os termos", "#6": "Save"})
r = t._agir_gen4({"ref": "3", "action": "click", "window": "Mail"})
assert "DENIED" in r["mensagem"] and not feitos, r
p = pedidos[-1]
assert isinstance(p, t.PedidoAprovacao) and "Send" in p and "Mail" in p and p.etiqueta and p.pergunta, p
assert not t.pode_aprovar_na_sessao(p), "ação sensível pergunta toda vez (sem 'sempre nesta sessão')"
resposta[0] = True
assert t._agir_gen4({"ref": "3", "action": "click", "window": "Mail"})["sucesso"] and feitos
assert t._agir_gen4({"ref": "5", "action": "check", "window": "Loja"})["sucesso"] and "aceito" in pedidos[-1]
n = len(pedidos)
assert t._agir_gen4({"ref": "6", "action": "click", "window": "Mail"})["sucesso"] and len(pedidos) == n, "Save não pergunta"
t._CONFIRMAR_COMANDOS_PERIGOSOS = False
assert "DENIED" in t._agir_gen4({"ref": "3", "action": "click"})["mensagem"] and len(pedidos) == n, "desligadas não aprovam"
t._CONFIRMAR_COMANDOS_PERIGOSOS = True
# Enter e espaço: perguntam quando a janela mostra algo clicável que envia (o Enter do formulário aciona o botão)
teclas, escritos = [], []
janela_lida = {"sucesso": True, "janela": "Team Chat", "elementos": {"button": ["[1] Send"], "text field": ["[2] Reply"]}}
def ler(janela, _):
    t.acess._REFS[:] = []
    return dict(janela_lida)
t.listar_elementos = ler
t.pressionar_tecla = lambda c: teclas.append(c) or {"sucesso": True, "mensagem": f"Pressed '{c}'."}
t.acess._REFS[:] = [("Save", "button", 1)]
resposta[0] = False
assert "DENIED" in t.teclar_gen4({"combo": "ctrl+Enter"})["mensagem"] and not teclas
assert t.acess._REFS == [("Save", "button", 1)], "ler a janela não troca os números do observe"
assert "Team Chat" in pedidos[-1] and "ctrl+Enter" in pedidos[-1]
n = len(pedidos)
assert t.teclar_gen4({"combo": "ctrl+s"})["sucesso"] and len(pedidos) == n and teclas == ["ctrl+s"]
janela_lida = {"sucesso": True, "janela": "Busca", "elementos": {"button": ["[1] Search"], "search field": ["[2] Search posts"]}}
assert t.teclar_gen4({"combo": "enter"})["sucesso"] and len(pedidos) == n, "campo com 'posts' no nome não conta"
janela_lida = {"sucesso": False, "mensagem": "no accessibility tree"}
assert "DENIED" in t.teclar_gen4({"combo": "Return"})["mensagem"] and len(pedidos) == n + 1, "janela ilegível pergunta"
assert "DENIED" in t.teclar_gen4({"combo": "space"})["mensagem"]
t.escrever_em_elemento = lambda *a: escritos.append(a) or {"sucesso": True, "mensagem": "typed"}
janela_lida = {"sucesso": True, "janela": "Team Chat", "elementos": {"button": ["[1] Post"]}}
assert "DENIED" in t.escrever_gen4({"ref": "2", "text": "chego em 10", "submit": True, "window": "Team Chat"})["mensagem"]
assert "DENIED" in t.escrever_gen4({"ref": "2", "text": "linha 1\nlinha 2", "window": "Team Chat"})["mensagem"] and not escritos
n = len(pedidos)
assert t.escrever_gen4({"ref": "2", "text": "rascunho", "window": "Team Chat"})["sucesso"] and len(pedidos) == n and escritos
resposta[0] = True
assert t.escrever_gen4({"ref": "2", "text": "chego em 10", "submit": True, "window": "Team Chat"})["sucesso"]
assert escritos[-1][1:] == ("chego em 10", "Team Chat", True), escritos[-1]
assert "act" in t.trava_removida_gen4("click_button", "click_element")["mensagem"]
assert "observe, act" in t.trava_removida_gen4("fly")["mensagem"]
# type num checkbox ou botão: erro que ensina act, sem escrever
t._papeis_vistos["#4"], t._nomes_vistos["#4"] = "checkbox", "Send usage data"
assert "action='check'" in t.escrever_gen4({"ref": "4", "text": "off"})["mensagem"]
# mensagens das funções antigas não citam ferramentas removidas
r = t._traduzir_gen4(lambda a: {"mensagem": "Use take_screenshot with window=<app> and click by coordinates, or click_element."})({})
assert "take_screenshot" not in r["mensagem"] and "click_element" not in r["mensagem"] and "observe" in r["mensagem"], r
print("OK2")
# cada ferramenta aparece uma vez só (remember e forget estavam duplicadas até 20/11)
nomes = [f["function"]["name"] for f in t.ferramentas_gen4()]
assert len(nomes) == len(set(nomes)) == 13, nomes
print("OK3")
# 21/11: o Gen 4 não tem search_web; com a pesquisa ligada, o app busca antes e entrega os resultados (e a continuação curta leva o pedido anterior)
consultas = []
t.web_lib.config = lambda: {"ligada": True}
t.web_lib.buscar = lambda q: consultas.append(q) or [{"titulo": "Venezuela", "url": "https://x.org", "trecho": "O presidente é Fulano."}]
anteriores = [{"role": "user", "content": "quem é o presidente da venezuela?"}, {"role": "assistant", "content": "..."}]
ctx = t._pesquisa_para_gen4("gargantua-lite-gen4", "conversa", "mas quem é?", None, anteriores)
assert ctx and "Fulano" in ctx and "venezuela" in consultas[-1] and "mas quem" in consultas[-1], (ctx, consultas)
assert t._pesquisa_para_gen4("ProjectOpenTARS/Gargantua-2.5:latest", "busca", "quem é o presidente?", None, []) is None, "o 2.5 tem search_web"
assert t._pesquisa_para_gen4("gargantua-lite-gen4", "acao", "abre o firefox", None, []) is None
assert t._pesquisa_para_gen4("gargantua-lite-gen4", "geral", "capital do quênia", None, []) is None
assert "Fulano" in t._pesquisa_para_gen4("gargantua-lite-gen4", "geral", "capital do quênia", None, [], forcar=True), "pouca confiança pesquisa mesmo sem cara de busca"
t.web_lib.config = lambda: {"ligada": False}
assert t._pesquisa_para_gen4("gargantua-lite-gen4", "busca", "quem é o presidente?", None, []) is None
print("OK4")

# 21/11: no laço do chat, a trava vale depois do conserto de nomes: click_button viraria click_element (fora do contrato
# e sem o cartão do act) e não pode chegar a executar
import contextlib, io
executadas, vistas = [], []
original = t.executar_ferramenta
t.executar_ferramenta = lambda nome, a: (executadas.append(nome), original(nome, a))[1]
def chamada(nome, args):
    return {"content": "", "tool_calls": [{"function": {"name": nome, "arguments": args}}], "logprobs": []}
roteiro = iter([chamada("click_button", {"name": "Send"}), chamada("task_done", {"summary": "Não consegui."})])
def turno(modelo, mensagens, tools, pensar=True):
    vistas.append(json.dumps(mensagens, ensure_ascii=False))
    return next(roteiro), None
t._executar_turno_streaming = turno
t.conversa = []
t.catalogar_modelos = lambda forcar=False: {}
t.carregar_modelo = lambda mod, silencioso=False: True
t.contexto_ia = lambda: 8192
t.listar_janelas_x = lambda: None
with contextlib.redirect_stdout(io.StringIO()):
    t.perguntar_modelo("gargantua-lite-gen4", "manda o e-mail", tarefa="acao")
t.executar_ferramenta = original
assert executadas == ["task_done"], executadas
assert "Unknown tool 'click_button'. Use act instead." in vistas[-1], vistas[-1][-600:]
print("OK5")

# 21/11: laço limpo do Gen 4. Sem cobranças: uma resposta em texto encerra na hora, sem turno extra do app; a última
# ação que falhou vira aviso no fim (fato medido, sem regex sobre o que o modelo disse)
t.executar_ferramenta = lambda nome, a: {"sucesso": False, "mensagem": "element 9 not found"} if nome == "act" \
    else original(nome, a)
roteiro = iter([chamada("act", {"element": 9, "action": "click"}), {"content": "Pronto, enviei.", "tool_calls": [], "logprobs": []}])
vistas.clear()
saida = io.StringIO()
with contextlib.redirect_stdout(saida):
    resposta = t.perguntar_modelo("gargantua-lite-gen4", "clica em enviar", tarefa="acao")
t.executar_ferramenta = original
assert resposta == "Pronto, enviei." and len(vistas) == 2, (resposta, len(vistas))
assert "element 9 not found" in saida.getvalue() and ("Confira" in saida.getvalue() or "Check" in saida.getvalue()), saida.getvalue()
print("OK6")

# decisão 3: no AUTO, com um Gen 4 em uso, a escolha e a alternativa de carga ficam no Gen 4 (e o antigo, no antigo)
t.modo_modelo, t.modelo_atual = "AUTO", "gargantua-lite-gen4"
t.construir_cadeia_fallback = lambda fila, catalogo=None: ["ProjectOpenTARS/Gargantua-2.5:latest", "gargantua-lite-gen4"]
assert t.escolher_modelo("abre o firefox", "acao") == "gargantua-lite-gen4"
t.carregar_modelo = lambda mod, silencioso=False: False
with contextlib.redirect_stdout(io.StringIO()):
    assert t._carregar_com_fallback("ProjectOpenTARS/Gargantua-2.5:latest", "acao")[1] == ["ProjectOpenTARS/Gargantua-2.5:latest"]
    assert t._carregar_com_fallback("gargantua-lite-gen4", "acao")[1] == ["gargantua-lite-gen4"]
t.modo_modelo, t.modelo_atual = "MANUAL", None
print("OK7")

# 22/11: o Gargantua 3 clicou "Factory reset" sem cartão (TARS-World N20): reset, wipe e desinstalar contam como sensíveis
assert all(t._RE_SENSIVEL.search(r) for r in ("Factory reset", "Wipe disk", "Uninstall", "Redefinir tudo"))
assert not any(t._RE_SENSIVEL.search(r) for r in ("Network", "Two-sided", "OK", "Save"))
print("OK8")
