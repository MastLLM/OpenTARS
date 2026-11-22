// Registra um evento no servidor da bateria (servidor.py grava no log).
function ev(e, v) { fetch("/ev?e=" + encodeURIComponent(e) + "&v=" + encodeURIComponent(v || "")); }
function $(id) { return document.getElementById(id); }
function mostrar(id, sim) { $(id).hidden = !sim; }
