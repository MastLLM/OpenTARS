"""CU1: type_in_element sem 'name' (o modelo esquece) devolve o que falta e os campos da janela, sem tentar escrever."""
from _util import carregar_tars

tars = carregar_tars()
tars._janela_acessivel = lambda janela: ({"titulo": "Sign up", "pid": 1}, None)
tars.acess.preencher = lambda alvo, nome, texto: {"sucesso": False, "achou": False, "campos": ["Name", "Email", "City"]}

r = tars.executar_ferramenta("type_in_element", {"text": "Maria", "window": "Sign up"})
assert not r["sucesso"] and "'name' is missing" in r["mensagem"] and "name='Name'" in r["mensagem"], r

r = tars.executar_ferramenta("type_in_element", {"name": "Nope", "text": "Maria", "window": "Sign up"})
assert not r["sucesso"] and "No text field named 'Nope'" in r["mensagem"], r
print("test_escrever_sem_nome OK")
