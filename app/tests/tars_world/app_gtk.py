"""App GTK de teste da bateria TARS-World, montado a partir de uma spec JSON.

Uso: python3 app_gtk.py SPEC.json LOG.txt
Cada ação da pessoa (ou da IA) vira uma linha no LOG, separada por tabulação:
  click <janela> <botão> | text <janela> <campo> <valor> | check <janela> <nome> 0/1
  combo <janela> <nome> <opção> | radio <janela> <nome> | menu <caminho> | tab <janela> <aba> | janela <título>
A spec descreve a janela principal e os diálogos (janelas que um botão abre).
"""
import json
import sys

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

spec = json.load(open(sys.argv[1], encoding="utf-8"))
log = open(sys.argv[2], "a", buffering=1, encoding="utf-8")
janelas = {}


def ev(*partes):
    log.write("\t".join(str(p) for p in partes) + "\n")


def nomear(w, nome):
    w.get_accessible().set_name(nome)


def montar(itens, titulo, caixa):
    grupo_radio = {}
    for it in itens:
        t, n = it["t"], it.get("n", "")
        if t == "label":
            caixa.pack_start(Gtk.Label(label=n, xalign=0), False, False, 0)
        elif t == "button":
            b = Gtk.Button(label=n)

            def clicou(_b, it=it, n=n):
                ev("click", titulo, n)
                if it.get("muda"):
                    for rot, novo in it["muda"].items():
                        rotulos[rot].set_text(novo)
                if it.get("abre"):
                    abrir(it["abre"])
                if it.get("fecha"):
                    janelas[titulo].hide()
            b.connect("clicked", clicou)
            caixa.pack_start(b, False, False, 0)
        elif t == "entry":
            linha = Gtk.Box(spacing=6)
            linha.pack_start(Gtk.Label(label=n), False, False, 0)
            e = Gtk.Entry()
            e.set_text(it.get("v", ""))
            nomear(e, n)
            e.connect("changed", lambda w, n=n: ev("text", titulo, n, w.get_text()))
            linha.pack_start(e, True, True, 0)
            caixa.pack_start(linha, False, False, 0)
        elif t in ("check", "toggle"):
            c = Gtk.CheckButton(label=n) if t == "check" else Gtk.ToggleButton(label=n)
            c.set_active(bool(it.get("v")))
            c.connect("toggled", lambda w, n=n: ev("check", titulo, n, int(w.get_active())))
            caixa.pack_start(c, False, False, 0)
        elif t == "radio":
            g = it.get("g", "r")
            r = Gtk.RadioButton.new_with_label_from_widget(grupo_radio.get(g), n)
            grupo_radio.setdefault(g, r)
            r.connect("toggled", lambda w, n=n: w.get_active() and ev("radio", titulo, n))
            caixa.pack_start(r, False, False, 0)
        elif t == "combo":
            linha = Gtk.Box(spacing=6)
            linha.pack_start(Gtk.Label(label=n), False, False, 0)
            c = Gtk.ComboBoxText()
            for op in it["op"]:
                c.append_text(op)
            c.set_active(0)
            nomear(c, n)
            c.connect("changed", lambda w, n=n: ev("combo", titulo, n, w.get_active_text()))
            linha.pack_start(c, False, False, 0)
            caixa.pack_start(linha, False, False, 0)
        elif t == "text":
            rotulos[it["id"]] = Gtk.Label(label=n, xalign=0)
            caixa.pack_start(rotulos[it["id"]], False, False, 0)
        elif t == "tabs":
            nb = Gtk.Notebook()
            for aba, sub in it["abas"].items():
                cx = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=8)
                montar(sub, titulo, cx)
                nb.append_page(cx, Gtk.Label(label=aba))
            nb.connect("switch-page", lambda _nb, _p, i, it=it: ev("tab", titulo, list(it["abas"])[i]))
            caixa.pack_start(nb, True, True, 0)
        elif t == "menu":
            barra = Gtk.MenuBar()
            for topo, filhos in it["menus"].items():
                m = Gtk.MenuItem(label=topo)
                sub = Gtk.Menu()
                for f in filhos:
                    mi = Gtk.MenuItem(label=f)
                    mi.connect("activate", lambda _m, p=f"{topo}>{f}", f=f, it=it: (ev("menu", p), it.get("abre", {}).get(f) and abrir(it["abre"][f])))
                    sub.append(mi)
                m.set_submenu(sub)
                barra.append(m)
            caixa.pack_start(barra, False, False, 0)


rotulos = {}


def criar(d, principal=False):
    w = Gtk.Window(title=d["titulo"])
    w.set_default_size(d.get("w", 520), d.get("h", 380))
    cx = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=10)
    w.add(cx)
    montar(d["itens"], d["titulo"], cx)
    if principal:
        w.connect("destroy", Gtk.main_quit)
    else:
        w.connect("delete-event", lambda w, _e: w.hide() or True)
    janelas[d["titulo"]] = w
    return w


def abrir(nome):
    d = spec["dialogos"][nome]
    w = janelas.get(d["titulo"]) or criar(d)
    w.set_transient_for(janelas[spec["titulo"]])
    w.show_all()
    w.present()
    ev("janela", d["titulo"])


criar(spec, principal=True).show_all()
Gtk.main()
