"""Os motores que a pessoa escolhe em Configurações > Avançado (5.3.5): o llama.cpp (padrão), o Ollama e o Colibri.

Cada motor tem a sua biblioteca de modelos e o seletor só mostra o que está baixado no motor em uso, porque o app pergunta
ao endereço do motor ativo (/api/tags). O llama.cpp e o Colibri ficam atrás do proxy com cara de Ollama de
tars_motor_local (portas 11435 e 11436); o Ollama responde sozinho na 11434. O binário de cada motor vem da Release oficial,
em versão fixa e com o SHA-256 conferido, para a pasta do app (sem sudo). Se o motor já existe no sistema, usa o do sistema.
"""

import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path

import tars_motor
import tars_motor_local as ml
import tars_plataforma as plataforma

OLLAMA_URL = "http://127.0.0.1:11434"
OLLAMA_VERSAO = "v0.40.17"
COLIBRI_VERSAO = "v2.1.0"
PACOTES = {   # (motor, sistema, máquina): (arquivo, sha256, tamanho aproximado em GB)
    ("ollama", "linux", "x86_64"): ("ollama-linux-amd64.tar.zst", "1df9d6228bac5a22e420b242708c0d10e5b886db97bab99d446a41760f4e79af", 1.5),
    ("ollama", "linux", "arm64"): ("ollama-linux-arm64.tar.zst", "0ec632480057cef6300459d1fa7dbbb3fc188b9a7d56cd0b0a72d05927d90ecc", 1.6),
    ("ollama", "macos", "arm64"): ("ollama-darwin.tgz", "4b9db20d077c5a1e52fb4a6f2e6791f76ae945fd07c9b1a5647c82e927826653", 0.19),
    ("ollama", "macos", "x86_64"): ("ollama-darwin.tgz", "4b9db20d077c5a1e52fb4a6f2e6791f76ae945fd07c9b1a5647c82e927826653", 0.19),
    ("ollama", "windows", "x86_64"): ("ollama-windows-amd64.zip", "3dd80f6e3a9699f2eadf4ac418f00529cee594df9557541806eda1f1f3f5588a", 1.6),
    ("colibri", "linux", "x86_64"): ("colibri-v2.1.0-linux-x86_64.tar.gz", "d54b4c57c12417fc9e784b649249ac1aa3480eec44ece2777d4cbc639a25e66a", 0.014),
    ("colibri", "macos", "arm64"): ("colibri-v2.1.0-macos-arm64.tar.gz", "58320c9d92f84873820ced439c5dfe30afec64ebfc5ae7255ed8f34414d9e202", 0.004),
    ("colibri", "windows", "x86_64"): ("colibri-v2.1.0-windows-x86_64.zip", "195ee0be129d563789f1ade2383e023bde5519230d6fb508516e63767ee85465", 0.018),
}
_URLS = {"ollama": f"https://github.com/ollama/ollama/releases/download/{OLLAMA_VERSAO}/",
         "colibri": f"https://github.com/JustVugg/colibri/releases/download/{COLIBRI_VERSAO}/"}


def pasta(motor):
    return ml.pasta() / motor


def pacote(motor):
    """(arquivo, sha256, GB) da Release deste motor para esta máquina, ou None se não há."""
    return PACOTES.get((motor, *ml.sistema_e_maquina()))


def binario(motor):
    """O executável do motor: o da pasta do app, senão o do sistema. None se não há."""
    if motor == "llamacpp":
        return ml.binario()
    nome = {"ollama": "ollama", "colibri": "coli"}[motor]
    for achado in sorted(pasta(motor).glob(f"**/{nome}.exe" if plataforma.sistema() == "windows" and motor == "ollama" else f"**/{nome}")):
        if achado.is_file():
            return achado
    sistema = shutil.which(nome)
    return Path(sistema) if sistema else None


def _python():
    """O coli é um script Python só com a biblioteca padrão: roda no Python do app (no app empacotado, no do sistema)."""
    return shutil.which("python3") or shutil.which("python") if getattr(sys, "frozen", False) else sys.executable


def comando_colibri(*args):
    coli = binario("colibri")
    if coli is None:
        raise ValueError("Colibri is not installed")
    return [_python(), str(coli), *args]


def instalar(motor, ao_progresso=None):
    """Baixa a Release do motor, confere o SHA-256 e extrai na pasta do app. Devolve o executável."""
    if motor == "llamacpp":
        return ml.instalar_binario(ao_progresso)
    ficha = pacote(motor)
    if ficha is None:
        raise ValueError(f"no {motor} build for this computer")
    arquivo, sha, _gb = ficha
    baixado = ml.baixar(_URLS[motor] + arquivo, ml.pasta() / "baixados" / arquivo, sha, ao_progresso)
    destino, temporario = pasta(motor), pasta(motor).with_name(motor + ".novo")
    shutil.rmtree(temporario, ignore_errors=True)
    temporario.mkdir(parents=True)
    filtro = {"filter": "data"} if hasattr(tarfile, "data_filter") else {}
    if arquivo.endswith(".zip"):
        with zipfile.ZipFile(baixado) as z:
            z.extractall(temporario)
    elif arquivo.endswith(".zst"):
        # shortcut: o Python 3.12 não lê zstd; usa o zstd do sistema (vem na maioria dos Linux). Trocar por compression.zstd no 3.14
        if not shutil.which("zstd"):
            raise ValueError("zstd not found (install the zstd package)")
        with subprocess.Popen(["zstd", "-dc", str(baixado)], stdout=subprocess.PIPE) as p, tarfile.open(fileobj=p.stdout, mode="r|") as t:
            t.extractall(temporario, **filtro)
    else:
        with tarfile.open(baixado) as t:
            t.extractall(temporario, **filtro)
    if plataforma.sistema() != "windows":
        for executavel in list(temporario.rglob("ollama")) + list(temporario.rglob("coli")) + list(temporario.rglob("colibri")):
            if executavel.is_file():
                executavel.chmod(0o755)
    shutil.rmtree(destino, ignore_errors=True)
    os.replace(temporario, destino)
    baixado.unlink(missing_ok=True)
    return binario(motor)


# ---------------------------------------------------------------- Ollama

def _ollama_responde(tempo=1.0):
    try:
        with urllib.request.urlopen(tars_motor.url("versao", OLLAMA_URL), timeout=tempo) as r:
            return r.status == 200
    except OSError:
        return False


def garantir_ollama(espera=15):
    """Deixa o Ollama de pé na 11434 (o do sistema, se já roda; senão o da pasta do app) e devolve o endereço, ou None."""
    if _ollama_responde():
        return OLLAMA_URL
    exe = binario("ollama")
    if exe is None:
        return None
    extra = {"creationflags": 0x08000000} if plataforma.sistema() == "windows" else {"start_new_session": True}
    pasta("ollama").mkdir(parents=True, exist_ok=True)
    with open(pasta("ollama") / "ollama.log", "ab") as registro:
        subprocess.Popen([str(exe), "serve"], stdin=subprocess.DEVNULL, stdout=registro, stderr=registro,
                         env=dict(os.environ, OLLAMA_HOST="127.0.0.1:11434"), **extra)
    limite = time.time() + espera
    while time.time() < limite:
        if _ollama_responde(0.5):
            return OLLAMA_URL
        time.sleep(0.3)
    return None


# ---------------------------------------------------------------- Colibri

def pasta_modelos_colibri():
    """A mesma pasta que o próprio coli usa por padrão: o que a pessoa já baixou com ele aparece no app."""
    return Path(os.environ.get("TARS_COLIBRI_MODELOS") or Path.home() / "colibri-models")


def instalados_colibri():
    raiz = pasta_modelos_colibri()
    return sorted(p.name for p in raiz.iterdir() if (p / "config.json").exists()) if raiz.is_dir() else []


def catalogo_colibri(atualizar=False):
    """O catálogo do Colibri ([{id, name, download_gb, fits, summary, ...}]), lido do próprio coli e guardado em cache."""
    cache = pasta("colibri") / "catalogo.json"
    if cache.exists() and not atualizar:
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except ValueError:
            pass
    try:
        saida = subprocess.run(comando_colibri("setup", "--list", "--all", "--json"), capture_output=True, text=True, timeout=90).stdout
        lista = [m for m in json.loads(saida) if isinstance(m, dict) and m.get("id")]
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return []
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(lista, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass                        # sem cache, lê de novo na próxima vez
    return lista


def puxar_colibri(modelo, avisar):
    """Baixa um modelo do catálogo pelo próprio coli (que retoma e confere os arquivos). Levanta OSError se falhou."""
    p = subprocess.Popen(comando_colibri("setup", "--model", modelo, "--dir", str(pasta_modelos_colibri()), "--yes", "--no-start",
                                         "--no-browser"), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for linha in p.stdout:
        if linha.strip():
            avisar({"status": linha.strip()[:200]})
    if p.wait() != 0 or modelo not in instalados_colibri():
        raise OSError(f"coli setup failed for {modelo} (code {p.returncode})")
