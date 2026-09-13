import json
import threading
from jarvis.caminhos import PASTA_DADOS, garantir_pasta

PASTA_CACHE = garantir_pasta(PASTA_DADOS)
ARQUIVO_CACHE = PASTA_CACHE / "discord_contatos.json"

_LOCK = threading.Lock()


def _criar_arquivo_se_necessario():
    PASTA_CACHE.mkdir(
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
    PASTA_CACHE.mkdir(
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


def obter(nome_normalizado):
    with _LOCK:
        dados = _carregar_dados()

    return dados.get(nome_normalizado)


def salvar(nome_normalizado, contato_info):
    with _LOCK:
        dados = _carregar_dados()

        dados[nome_normalizado] = contato_info

        _salvar_dados(dados)
