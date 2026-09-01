# Cache técnico de resolução nome falado -> app (AppID), separado da
# memória conversacional do jarvis (jarvis/servicos/memoria/gerenciador.py) — este
# arquivo não guarda nada que o usuário pediu pra "lembrar", só
# evita repetir a busca no Get-StartApps pra um app já resolvido
# antes. Escrita atômica (.tmp + replace) e lock de thread seguem a
# mesma técnica já validada em jarvis/servicos/memoria/gerenciador.py.
import json
import threading
from jarvis.caminhos import PASTA_DADOS, garantir_pasta

PASTA_CACHE = garantir_pasta(PASTA_DADOS)
ARQUIVO_CACHE = PASTA_CACHE / "apps_conhecidos.json"

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


# Grava usando um arquivo temporário + replace, pra nunca deixar o
# cache pela metade se o processo for interrompido no meio da
# escrita.
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


# Retorna {"nome", "app_id"} se nome_normalizado já foi resolvido e
# salvo antes, ou None se não estiver no cache.
def obter(nome_normalizado):
    with _LOCK:
        dados = _carregar_dados()

    return dados.get(nome_normalizado)


# Salva a resolução de nome_normalizado -> app_info
# ({"nome", "app_id"}). Só deve ser chamado depois de o app ter
# sido aberto com sucesso — quem chama (jarvis/pacotes/abrir_app_local/__init__.py)
# é responsável por essa ordem, este módulo só grava o que recebe.
def salvar(nome_normalizado, app_info):
    with _LOCK:
        dados = _carregar_dados()

        dados[nome_normalizado] = app_info

        _salvar_dados(dados)
