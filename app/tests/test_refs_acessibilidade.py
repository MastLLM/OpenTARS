# Refs numéricas de list_elements: #N e [N] resolvem, "3" continua nome, ref velha não acerta.
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tars_acessibilidade as a

itens = [(0, "botão", "Salvar", None, "clicavel"), (1, "botão", "Salvar", None, "clicavel"),
         (2, "botão", "Abrir", None, "clicavel")]
a._REFS[:] = [("Salvar", "botão", 1), ("Salvar", "botão", 2), ("Abrir", "botão", 1)]
assert a._RE_REF.fullmatch("#2") and a._RE_REF.fullmatch("[3]") and a._RE_REF.fullmatch(" # 1 ")
assert not a._RE_REF.fullmatch("3") and not a._RE_REF.fullmatch("Salvar")
assert a._por_ref(itens, 2) == itens[1]
assert a._por_ref(itens, 9) is None
print("OK refs")

# Dica entre janelas: _dica_outras_janelas (nucleo/elementos.py) com janelas falsas.
import ast, types
_src = open(os.path.join(os.path.dirname(__file__), "..", "nucleo", "elementos.py"), encoding="utf-8").read()
_fn = next(n for n in ast.parse(_src).body if isinstance(n, ast.FunctionDef) and n.name == "_dica_outras_janelas")
_ns = {"acess": types.SimpleNamespace(
    janelas=lambda: [{"titulo": "Teste"}, {"titulo": "Calculadora"}, {"titulo": "Notas"}],
    _itens=lambda j: j["titulo"], _achar=lambda itens, nome, papel: itens == "Notas" and nome == "Abrir")}
exec(compile(ast.Module([_fn], []), "elementos", "exec"), _ns)
dica = _ns["_dica_outras_janelas"]
assert "window='Notas'" in dica({"titulo": "Teste"}, "Abrir", None)
assert "Open windows" in dica({"titulo": "Teste"}, "Fechar", None)
print("OK dica janelas")
