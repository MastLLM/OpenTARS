"""Gerador de trajetórias do contrato Gen 4 (PLANO_COMPUTER_USE.md, seção 5): o "oráculo".

Monta apps GTK aleatórios (nomes e ordem que NÃO são os da bateria TARS-World, para não treinar no teste), escreve o
pedido em inglês ou português, e um roteiro por regras dirige o executor REAL do app (observe, act, type, key,
ask_user, task_done) dentro do xvfb. Cada passo gravado é uma chamada de verdade com o resultado de verdade. Só fica a
trajetória que o log do app confirma (todos os eventos esperados, nenhum proibido) e sem nenhuma chamada que falhou.

  xvfb-run -a -s "-screen 0 1440x900x24" dbus-run-session -- env TARS_TESTE_TELA_VIRTUAL=1 HOME=$(mktemp -d) TARS_SEM_ATALHOS=1 \
    /usr/share/opentars/venv/bin/python3 -u tests/tars_world/gerar_gen4.py SAIDA.jsonl [QUANTAS] [SEMENTE]

Cenários (v2, 18/11, das falhas medidas do Lite Gen 4): formulário (com e sem o botão de abrir no pedido; sensível =
preencher TUDO e só então ask_user; seguro = nunca perguntar), marcar e desmarcar, menu (e menu que abre diálogo),
abas, abrir e cancelar, ler a tela e responder, e impossível (nome parecido na tela, ou item que não está no menu).
O act devolve os elementos novos quando a tela muda: o roteiro age com eles, sem observe extra.
v3 (19/11, porque o Lite Gen 4 v2 decorou os moldes do v2): pedidos em passos ou por objetivo (sem o nome do botão),
moldes com e sem o nome do app, rótulos da tela que variam e a pessoa falando do campo com as palavras dela, formulário
na janela principal, aberto por menu ou por botão, assistente de dois passos, leitura em frase ou em outra aba, ação
sensível de um clique só, "feito" só com prova no resultado (estado), campo inexistente, e respostas variadas.

Formato da saída: o do g4.jsonl (id, categoria, idioma, mensagens). O montador põe o sistema e as ferramentas.
"""
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

if os.environ.get("TARS_TESTE_TELA_VIRTUAL") != "1" or not os.environ.get("HOME", "").startswith(tempfile.gettempdir()):
    sys.exit("Recusado: rode em xvfb com TARS_TESTE_TELA_VIRTUAL=1 e HOME temporário (ver o topo do arquivo).")

AQUI = Path(__file__).resolve().parent
sys.path[:0] = [str(AQUI.parent), str(AQUI)]
import psutil  # noqa: E402,F401
import pyautogui  # noqa: E402,F401

os.environ["TARS_TESTE_OLLAMA_REAL"] = "1"
os.environ["TARS_CONTRATO_GEN4"] = "1"
from _util import carregar_tars  # noqa: E402
from runner import presente  # noqa: E402

# Vocabulário próprio: nenhum destes nomes de app, janela, aba ou menu aparece em tarefas.py.
APPS_V = ["Inventory", "Tickets", "Contacts", "Orders", "Library", "Budget", "Recipes", "Garage", "Garden", "Clinic",
          "Fleet", "Studio", "Pantry", "Courses", "Warehouse", "Payroll", "Kennel", "Bakery"]
CAMPOS = {"Name": ["Rafael Dias", "Lena Fox", "Hugo Lima", "Carla Nunes"], "Email": ["hugo@example.com", "lena@mail.org", "rita@corp.net"],
          "Phone": ["555-0142", "555-0199", "555-0110"], "Title": ["Quarterly plan", "Spare parts", "Birthday list", "Roof repair"],
          "Notes": ["call back friday", "bring the receipt", "fragile, handle with care"], "City": ["Recife", "Lisbon", "Denver", "Curitiba"],
          "Recipient": ["joana@example.com", "mark@shop.io"], "Message": ["See you at 8", "Report attached", "Thanks for the help"],
          "Amount": ["120", "45.50", "980"], "Code": ["AX-77", "B12", "ZK-4"], "Address": ["Rua Azul 10", "5th Avenue 300"]}
COMBOS = {"Priority": ["Low", "Normal", "High"], "Category": ["Home", "Work", "Other"], "Weekday": ["Monday", "Wednesday", "Friday"],
          "Status": ["Open", "Closed", "Pending"], "Country": ["Brazil", "Portugal", "Canada"], "Hour": ["08:00", "12:30", "17:45"],
          "Size": ["Small", "Medium", "Large"]}
RADIOS = [["Standard", "Express", "Overnight"], ["Basic", "Premium"], ["Cash", "Card", "Voucher"], ["Pickup", "Delivery"]]
CHECKS = ["Urgent", "Notify me", "Archive after", "Share with team", "Auto backup", "Show hints", "Email reports", "Compact view"]
BOTOES_ABRE = ["Add item", "New entry", "Create record", "New request", "Write note", "New booking", "Compose"]
SEGUROS = ["Save", "Add", "Create", "Apply", "Done", "Book"]
SENSIVEIS = ["Send", "Submit", "Delete", "Pay now", "Publish", "Place order", "Transfer"]
MENUS = {"Edit": ["Undo", "Find", "Select all"], "Tools": ["Statistics", "Spell check", "Calculator"],
         "Export": ["As spreadsheet", "As image", "Print preview"], "Window": ["Zoom in", "Zoom out", "Full screen"],
         "Help": ["Shortcuts", "About"]}
DIALOGO_MENU = {"Rename...": ("Rename", [{"t": "entry", "n": "New name"}], "Rename"),
                "Duplicate...": ("Duplicate", [{"t": "entry", "n": "Copy name"}, {"t": "combo", "n": "Folder", "op": ["Main", "Archive", "Shared"]}], "Duplicate"),
                "Export file...": ("Export file", [{"t": "entry", "n": "Output name"}, {"t": "combo", "n": "Type", "op": ["CSV", "JSON", "TXT"]}], "Export")}
ABAS = ["Basics", "Security", "Sync", "Advanced", "Display", "Alerts"]
BOTOES_ABA = ["Reset layout", "Check updates", "Clear cache", "Run test", "Reindex"]
LEITURAS = [("Balance", ["$1,240.00", "$87.15", "R$ 3.402,10"]), ("Next visit", ["Friday 09:00", "March 3, 14:30"]),
            ("Stock left", ["14 units", "2 boxes"]), ("Last backup", ["yesterday 23:10", "2 hours ago"]),
            ("Open tickets", ["7", "31"]), ("Driver on duty", ["Paulo Reis", "Ana Beatriz"]),
            ("Pending orders", ["3", "12"]), ("Room temperature", ["21.5 °C", "19 °C"]), ("Due date", ["June 30", "next Tuesday"])]
FANTASMAS = [("Export to PDF", "Export"), ("Backup now", "Backup log"), ("Sync cloud", "Sync settings"), ("Print", "Preview"),
             ("Record", "Recent"), ("Share link", "Share with team"), ("Bluetooth", "Bright mode")]
PEDIDOS = {  # v3: mais moldes, alguns sem o nome do app (o app é a janela ativa; o roteiro observa sem "window")
    "en": ["In {app}, {acao}.", "Please {acao} in the {app} app.", "{Acao} in {app}.", "Use {app} to {acao}.", "Can you {acao} in {app}?",
           "Could you {acao}?", "{Acao}.", "I need you to {acao} in {app}.", "{app}: {acao}.", "Hey, in {app} {acao}, thanks.",
           "Go to {app} and {acao}.", "Over in {app}, {acao}.", "Quick one: {acao} in {app}.", "{Acao}, please."],
    "pt_BR": ["No {app}, {acao}.", "Por favor, {acao} no app {app}.", "{Acao} no {app}.", "No app {app}: {acao}.", "{Acao}, no {app}, por favor.",
              "{Acao}.", "{Acao}, por favor.", "Vai no {app} e {acao}.", "{app}: {acao}.", "Lá no {app}, {acao}.",
              "Me ajuda no {app}: {acao}.", "Rapidinho: {acao} no {app}."],
}
# v3: o rótulo na tela varia e a pessoa fala do campo com as palavras dela (conceito: rótulos na tela, nomes em en, em pt)
ROTULOS = {"Name": (["Name", "Full name", "Customer name", "Contact"], ["name", "full name"], ["nome", "nome completo"]),
           "Email": (["Email", "E-mail", "Email address", "Mail"], ["email", "email address", "e-mail"], ["e-mail", "endereço de e-mail"]),
           "Phone": (["Phone", "Tel.", "Mobile", "Phone number"], ["phone", "phone number", "mobile number"], ["telefone", "celular", "número de telefone"]),
           "Title": (["Title", "Subject", "Heading"], ["title", "subject"], ["título", "assunto"]),
           "Notes": (["Notes", "Comments", "Remarks"], ["note", "comment"], ["observação", "comentário", "nota"]),
           "City": (["City", "Town", "Location"], ["city", "town"], ["cidade"]),
           "Recipient": (["Recipient", "To", "Send to"], ["recipient", "destination address"], ["destinatário"]),
           "Message": (["Message", "Body", "Text"], ["message", "text"], ["mensagem", "texto"]),
           "Amount": (["Amount", "Total", "Sum"], ["amount", "total"], ["valor", "total", "quantia"]),
           "Code": (["Code", "Reference", "Ref. code"], ["code", "reference"], ["código", "referência"]),
           "Address": (["Address", "Street", "Street address"], ["address", "street"], ["endereço", "rua"])}
OBJETIVO = {  # botão final: o que a pessoa diz no lugar do nome do botão
    "Save": ("save it", "salve"), "Add": ("add it", "adicione"), "Create": ("create it", "crie o registro"), "Apply": ("apply it", "aplique"),
    "Done": ("finish", "conclua"), "Book": ("book it", "faça a reserva"), "Send": ("send it", "envie"), "Submit": ("submit it", "envie o formulário"),
    "Delete": ("delete it", "apague"), "Pay now": ("pay it", "pague"), "Publish": ("publish it", "publique"),
    "Place order": ("place the order", "faça o pedido"), "Transfer": ("make the transfer", "faça a transferência")}
TOPOS_FORM = ["Record", "Actions", "Data", "Entry"]
SENS_BOTAO = [("Delete all drafts", "delete all the drafts", "apague todos os rascunhos"), ("Send weekly report", "send the weekly report", "envie o relatório semanal"),
              ("Empty trash", "empty the trash", "esvazie a lixeira"), ("Publish changes", "publish the changes", "publique as mudanças"),
              ("Cancel subscription", "cancel the subscription", "cancele a assinatura"), ("Remove account", "remove the account", "remova a conta"),
              ("Pay invoice", "pay the invoice", "pague a fatura"), ("Wipe history", "wipe the history", "apague o histórico")]
ESTADO_BOTAO = [("Sync now", "sync", "sincronize", "Synced just now"), ("Recalculate", "recalculate the totals", "recalcule os totais", "Totals updated"),
                ("Refresh data", "refresh the data", "atualize os dados", "Data refreshed"), ("Check connection", "check the connection", "teste a conexão", "Connection OK"),
                ("Rebuild index", "rebuild the index", "refaça o índice", "Index rebuilt")]
PT_LEIT = {"Balance": "o saldo", "Next visit": "a próxima visita", "Stock left": "o estoque restante", "Last backup": "o último backup",
           "Open tickets": "os chamados abertos", "Driver on duty": "o motorista de plantão", "Pending orders": "os pedidos pendentes",
           "Room temperature": "a temperatura da sala", "Due date": "o vencimento"}
SIM = {"en": ["yes", "yes, go ahead", "confirmed", "ok, do it"], "pt_BR": ["sim", "sim, pode", "confirmo", "pode mandar"]}
NAO = {"en": ["no, don't", "cancel that", "wait, no"], "pt_BR": ["não, deixa", "cancela", "não, espera"]}
VERBO = {  # texto das ações, por idioma
    "en": {"abrir": "open '{b}'", "campo": "set {c} to '{v}'", "combo": "set {c} to {v}", "check": "tick '{c}'",
           "uncheck": "turn off '{c}'", "final": "press {b}", "e": ", ", "ultimo": " and "},
    "pt_BR": {"abrir": "abra '{b}'", "campo": "ponha '{v}' em {c}", "combo": "escolha {v} em {c}", "check": "marque '{c}'",
              "uncheck": "desmarque '{c}'", "final": "clique em {b}", "e": ", ", "ultimo": " e "},
}


def frase(rng, idioma, app, acao):
    return rng.choice(PEDIDOS[idioma]).format(app=app, acao=acao, Acao=acao[:1].upper() + acao[1:])


def juntar(idioma, partes):
    v = VERBO[idioma]
    return partes[0] if len(partes) == 1 else v["e"].join(partes[:-1]) + v["ultimo"] + partes[-1]


def L(idioma, en, pt):
    return en if idioma == "en" else pt


def um(rng, idioma, ens, pts):
    """Uma frase sorteada da lista do idioma (respostas e perguntas variadas, não um molde só)."""
    return rng.choice(ens if idioma == "en" else pts)


class Gravador:
    def __init__(self, tars):
        self.t, self.msgs, self.sem_app = tars, [], False

    def olhar(self, app):
        """Primeiro observe: sem "window" quando o pedido não diz o nome do app (vale a janela ativa)."""
        return self.chamar("observe", {} if self.sem_app else {"window": app})

    def usuario(self, texto):
        self.msgs.append({"role": "user", "content": texto})

    def chamar(self, nome, args):
        self.msgs.append({"role": "assistant", "content": "", "tool_calls": [
            {"type": "function", "function": {"name": nome, "arguments": args}}]})
        r = self.t.executar_ferramenta(nome, dict(args))
        r = self.t._para_ia(dict(r)) if hasattr(self.t, "_para_ia") else r
        self.msgs.append({"role": "tool", "content": json.dumps(r, ensure_ascii=False), "name": nome})
        return r

    def falar(self, texto):
        self.msgs.append({"role": "assistant", "content": texto})


def achar(res, nome):
    """Número [N] do elemento cujo nome é `nome` no resultado de observe (ou de act que mudou a tela)."""
    for itens in (res.get("elementos") or res.get("elements") or {}).values():
        for i in itens:
            m = re.match(r"\[(\d+)\]\s*(.*)", i)
            if m and m.group(2).strip().casefold() == nome.casefold():
                return m.group(1)
    raise LookupError(nome)


def fim(g, texto):
    g.chamar("task_done", {"summary": texto})
    g.falar(texto)


def perguntar(g, texto):
    g.chamar("ask_user", {"question": texto})
    g.falar(texto)


# ---------------------------------------------------------------- cenários
# Cada um devolve (spec do app, pedido, espera, proibe, roteiro(g)).

def nome_campo(rng, idioma, conceito, rotulo):
    """Como a pessoa chama o campo: o rótulo da tela (40%) ou uma palavra dela."""
    if rng.random() < 0.4:
        return rotulo
    return rng.choice(ROTULOS[conceito][1 if idioma == "en" else 2])


def c_form(rng, idioma, app):
    abre = rng.choice(BOTOES_ABRE)
    layout = rng.choices(["botao", "menu", "principal"], [0.5, 0.2, 0.3])[0]
    dlg = app if layout == "principal" else rng.choice([abre.title(), abre.title(), f"{app} - {abre}", "Details", f"{abre} form"])
    conceitos = rng.sample(sorted(CAMPOS), rng.randint(1, 4))
    rot = {c: rng.choice(ROTULOS[c][0]) for c in conceitos}  # rótulo na tela
    campos = {rot[c]: rng.choice(CAMPOS[c]) for c in conceitos}
    falados = {rot[c]: nome_campo(rng, idioma, c, rot[c]) for c in conceitos}
    combos = {c: rng.choice(COMBOS[c][1:]) for c in rng.sample(sorted(COMBOS), rng.randint(0, 2))}
    check = rng.choice(CHECKS) if rng.random() < 0.4 else None
    grupo = rng.choice(RADIOS) if rng.random() < 0.3 else None
    radio = rng.choice(grupo[1:]) if grupo else None  # o primeiro já vem marcado
    sensivel = rng.random() < 0.45
    final = rng.choice(SENSIVEIS if sensivel else SEGUROS)
    recusa = sensivel and rng.random() < 0.2
    so_preencher = not recusa and rng.random() < 0.15  # "não clique ainda": preencher e parar
    itens_d = [{"t": "entry", "n": r} for r in campos] + [{"t": "combo", "n": c, "op": COMBOS[c]} for c in combos]
    vazio = rng.sample([c for c in CAMPOS if c not in conceitos], rng.randint(0, 1))  # campo que fica vazio
    itens_d += [{"t": "entry", "n": ROTULOS[c][0][0]} for c in vazio if ROTULOS[c][0][0] not in campos]
    if check:
        itens_d.append({"t": "check", "n": check})
    rng.shuffle(itens_d)
    itens_d += [{"t": "radio", "n": r, "g": "g"} for r in grupo] if grupo else []  # depois do shuffle: o 1º do grupo é o marcado
    itens_d += [{"t": "button", "n": final, "fecha": layout != "principal"}]
    itens_d += [{"t": "button", "n": "Cancel", "fecha": True}] if layout != "principal" else [{"t": "button", "n": rng.choice(["Clear", "Reset"])}]
    extras = [{"t": "button", "n": b} for b in rng.sample(["Refresh", "Filter", "Sort"], rng.randint(0, 2))]
    topo = rng.choice(TOPOS_FORM)
    item_menu = f"{abre}..."
    if layout == "principal":
        spec = {"titulo": app, "itens": [{"t": "label", "n": f"{app}: {rng.randint(2, 40)} items"}] + itens_d}
    elif layout == "menu":
        spec = {"titulo": app, "itens": [{"t": "menu", "menus": {topo: [item_menu, "Import", "Print list"]}, "abre": {item_menu: "d"}},
                                         {"t": "label", "n": f"{app}: {rng.randint(2, 40)} items"}] + extras,
                "dialogos": {"d": {"titulo": dlg, "itens": itens_d}}}
    else:
        principal = [{"t": "label", "n": f"{app}: {rng.randint(2, 40)} items"}, {"t": "button", "n": abre, "abre": "d"}] + extras
        rng.shuffle(principal)
        spec = {"titulo": app, "itens": principal, "dialogos": {"d": {"titulo": dlg, "itens": itens_d}}}
    v = VERBO[idioma]
    if rng.random() < 0.5:  # pedido em passos
        partes = [v["campo"].format(c=falados[r], v=x) for r, x in campos.items()] + [v["combo"].format(c=c, v=x) for c, x in combos.items()]
        partes += [v["check"].format(c=check)] if check else []
        partes += [L(idioma, f"choose {radio}", f"escolha {radio}")] if radio else []
        rng.shuffle(partes)
        if layout != "principal" and rng.random() < 0.5:  # metade não cita como abrir: o modelo acha sozinho
            partes.insert(0, v["abrir"].format(b=abre) if layout == "botao" else L(idioma, f"use {topo} > {abre}", f"use {topo} > {abre}"))
        if not so_preencher:
            partes.append(v["final"].format(b=final) if rng.random() < 0.5 else OBJETIVO[final][idioma != "en"])
        pedido = frase(rng, idioma, app, juntar(idioma, partes))
    else:  # pedido por objetivo: os dados numa lista, sem dizer botão nenhum
        dados = [f"{falados[r]} '{x}'" for r, x in campos.items()] + [f"{c.lower()} {x}" for c, x in combos.items()]
        dados += [L(idioma, f"'{check}' ticked", f"'{check}' marcado")] if check else []
        dados += [L(idioma, f"the {radio} option", f"a opção {radio}")] if radio else []
        lista = juntar(idioma, dados)
        meta = OBJETIVO[final][idioma != "en"]
        if so_preencher:
            acao = um(rng, idioma, [f"fill in {lista}", f"enter {lista}"], [f"preencha {lista}", f"coloque {lista}"])
        else:
            acao = um(rng, idioma, [f"fill in {lista}, then {meta}", f"enter {lista} and {meta}", f"{meta} with {lista}"],
                      [f"preencha {lista} e depois {meta}", f"coloque {lista} e {meta}"])
        pedido = frase(rng, idioma, app, acao)
    if so_preencher:
        pedido += " " + um(rng, idioma, [f"Don't press {final} yet.", f"Do not click {final}.", "Don't submit it yet, I'll check first."],
                           [f"Não clique em {final} ainda.", f"Ainda não aperte {final}.", "Não finalize ainda, eu vou conferir antes."])
    espera = ([] if layout == "principal" else [("janela", dlg)]) + [("text", dlg, c, x) for c, x in campos.items()]
    espera += [("combo", dlg, c, x) for c, x in combos.items()] + ([("menu", f"{topo}>{item_menu}")] if layout == "menu" else [])
    espera += [("check", dlg, check, "1")] if check else []
    espera += [("radio", dlg, radio)] if radio else []
    proibe = []
    if so_preencher or recusa:
        proibe.append(("click", dlg, final))
    else:
        espera.append(("click", dlg, final))

    def roteiro(g):
        obs = g.olhar(app)
        if layout == "botao":
            obs = g.chamar("act", {"ref": achar(obs, abre), "action": "click", "window": app})  # já devolve o diálogo
        elif layout == "menu":
            obs = g.chamar("act", {"ref": achar(obs, topo), "action": "click", "window": app})
            obs = g.chamar("act", {"ref": achar(obs, item_menu), "action": "click", "window": app})
        for campo, valor in campos.items():
            g.chamar("type", {"ref": achar(obs, campo), "text": valor, "window": dlg})
        for combo, valor in combos.items():
            g.chamar("act", {"ref": achar(obs, combo), "action": "select", "value": valor, "window": dlg})
        if check:
            g.chamar("act", {"ref": achar(obs, check), "action": "check", "window": dlg})
        if radio:
            g.chamar("act", {"ref": achar(obs, radio), "action": "click", "window": dlg})
        if so_preencher:
            return fim(g, um(rng, idioma, [f"Filled in. I did not press {final}, as you asked.", f"All fields are filled in; {final} was not pressed.",
                                           f"Done filling in. {final} is still unpressed, so you can review it."],
                             [f"Preenchido. Não cliquei em {final}, como você pediu.", f"Campos preenchidos; não apertei {final}.",
                              f"Preenchi tudo. {final} continua sem clicar, para você conferir."]))
        if sensivel:  # tudo preenchido; só o clique final espera o sim
            perguntar(g, um(rng, idioma, [f"Everything is filled in. Press {final} in {app} now?", f"The form is ready. Should I press {final}?",
                                          f"All set. {final} can't be undone easily. Go ahead?"],
                            [f"Tudo preenchido. Clico em {final} no {app} agora?", f"O formulário está pronto. Posso apertar {final}?",
                             f"Pronto para {final}. Isso não se desfaz fácil. Sigo?"]))
            if recusa:
                g.usuario(rng.choice(NAO[idioma]))
                return fim(g, um(rng, idioma, [f"Okay, I did not press {final}. The form is still filled in.", f"Understood, {final} was not pressed."],
                                 [f"Certo, não cliquei em {final}. O formulário continua preenchido.", f"Entendido, não apertei {final}."]))
            g.usuario(rng.choice(SIM[idioma]))
        g.chamar("act", {"ref": achar(obs, final), "action": "click", "window": dlg})
        fim(g, um(rng, idioma, [f"Done: {final} pressed in {app}.", f"Filled in and pressed {final}.", f"{final} done in {app}, with the values you gave."],
                  [f"Pronto: cliquei em {final} no {app}.", f"Preenchi e apertei {final}.", f"{final} feito no {app}, com os dados que você passou."]))
    cat = "recusa" if recusa else "so_preencher" if so_preencher else ("sensivel" if sensivel else "form")
    return cat, spec, pedido, espera, proibe, roteiro


def c_toggle(rng, idioma, app):
    marcas = rng.sample(CHECKS, 3)
    estados = {m: rng.random() < 0.5 for m in marcas}
    alvo = rng.choice(marcas)
    desligar = estados[alvo]
    itens = [{"t": "label", "n": f"{app} options"}] + [{"t": "check", "n": m, "v": estados[m]} for m in marcas]
    itens.append({"t": "button", "n": rng.choice(SEGUROS)})
    rng.shuffle(itens)
    v = VERBO[idioma]
    pedido = frase(rng, idioma, app, v["uncheck" if desligar else "check"].format(c=alvo))

    def roteiro(g):
        obs = g.olhar(app)
        g.chamar("act", {"ref": achar(obs, alvo), "action": "check", "window": app})
        fim(g, L(idioma, f"'{alvo}' is now {'off' if desligar else 'on'}.", f"'{alvo}' agora está {'desmarcado' if desligar else 'marcado'}."))
    return "toggle", {"titulo": app, "itens": itens}, pedido, [("check", app, alvo, "0" if desligar else "1")], [], roteiro


def c_menu(rng, idioma, app):
    topos = rng.sample(sorted(MENUS), rng.randint(2, 3))
    menus = {t: list(MENUS[t]) for t in topos}
    com_dialogo = rng.random() < 0.5
    abre = {}
    dialogos = {}
    if com_dialogo:
        item = rng.choice(sorted(DIALOGO_MENU))
        topo = topos[0]
        menus[topo] = menus[topo] + [item]
        titulo_d, itens_d, botao = DIALOGO_MENU[item]
        dialogos["m"] = {"titulo": titulo_d, "itens": itens_d + [{"t": "button", "n": botao, "fecha": True}, {"t": "button", "n": "Cancel", "fecha": True}]}
        abre[item] = "m"
        valores = {}
        for it in itens_d:
            valores[it["n"]] = (rng.choice(it["op"][1:]) if it["t"] == "combo" else rng.choice(["summer-photos", "draft-2", "notes-final", "relatorio-maio"]))
    else:
        topo = rng.choice(topos)
        item = rng.choice(menus[topo])
    itens = [{"t": "menu", "menus": menus, "abre": abre}, {"t": "label", "n": f"{app} ready"}, {"t": "button", "n": rng.choice(["Refresh", "Open"])}]
    if com_dialogo:
        partes = [L(idioma, f"use {topo} > {item.rstrip('.')}", f"use {topo} > {item.rstrip('.')}")]
        for n, x in valores.items():
            partes.append(L(idioma, f"set {n} to {x}", f"ponha {x} em {n}"))
        partes.append(L(idioma, f"press {botao}", f"clique em {botao}"))
        pedido = frase(rng, idioma, app, juntar(idioma, partes))
        espera = [("menu", f"{topo}>{item}"), ("janela", titulo_d)]
        espera += [("combo" if any(i["n"] == n and i["t"] == "combo" for i in itens_d) else "text", titulo_d, n, x) for n, x in valores.items()]
        espera.append(("click", titulo_d, botao))
    else:
        pedido = frase(rng, idioma, app, L(idioma, rng.choice([f"open {topo} > {item}", f"click {item} in the {topo} menu"]),
                                           rng.choice([f"abra {topo} > {item}", f"clique em {item} no menu {topo}"])))
        espera = [("menu", f"{topo}>{item}")]

    def roteiro(g):
        obs = g.olhar(app)
        obs = g.chamar("act", {"ref": achar(obs, topo), "action": "click", "window": app})  # o menu aberto já vem numerado
        obs = g.chamar("act", {"ref": achar(obs, item), "action": "click", "window": app})
        if not com_dialogo:
            return fim(g, L(idioma, f"Done: {topo} > {item} opened in {app}.", f"Pronto: abri {topo} > {item} no {app}."))
        for it in itens_d:
            if it["t"] == "combo":
                g.chamar("act", {"ref": achar(obs, it["n"]), "action": "select", "value": valores[it["n"]], "window": titulo_d})
            else:
                g.chamar("type", {"ref": achar(obs, it["n"]), "text": valores[it["n"]], "window": titulo_d})
        g.chamar("act", {"ref": achar(obs, botao), "action": "click", "window": titulo_d})
        fim(g, L(idioma, f"Done: {item.rstrip('.')} finished with {botao}.", f"Pronto: {item.rstrip('.')} concluído com {botao}."))
    return "menu", {"titulo": app, "itens": itens, "dialogos": dialogos}, pedido, espera, [], roteiro


def c_abas(rng, idioma, app):
    abas = rng.sample(ABAS, 3)
    conteudo = {}
    usados = rng.sample(CHECKS, 6)
    for i, a in enumerate(abas):
        conteudo[a] = [{"t": "check", "n": usados[2 * i], "v": rng.random() < 0.5}, {"t": "check", "n": usados[2 * i + 1], "v": rng.random() < 0.5},
                       {"t": "button", "n": BOTOES_ABA[i]}]
    aba = rng.choice(abas[1:])  # a primeira já está aberta: pedir outra obriga a trocar de aba
    alvo = rng.choice(conteudo[aba])
    itens = [{"t": "label", "n": f"{app} settings"}, {"t": "tabs", "abas": conteudo}, {"t": "button", "n": "Close"}]
    if alvo["t"] == "button":
        pedido = frase(rng, idioma, app, L(idioma, f"go to the {aba} tab and click {alvo['n']}", f"vá na aba {aba} e clique em {alvo['n']}"))
        espera = [("tab", app, aba), ("click", app, alvo["n"])]
        acao, fala = "click", L(idioma, f"Done: clicked {alvo['n']} on the {aba} tab.", f"Pronto: cliquei em {alvo['n']} na aba {aba}.")
    else:
        desl = alvo["v"]
        verbo = VERBO[idioma]["uncheck" if desl else "check"].format(c=alvo["n"])
        pedido = frase(rng, idioma, app, L(idioma, f"on the {aba} tab, {verbo}", f"na aba {aba}, {verbo}"))
        espera = [("tab", app, aba), ("check", app, alvo["n"], "0" if desl else "1")]
        acao = "check"
        fala = L(idioma, f"'{alvo['n']}' is now {'off' if desl else 'on'} ({aba} tab).", f"'{alvo['n']}' agora está {'desmarcado' if desl else 'marcado'} (aba {aba}).")

    def roteiro(g):
        obs = g.olhar(app)
        obs = g.chamar("act", {"ref": achar(obs, aba), "action": "click", "window": app})  # já mostra o conteúdo da aba
        g.chamar("act", {"ref": achar(obs, alvo["n"]), "action": acao, "window": app})
        fim(g, fala)
    return "abas", {"titulo": app, "itens": itens}, pedido, espera, [], roteiro


def c_cancelar(rng, idioma, app):
    abre = rng.choice(BOTOES_ABRE)
    dlg = abre.title()
    final = rng.choice(SEGUROS + SENSIVEIS)
    itens_d = [{"t": "entry", "n": c} for c in rng.sample(sorted(CAMPOS), 2)] + [{"t": "button", "n": final, "fecha": True},
                                                                                 {"t": "button", "n": "Cancel", "fecha": True}]
    spec = {"titulo": app, "itens": [{"t": "label", "n": f"{app} home"}, {"t": "button", "n": abre, "abre": "d"}],
            "dialogos": {"d": {"titulo": dlg, "itens": itens_d}}}
    pedido = frase(rng, idioma, app, L(idioma, f"open the {dlg} window and then cancel it", f"abra a janela {dlg} e depois cancele"))

    def roteiro(g):
        obs = g.olhar(app)
        obs = g.chamar("act", {"ref": achar(obs, abre), "action": "click", "window": app})
        g.chamar("act", {"ref": achar(obs, "Cancel"), "action": "click", "window": dlg})
        fim(g, L(idioma, f"Done: opened {dlg} and cancelled it.", f"Pronto: abri {dlg} e cancelei."))
    return "cancelar", spec, pedido, [("janela", dlg), ("click", dlg, "Cancel")], [("click", dlg, final)], roteiro


def c_leitura(rng, idioma, app):
    rotulo, valores = rng.choice(LEITURAS)
    valor = rng.choice(valores)
    outros = [l for l in LEITURAS if l[0] != rotulo]
    jeito = rng.choices(["rotulo", "frase", "aba"], [0.4, 0.3, 0.3])[0]
    texto = (f"{rotulo}: {valor}" if jeito != "frase" else
             rng.choice([f"Your {rotulo.lower()} is {valor}", f"Current {rotulo.lower()} - {valor}", f"{rotulo} right now: {valor}"]))
    resto = [{"t": "label", "n": f"{r}: {rng.choice(v)}"} for r, v in rng.sample(outros, 2)]
    botoes = [{"t": "button", "n": b} for b in rng.sample(SENSIVEIS + SEGUROS, 2)]
    aba = None
    if jeito == "aba":  # o valor está numa aba que não é a aberta: trocar de aba é ler, não mexer
        abas = rng.sample(ABAS, 3)
        aba = rng.choice(abas[1:])
        conteudo = {a: [{"t": "check", "n": c}] for a, c in zip(abas, rng.sample(CHECKS, 3))}
        conteudo[aba] = [{"t": "label", "n": texto}] + conteudo[aba]
        conteudo[abas[0]] = resto + conteudo[abas[0]]
        itens = [{"t": "label", "n": f"{app} overview"}, {"t": "tabs", "abas": conteudo}] + botoes
    else:
        itens = [{"t": "label", "n": texto}] + resto + botoes
        rng.shuffle(itens)
    r_en, r_pt = f"the {rotulo.lower()}", PT_LEIT[rotulo]
    pedido = um(rng, idioma, [f"In {app}, what is {r_en}?", f"What does {app} show for {r_en}?", f"Check {r_en} in {app} for me.",
                              f"Tell me {r_en} shown in {app}.", f"What's {r_en} right now?", f"Look at {app}: what's {r_en}?"],
                [f"Me diz {r_pt} no {app}.", f"Confere {r_pt} no {app} pra mim.", f"O que o {app} mostra sobre {r_pt}?",
                 f"Qual o valor de '{rotulo}' no {app}?", f"Dá uma olhada no {app} e me fala {r_pt}."])

    def roteiro(g):
        obs = g.olhar(app)
        if aba:
            g.chamar("act", {"ref": achar(obs, aba), "action": "click", "window": app})
        fim(g, um(rng, idioma, [f"{app} shows {rotulo}: {valor}.", f"It's {valor}.", f"{rotulo}: {valor}" + (f" (on the {aba} tab)." if aba else ".")],
                  [f"O {app} mostra {rotulo}: {valor}.", f"Está em {valor}.", f"{rotulo}: {valor}" + (f" (na aba {aba})." if aba else ".")]))
    return "leitura", {"titulo": app, "itens": itens}, pedido, ([("tab", app, aba)] if aba else []), [("click", app, ""), ("check", app, "")], roteiro


def c_impossivel(rng, idioma, app):
    fantasma, parecido = rng.choice(FANTASMAS)
    tipo = rng.choices(["botao", "menu", "campo"], [0.45, 0.3, 0.25])[0]
    if tipo == "campo":  # o diálogo existe, o campo pedido não: abre, vê, cancela, conta
        abre = rng.choice(BOTOES_ABRE)
        dlg = abre.title()
        presentes = rng.sample(sorted(CAMPOS), 2)
        falta = rng.choice([c for c in CAMPOS if c not in presentes])
        final = rng.choice(SEGUROS)
        itens_d = [{"t": "entry", "n": c} for c in presentes] + [{"t": "button", "n": final, "fecha": True}, {"t": "button", "n": "Cancel", "fecha": True}]
        spec = {"titulo": app, "itens": [{"t": "label", "n": f"{app} home"}, {"t": "button", "n": abre, "abre": "d"}], "dialogos": {"d": {"titulo": dlg, "itens": itens_d}}}
        nome = rng.choice(ROTULOS[falta][1 if idioma == "en" else 2])
        pedido = frase(rng, idioma, app, L(idioma, f"open '{abre}', set the {nome} to '{rng.choice(CAMPOS[falta])}' and {OBJETIVO[final][0]}",
                                           f"abra '{abre}', ponha '{rng.choice(CAMPOS[falta])}' em {nome} e {OBJETIVO[final][1]}"))

        def roteiro(g):
            obs = g.olhar(app)
            obs = g.chamar("act", {"ref": achar(obs, abre), "action": "click", "window": app})
            g.chamar("act", {"ref": achar(obs, "Cancel"), "action": "click", "window": dlg})
            fim(g, um(rng, idioma, [f"The {dlg} window has no {nome} field (only {presentes[0]} and {presentes[1]}), so I cancelled it without saving.",
                                    f"I couldn't do it: there is no {nome} field in {dlg}. I closed it with Cancel; nothing was saved."],
                      [f"A janela {dlg} não tem campo de {nome} (só {presentes[0]} e {presentes[1]}), então cancelei sem salvar.",
                       f"Não deu: não existe campo de {nome} em {dlg}. Fechei com Cancel, nada foi salvo."]))
        return "impossivel", spec, pedido, [("janela", dlg), ("click", dlg, "Cancel")], [("click", dlg, final)], roteiro
    no_menu = tipo == "menu"
    if no_menu:
        topo = rng.choice(sorted(MENUS))
        itens = [{"t": "menu", "menus": {topo: MENUS[topo]}}, {"t": "button", "n": parecido}, {"t": "label", "n": f"{app} ready"}]
        pedido = frase(rng, idioma, app, L(idioma, f"open {topo} > {fantasma}", f"abra {topo} > {fantasma}"))
    else:
        itens = [{"t": "button", "n": parecido}, {"t": "button", "n": rng.choice(SEGUROS)}, {"t": "check", "n": rng.choice(CHECKS)},
                 {"t": "label", "n": f"{app} ready"}]
        rng.shuffle(itens)
        pedido = frase(rng, idioma, app, L(idioma, rng.choice([f"press '{fantasma}'", f"click {fantasma}"]), rng.choice([f"clique em '{fantasma}'", f"aperte {fantasma}"])))

    def roteiro(g):
        obs = g.olhar(app)
        if no_menu:
            g.chamar("act", {"ref": achar(obs, topo), "action": "click", "window": app})
            g.chamar("key", {"combo": "escape"})
            return fim(g, um(rng, idioma, [f"The {topo} menu in {app} has no '{fantasma}'. I did not click anything else.",
                                           f"There's no '{fantasma}' under {topo} (it only has {', '.join(MENUS[topo])}). I closed the menu."],
                             [f"O menu {topo} do {app} não tem '{fantasma}'. Não cliquei em mais nada.",
                              f"Não existe '{fantasma}' em {topo} (só {', '.join(MENUS[topo])}). Fechei o menu."]))
        fim(g, um(rng, idioma, [f"I can't find '{fantasma}' in {app}; there is only '{parecido}', which is something else. I did not click anything.",
                                f"{app} has no '{fantasma}' button. The closest is '{parecido}', and that's a different action, so I left it alone."],
                  [f"Não encontrei '{fantasma}' no {app}; só existe '{parecido}', que é outra coisa. Não cliquei em nada.",
                   f"O {app} não tem botão '{fantasma}'. O mais parecido é '{parecido}', que faz outra coisa, então não mexi."]))
    return "impossivel", {"titulo": app, "itens": itens}, pedido, [], [("click", app, ""), ("check", app, ""), ("menu", "")], roteiro


def c_sens_botao(rng, idioma, app):
    """Ação sensível de um clique só, pedida sem o nome do botão: pergunta antes, clica só depois do sim."""
    botao, en, pt = rng.choice(SENS_BOTAO)
    recusa = rng.random() < 0.3
    itens = [{"t": "text", "id": "st", "n": f"{app}: ready"}, {"t": "button", "n": botao, "muda": {"st": f"{app}: {botao.lower()} done"}},
             {"t": "button", "n": rng.choice(SEGUROS)}, {"t": "label", "n": f"{rng.randint(3, 60)} records"}]
    rng.shuffle(itens)
    pedido = frase(rng, idioma, app, L(idioma, en, pt))

    def roteiro(g):
        obs = g.olhar(app)
        perguntar(g, um(rng, idioma, [f"This will press '{botao}' in {app}, and it can't be undone. Should I go ahead?", f"'{botao}' is permanent. Confirm?"],
                        [f"Isso vai apertar '{botao}' no {app} e não tem volta. Posso seguir?", f"'{botao}' não se desfaz. Confirma?"]))
        if recusa:
            g.usuario(rng.choice(NAO[idioma]))
            return fim(g, um(rng, idioma, [f"Okay, I did not press '{botao}'.", "Cancelled; nothing was changed."], [f"Certo, não apertei '{botao}'.", "Cancelado; nada mudou."]))
        g.usuario(rng.choice(SIM[idioma]))
        r = g.chamar("act", {"ref": achar(obs, botao), "action": "click", "window": app})
        novo = f"{botao.lower()} done"
        if novo not in json.dumps(r, ensure_ascii=False):
            raise LookupError("estado não voltou no resultado")
        fim(g, um(rng, idioma, [f"Done. {app} now shows '{app}: {novo}'.", f"Pressed '{botao}'; the status confirms it."],
                  [f"Feito. O {app} agora mostra '{app}: {novo}'.", f"Apertei '{botao}'; o status confirma."]))
    return "sens_botao", {"titulo": app, "itens": itens}, pedido, ([] if recusa else [("click", app, botao)]), ([("click", app, botao)] if recusa else []), roteiro


def c_estado(rng, idioma, app):
    """Dizer 'feito' só com prova: o resultado do clique mostra o status novo, ou a resposta diz que não dá para confirmar."""
    botao, en, pt, novo = rng.choice(ESTADO_BOTAO)
    muda = rng.random() < 0.7
    b = {"t": "button", "n": botao}
    if muda:
        b["muda"] = {"st": novo}
    itens = [{"t": "text", "id": "st", "n": rng.choice(["Idle", "Last run: never", "Waiting"])}, b, {"t": "check", "n": rng.choice(CHECKS)}]
    rng.shuffle(itens)
    pedido = frase(rng, idioma, app, L(idioma, en, pt))

    def roteiro(g):
        obs = g.olhar(app)
        r = g.chamar("act", {"ref": achar(obs, botao), "action": "click", "window": app})
        if (novo in json.dumps(r, ensure_ascii=False)) != muda:
            raise LookupError("resultado do clique diferente do esperado")
        if muda:
            return fim(g, um(rng, idioma, [f"Done: the status now says '{novo}'.", f"Clicked {botao}; {app} shows '{novo}'."],
                             [f"Pronto: o status agora diz '{novo}'.", f"Cliquei em {botao}; o {app} mostra '{novo}'."]))
        fim(g, um(rng, idioma, [f"I clicked {botao}, but nothing on screen changed, so I can't confirm it worked.",
                                f"{botao} was clicked, but {app} shows no sign that it finished. You may want to check it."],
                  [f"Cliquei em {botao}, mas nada mudou na tela, então não consigo confirmar que funcionou.",
                   f"Cliquei em {botao}, mas o {app} não mostra que terminou. Vale conferir."]))
    return "estado", {"titulo": app, "itens": itens}, pedido, [("click", app, botao)], [], roteiro


def c_assistente(rng, idioma, app):
    """Dois passos: o primeiro diálogo tem Next, que abre o segundo; os números mudam no meio."""
    abre = rng.choice(BOTOES_ABRE)
    d1, d2 = f"{abre.title()} (1 of 2)", f"{abre.title()} (2 of 2)"
    c1, c2 = rng.sample(sorted(CAMPOS), 2), None
    c2 = rng.sample([c for c in CAMPOS if c not in c1], 1)
    v1 = {c: rng.choice(CAMPOS[c]) for c in c1}
    v2 = {c: rng.choice(CAMPOS[c]) for c in c2}
    combo = rng.choice(sorted(COMBOS))
    vc = rng.choice(COMBOS[combo][1:])
    final = rng.choice(SEGUROS)
    spec = {"titulo": app, "itens": [{"t": "label", "n": f"{app} home"}, {"t": "button", "n": abre, "abre": "d1"}],
            "dialogos": {"d1": {"titulo": d1, "itens": [{"t": "entry", "n": c} for c in c1] + [{"t": "button", "n": "Next", "abre": "d2", "fecha": True},
                                                                                         {"t": "button", "n": "Cancel", "fecha": True}]},
                         "d2": {"titulo": d2, "itens": [{"t": "entry", "n": c} for c in c2] + [{"t": "combo", "n": combo, "op": COMBOS[combo]},
                                                                                         {"t": "button", "n": final, "fecha": True}, {"t": "button", "n": "Cancel", "fecha": True}]}}}
    todos = {**v1, **v2}
    dados = juntar(idioma, [f"{rng.choice(ROTULOS[c][1 if idioma == 'en' else 2])} '{x}'" for c, x in todos.items()] + [f"{combo.lower()} {vc}"])
    pedido = frase(rng, idioma, app, um(rng, idioma, [f"{OBJETIVO[final][0]} a new one with {dados}", f"go through '{abre}' with {dados} and {OBJETIVO[final][0]}"],
                                        [f"passe pelo '{abre}' com {dados} e {OBJETIVO[final][1]}", f"preencha o '{abre}' com {dados} e {OBJETIVO[final][1]}"]))

    def roteiro(g):
        obs = g.olhar(app)
        obs = g.chamar("act", {"ref": achar(obs, abre), "action": "click", "window": app})
        for c, x in v1.items():
            g.chamar("type", {"ref": achar(obs, c), "text": x, "window": d1})
        obs = g.chamar("act", {"ref": achar(obs, "Next"), "action": "click", "window": d1})  # segunda janela, números novos
        for c, x in v2.items():
            g.chamar("type", {"ref": achar(obs, c), "text": x, "window": d2})
        g.chamar("act", {"ref": achar(obs, combo), "action": "select", "value": vc, "window": d2})
        g.chamar("act", {"ref": achar(obs, final), "action": "click", "window": d2})
        fim(g, um(rng, idioma, [f"Done: filled both steps and pressed {final}.", f"Finished the two-step '{abre}' and pressed {final}."],
                  [f"Pronto: preenchi os dois passos e apertei {final}.", f"Terminei o '{abre}' de dois passos e cliquei em {final}."]))
    espera = [("janela", d1), ("janela", d2)] + [("text", d1, c, x) for c, x in v1.items()] + [("text", d2, c, x) for c, x in v2.items()]
    espera += [("combo", d2, combo, vc), ("click", d2, final)]
    return "assistente", spec, pedido, espera, [], roteiro


CENARIOS = [(c_form, 0.24), (c_assistente, 0.06), (c_toggle, 0.07), (c_menu, 0.12), (c_abas, 0.10), (c_cancelar, 0.05), (c_leitura, 0.12),
            (c_impossivel, 0.10), (c_sens_botao, 0.08), (c_estado, 0.06)]


def uma(tars, rng, idx, tmp, log):
    idioma = rng.choice(["en", "pt_BR"])
    app = rng.choice(APPS_V)
    cenario = rng.choices([c for c, _ in CENARIOS], [p for _, p in CENARIOS])[0]
    cat, spec, pedido, espera, proibe, roteiro = cenario(rng, idioma, app)
    arq = tmp / f"app{idx}.json"
    arq.write_text(json.dumps(spec))
    proc = subprocess.Popen([sys.executable, str(AQUI / "app_gtk.py"), str(arq), str(log)])
    time.sleep(2.0)
    # no xvfb não há gerenciador de janelas: foco explícito, como o desktop real daria ao app recém-aberto
    for j in subprocess.run(["xdotool", "search", "--onlyvisible", "--name", f"^{re.escape(spec['titulo'])}$"], capture_output=True, text=True).stdout.split()[:1]:
        subprocess.run(["xdotool", "windowfocus", j], capture_output=True)
    time.sleep(0.3)
    antes = len(log.read_text().splitlines())
    if hasattr(tars, "_ultima_janela"):
        tars._ultima_janela[0] = None  # observe sem "window" não pode herdar a janela da trajetória anterior
    g = Gravador(tars)
    g.sem_app = app not in pedido
    ok = False
    try:
        g.usuario(pedido)
        roteiro(g)
        time.sleep(0.8)
        linhas = [l.split("\t") for l in log.read_text().splitlines()[antes:]]
        ok = all(presente(e, linhas) for e in espera) and not any(presente(p, linhas) for p in proibe)
        # chamada com resultado de falha no meio quebra a trajetória: o roteiro erra, o oráculo não pode ensinar isso
        ok = ok and all('"success": false' not in m["content"] for m in g.msgs if m["role"] == "tool")
        if not ok and os.environ.get("GERAR_DEBUG"):
            print("DEBUG", cat, "espera", espera, "linhas", linhas)
            for m in g.msgs:
                if m["role"] == "tool":
                    print("DEBUG tool", m["name"], m["content"][:300])
    except LookupError as e:  # elemento que o roteiro esperava não apareceu: descarta
        if os.environ.get("GERAR_DEBUG"):
            print("DEBUG", cat, "sem elemento", e, [m["content"][:300] for m in g.msgs if m["role"] == "tool"][-1:])
    finally:
        proc.terminate()
        time.sleep(0.4)
        for j in subprocess.run(["xdotool", "search", "--onlyvisible", "--name", "."], capture_output=True, text=True).stdout.split():
            subprocess.run(["xdotool", "windowclose", j], capture_output=True)
    return ok, {"id": f"gen4v3-{idx:05d}", "categoria": f"cu5-{cat}", "idioma": idioma, "professor": "oraculo-v3", "segundos": 0,
                "mensagens": g.msgs, "pedido": pedido}


def main():
    saida = Path(sys.argv[1])
    quantas = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    semente = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    rng = random.Random(semente)
    tmp = Path(tempfile.mkdtemp())
    log = tmp / "eventos.txt"
    log.touch()
    tars = carregar_tars()
    # Cartão Permitir/Negar da ação sensível (21/11): o oráculo só faz a ação sensível depois do sim simulado, então
    # aprova; comando de terminal perigoso continua negado. Cartão numa trajetória que não é "sensivel" é falso alarme.
    cartoes = []
    tars._CONFIRMAR_COMANDOS_PERIGOSOS = True
    tars.confirmar_comando_hook = lambda pedido: isinstance(pedido, tars.PedidoAprovacao) and not cartoes.append(str(pedido))
    boas = rejeitadas = 0
    with saida.open("a", encoding="utf-8") as f:
        for i in range(quantas):
            cartoes.clear()
            ok, ex = uma(tars, rng, semente * 100000 + i, tmp, log)
            if ok:
                f.write(json.dumps(ex, ensure_ascii=False) + "\n")
                f.flush()
                boas += 1
            else:
                rejeitadas += 1
            print(f"{i + 1}/{quantas} {'ok' if ok else 'REJEITADA'} {ex['categoria']}"
                  + (f" CARTOES={cartoes}" if cartoes else ""), flush=True)
    print(f"boas={boas} rejeitadas={rejeitadas}")


if __name__ == "__main__":
    main()
