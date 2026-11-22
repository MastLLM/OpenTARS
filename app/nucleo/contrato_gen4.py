# Contrato Gen 4 do computer use (PLANO_COMPUTER_USE.md, 3.5): poucas ferramentas, por referência [N].
# NÃO entra em TOOLS: os modelos atuais continuam com o contrato antigo. Quem treina ou roda um modelo
# Gen 4 usa TOOLS_GEN4 + ferramentas_gen4(). Os handlers abaixo só traduzem para as funções que já existem.
import re as _re_g4

SISTEMA_GEN4 = (
    "You are Gargantua, a local AI assistant that controls this computer, inside the openTARS app.\n"
    "- Your name is Gargantua. openTARS is the app you run in, not your name.\n"
    "- To act on a window: observe it, act on an element by its [N] number, observe again to check the result.\n"
    "- Before anything that sends, pays, buys, deletes, publishes or accepts terms, ask_user and wait for a yes.\n"
    "- Never say something worked unless the window showed it. If you cannot do it, say so with task_done.\n"
    "- When it is just a question or small talk, answer directly, without tools.\n"
    "- Answer short, in the user's language.\n"
)
_FERRAMENTAS_FIXAS_GEN4 = ("open_application", "close_application", "execute_terminal", "remember", "forget")
_RE_GEN4 = _re_g4.compile(r"gen[-_ ]?4|gargantua-3|pro-gen[-_ ]?2")
# shortcut: lista fixa em inglês e português; ampliar quando aparecer app em outro idioma
_RE_SENSIVEL = _re_g4.compile(
    r"\b(send|submit|pay|buy|purchase|order|checkout|delete|remove|erase|publish|post|confirm|accept|agree|transfer|reset|factory|wipe|uninstall|enviar|"
    r"envie|pagar|comprar|apagar|excluir|deletar|remover|publicar|postar|aceitar|aceito|concordo|confirmar|finalizar|"
    r"transferir|redefinir|resetar|formatar|desinstalar)\b", _re_g4.I)
_nomes_vistos = {}  # "#N" -> texto do elemento, do último observe
_papeis_vistos = {}  # "#N" -> papel do elemento ("checkbox", "text field"...), do último observe
_ultima_janela = [None]  # shortcut: uma janela por vez, quando houver duas tarefas em paralelo trocar por estado da tarefa

# ferramenta antiga -> a que a substitui (a trava devolve isto ao modelo que ainda a chama)
REMOVIDAS_GEN4 = {
    "list_elements": "observe", "take_screenshot": "observe", "list_windows": "observe",
    "click_element": "act", "click_mouse": "act", "drag_mouse": "act", "focus_window": "act", "move_window": "act",
    "type_in_element": "type", "type_text": "type", "press_key": "key", "scroll_mouse": "scroll",
    "open_website": "browser_open", "search_web": "browser_open",
}
ACOES_GEN4 = ("click", "double_click", "right_click", "check", "select", "focus")
_PAPEL_DA_ACAO = {"check": "checkbox"}

TOOLS_GEN4 = [
    _ferramenta(
        "observe",
        "Shows the window: its elements numbered [N] and the texts it shows. Call it before acting and after each "
        "action that may change the window. screenshot=true also returns a picture (only if the numbers are not enough).",
        {"window": {"type": "string", "description": "App or window name. Without it, the focused window."},
         "screenshot": {"type": "boolean"}}),
    _ferramenta(
        "act",
        "Acts on the element [N] from the last observe. action: click, double_click, right_click, check, select "
        "(a drop-down option; pass value), focus. Sensitive actions (send, pay, delete, accept terms) need the "
        "user's approval first.",
        {"ref": {"type": "string", "description": "The [N] number, or the element text."},
         "action": {"type": "string", "enum": list(ACOES_GEN4)},
         "value": {"type": "string", "description": "For select: the option."},
         "window": {"type": "string"}},
        ["ref", "action"]),
    _ferramenta(
        "type",
        "Writes text into the field [N] (or the focused field without ref). submit=true presses Enter afterwards.",
        {"text": {"type": "string"}, "ref": {"type": "string"}, "submit": {"type": "boolean"}, "window": {"type": "string"}},
        ["text"]),
    _ferramenta("key", "Presses a key or shortcut, e.g. 'enter', 'ctrl+s'.", {"combo": {"type": "string"}}, ["combo"]),
    _ferramenta(
        "scroll", "Scrolls the element [N] (or the window) up or down.",
        {"ref": {"type": "string"}, "direction": {"type": "string", "enum": ["up", "down"]}}, ["direction"]),
    _ferramenta("browser_open", "Opens a web address in the browser.", {"url": {"type": "string"}}, ["url"]),
    _ferramenta("ask_user", "Asks the user a question and waits (confirmation before a sensitive action, or missing data).",
                {"question": {"type": "string"}}, ["question"]),
    _ferramenta("task_done", "Ends the task. Say what was done, or why it could not be done.",
                {"summary": {"type": "string"}}, ["summary"]),
]
NOMES_GEN4 = [f["function"]["name"] for f in TOOLS_GEN4]


def usa_contrato_gen4(modelo):
    """Gen 4 (Lite Gen 4, Gargantua 3, Pro Gen 2) ou TARS_CONTRATO_GEN4=1 (para testar um modelo qualquer)."""
    return os.environ.get("TARS_CONTRATO_GEN4") == "1" or bool(_RE_GEN4.search(str(modelo or "").lower()))


def ferramentas_gen4():
    lista, vistos = list(TOOLS_GEN4), set(NOMES_GEN4)
    for f in TOOLS + TOOLS_MEMORIA:  # remember e forget estão nas duas listas: cada uma entra uma vez só
        nome = f["function"]["name"]
        if nome in _FERRAMENTAS_FIXAS_GEN4 and nome not in vistos:
            vistos.add(nome)
            lista.append(_compactar(f))
    return lista


def _ref(r):
    r = str(r or "").strip().lstrip("#[").rstrip("]")
    return f"#{r}" if r.isdigit() else str(r or "")


def observar_gen4(a):
    janela = a.get("window") or _ultima_janela[0]
    r = listar_elementos(janela, None)
    if r.get("janela"):
        _ultima_janela[0] = r["janela"]
    _nomes_vistos.clear()
    _papeis_vistos.clear()
    for papel, lista in (r.get("elementos") or {}).items():
        for item in lista:
            m = _re_g4.match(r"\[(\d+)\]\s*(.*)", str(item))
            if m:
                _nomes_vistos["#" + m.group(1)] = m.group(2)
                _papeis_vistos["#" + m.group(1)] = papel
    if r.get("mensagem"):
        r["mensagem"] = _re_g4.sub(r"Press one with click_element.*?by name\.", "Act on one with act(ref=N), N being its [N] number (valid until the window changes).", r["mensagem"])
    if _booleano(a.get("screenshot")):
        r["print"] = tirar_print(janela or None, None)
    return r


def _titulos_janelas():
    return [j.get("titulo") for j in (listar_janelas_x() or [])]


def _aprovado_gen4(descricao):
    """Ação sensível: o app pergunta à pessoa no cartão Permitir/Negar (o mesmo da aprovação de comando), amarrado a
    esta ação, em vez de ler o "sim" no texto dela. Com as confirmações desligadas não aprova sozinho (como o e-mail)."""
    return _CONFIRMAR_COMANDOS_PERIGOSOS and _confirmar_comando_perigoso(
        PedidoAprovacao(descricao, t("sensivel.etiqueta"), t("sensivel.pergunta")))


def _negado_gen4():
    return {"sucesso": False, "mensagem": "DENIED: the user did not allow this action (it may send, pay, delete or "
            "accept something). Do not try it another way; tell the user with task_done."}


def _janela_que_pode_enviar(janela):
    """Título da janela quando um Enter ou espaço nela pode enviar, pagar, apagar ou aceitar algo: ela mostra um
    elemento clicável com esse nome (o Enter de um formulário aciona o botão dele), ou não dá para ler a janela.
    None quando não pode."""
    refs = list(acess._REFS)  # ler a janela não troca os números do último observe
    try:
        r = listar_elementos(janela, None)
    finally:
        acess._REFS[:] = refs
    titulo = r.get("janela") or janela or "?"
    if not r.get("sucesso"):
        return titulo  # app sem árvore de acessibilidade: não dá para saber o que a tecla faz
    campos = set(acess.PAPEIS_CAMPO.values())
    sensivel = any(_RE_SENSIVEL.search(str(item)) for papel, lista in (r.get("elementos") or {}).items()
                   if papel not in campos for item in lista)
    return titulo if sensivel else None


def teclar_gen4(a):
    combo = str(a.get("combo") or "")
    teclas = [k.strip().lower() for k in combo.split("+")]
    if teclas[-1] in ("enter", "return", "kp_enter") or combo.lower() in ("space", " "):
        titulo = _janela_que_pode_enviar(None)  # a tecla vai para a janela com o foco
        if titulo and not _aprovado_gen4(t("sensivel.tecla", tecla=combo, janela=titulo)):
            return _negado_gen4()
    return pressionar_tecla(combo)


def agir_gen4(a):
    acao = str(a.get("action") or "click").lower()
    if acao in ("type", "write", "fill"):  # o modelo confunde act com type (TARS-World C4): escreve em vez de errar
        return escrever_gen4({**a, "text": a.get("text") or a.get("value") or ""})
    refs = list(acess._REFS)
    antes = _titulos_janelas()
    r = _agir_gen4(a)
    if not (isinstance(r, dict) and r.get("sucesso")):
        return r
    atual = a.get("window") or _ultima_janela[0]
    novas = [t for t in _titulos_janelas() if t and t not in antes and t != atual]  # o menu aberto vira janela do X com o mesmo título
    abriu = str(r.get("elemento") or "").startswith(("menu ", "tab ", "page tab "))
    if not (novas or abriu or r.get("novos") or r.get("sumiram")):
        acess._REFS[:] = refs  # ação que não mudou a tela: os números do observe continuam valendo
        return r
    # a tela mudou: devolve já os elementos novos, numerados, para o modelo não agir com números velhos
    # nem observar a janela errada (TARS-World D1, G2, G3, 18/11)
    o = observar_gen4({"window": novas[-1] if novas else atual})
    if o.get("sucesso"):
        r["janela"], r["elementos"] = o["janela"], o["elementos"]
        r["mensagem"] = (str(r.get("mensagem") or "") + (f" A new window opened: '{o['janela']}'." if novas else "")
                         + f" The elements of '{o['janela']}' now, with NEW numbers: see 'elementos'.")
    return r


def _agir_gen4(a):
    acao = str(a.get("action") or "click").lower()
    if acao not in ACOES_GEN4:
        return {"sucesso": False, "mensagem": f"ERROR: unknown action '{acao}'. Use one of: {', '.join(ACOES_GEN4)}."}
    janela = a.get("window") or _ultima_janela[0]
    alvo = _ref(a.get("ref"))
    rotulo = _nomes_vistos.get(alvo, alvo)
    if acao in ("click", "double_click", "check") and _RE_SENSIVEL.search(rotulo):
        if not _aprovado_gen4(t("sensivel.marcar" if acao == "check" else "sensivel.clicar", alvo=rotulo, janela=janela or "?")):
            return _negado_gen4()
    if acao == "select":
        # lista suspensa: abre o combo e depois escolhe a opção (clicar_elemento já devolve as opções da lista aberta)
        if a.get("value"):
            refs = list(acess._REFS)
            r = clicar_elemento(_ref(a.get("ref")), janela, "combo box")
            if not r.get("sucesso"):
                return r
            r = clicar_elemento(str(a["value"]), janela, "menu item")
            acess._REFS[:] = refs  # os números do observe continuam valendo depois de escolher
            return r
        acao = "click"
    if acao == "focus":
        return focar_janela(janela or str(a.get("ref") or ""))
    if acao in ("double_click", "right_click"):
        nome = _ref(a.get("ref"))
        return clicar_mouse("right" if acao == "right_click" else "left", None, None, nome, janela, duplo=acao == "double_click")
    return clicar_elemento(_ref(a.get("ref")), janela, _PAPEL_DA_ACAO.get(acao))


def escrever_gen4(a):
    ref = _ref(a.get("ref"))
    if _papeis_vistos.get(ref) in ("checkbox", "check box", "radio button", "toggle button", "button", "menu", "menu item", "tab", "page tab"):
        acao = "check" if "check" in _papeis_vistos[ref] or "toggle" in _papeis_vistos[ref] else "click"
        return {"sucesso": False, "mensagem": f"[{ref.lstrip('#')}] '{_nomes_vistos.get(ref)}' is a {_papeis_vistos[ref]}, not a text "
                f"field: use act(ref={ref.lstrip('#')}, action='{acao}')."}
    texto, janela, enviar = str(a.get("text") or ""), a.get("window") or _ultima_janela[0], _booleano(a.get("submit"))
    if enviar or "\n" in texto:  # submit é um Enter; a quebra de linha também, quando o texto sai pelo teclado
        titulo = _janela_que_pode_enviar(janela)
        if titulo and not _aprovado_gen4(t("sensivel.texto", texto=texto, janela=titulo)):
            return _negado_gen4()
    return escrever_em_elemento(_nomes_vistos.get(ref, ref), texto, janela, enviar)


def rolar_gen4(a):
    return scroll_mouse(3 if str(a.get("direction")) == "up" else -3)


def abrir_gen4(a):
    return abrir_site(a.get("url", ""))


def perguntar_gen4(a):
    # o laço do chat termina o turno com esta pergunta (a pessoa responde no turno seguinte)
    return {"sucesso": True, "final": True, "mensagem": str(a.get("question") or "")}


def concluir_gen4(a):
    return {"sucesso": True, "final": True, "mensagem": str(a.get("summary") or "")}


# as mensagens das funções antigas citam ferramentas que o modelo Gen 4 não tem
_TROCAS_GEN4 = [
    (r"use take_screenshot with window=<app> and click by coordinates", "use observe with screenshot=true"),
    (r"Use take_screenshot with window=<app> and click by coordinates", "Use observe with screenshot=true"),
    (r"click the field and use type_text", "use type without ref on the focused field"),
    (r"click_element\(name=<option>\)", "act(ref=N, action='select')"),
    (r"click_element\(name=\"#N\"\)", "act(ref=N)"),
] + [(rf"\b{antiga}\b", nova) for antiga, nova in REMOVIDAS_GEN4.items()]


def _traduzir_gen4(f):
    def g(a):
        r = f(a)
        if isinstance(r, dict) and isinstance(r.get("mensagem"), str):
            for de, para in _TROCAS_GEN4:
                r["mensagem"] = _re_g4.sub(de, para, r["mensagem"])
        return r
    return g


def trava_removida_gen4(nome, consertado=None):
    """Mensagem para o modelo Gen 4 que chamou uma ferramenta fora do contrato: uma que saiu, ou um nome que o conserto
    traduziria para uma das antigas (click_button vira click_element e passaria por cima da confirmação do act)."""
    troca = REMOVIDAS_GEN4.get(nome) or REMOVIDAS_GEN4.get(consertado)
    dica = f"Use {troca} instead." if troca else f"Use one of: {', '.join(NOMES_GEN4)}."
    return {"sucesso": False, "mensagem": f"Unknown tool '{nome}'. {dica}"}


_DISPATCH_FERRAMENTAS.update({
    "observe": _traduzir_gen4(observar_gen4), "act": _traduzir_gen4(agir_gen4), "type": _traduzir_gen4(escrever_gen4),
    "key": _traduzir_gen4(teclar_gen4), "scroll": _traduzir_gen4(rolar_gen4),
    "browser_open": abrir_gen4, "ask_user": perguntar_gen4, "task_done": concluir_gen4,
})
