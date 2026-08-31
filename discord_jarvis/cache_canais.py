# Cache técnico de resolução nome falado -> canal do Discord (ID +
# nome), separado do cache de contatos (discord_jarvis/
# cache_contatos.py) — arquivo próprio, mesma técnica de escrita
# segura (arquivo temporário + replace, lock de thread) usada em
# memory/memory_manager.py e reaproveitada em todo o resto do
# projeto, copiada aqui de propósito (cada cache deste projeto é um
# arquivo independente, sem compartilhar lógica entre si).
import json
import threading
from pathlib import Path

PASTA_PACOTE = Path(__file__).resolve().parent
ARQUIVO_CACHE = PASTA_PACOTE / "canais_conhecidos.json"

_LOCK = threading.Lock()


def _criar_arquivo_se_necessario():
    PASTA_PACOTE.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not ARQUIVO_CACHE.exists():
        _salvar_dados({})


def _carregar_dados():
    _criar_arquivo_se_necessario()

    try:
        with ARQUIVO_CACHE.open(
            "r",
            encoding="utf-8",
        ) as arquivo:
            dados = json.load(arquivo)

    except (json.JSONDecodeError, OSError):
        dados = {}

    if not isinstance(dados, dict):
        dados = {}

    return dados


def _salvar_dados(dados):
    PASTA_PACOTE.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporario = ARQUIVO_CACHE.with_suffix(".tmp")

    with temporario.open(
        "w",
        encoding="utf-8",
    ) as arquivo:
        json.dump(
            dados,
            arquivo,
            ensure_ascii=False,
            indent=2,
        )

    temporario.replace(ARQUIVO_CACHE)


# Retorna {"id", "nome"} se nome_normalizado já foi resolvido e
# salvo antes, ou None se não estiver no cache.
def obter(nome_normalizado):
    with _LOCK:
        dados = _carregar_dados()

    return dados.get(nome_normalizado)


# Retorna todos os canais já conhecidos (dict nome_normalizado ->
# {"id", "nome"}) — usado só pra decidir se existe exatamente UM
# canal conhecido, quando o usuário pede pra enviar mensagem sem
# especificar qual (ver discord_jarvis/__init__.py).
def listar_todos():
    with _LOCK:
        return _carregar_dados()


# Salva a resolução de nome_normalizado -> canal_info
# ({"id", "nome"}). Só deve ser chamado depois de a mensagem ter
# sido enviada com sucesso.
def salvar(nome_normalizado, canal_info):
    with _LOCK:
        dados = _carregar_dados()

        dados[nome_normalizado] = canal_info

        _salvar_dados(dados)
