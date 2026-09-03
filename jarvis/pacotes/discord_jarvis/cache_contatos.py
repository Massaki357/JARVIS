# Cache técnico de resolução nome falado -> contato do Discord
# (user_id + nome de exibição), separado da memória conversacional
# do jarvis — mesma técnica de escrita segura já validada em
# jarvis/servicos/memoria/gerenciador.py e reaproveitada em
# jarvis/servicos/memoria/gerenciador.py (arquivo temporário + replace, lock de
# thread), copiada aqui de propósito: cada pacote isolado mantém sua
# própria cópia, sem compartilhar arquivo nem lógica com
# memória conversacional.
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


# Retorna {"id", "nome_exibicao"} se nome_normalizado já foi
# resolvido e salvo antes, ou None se não estiver no cache.
def obter(nome_normalizado):
    with _LOCK:
        dados = _carregar_dados()

    return dados.get(nome_normalizado)


# Salva a resolução de nome_normalizado -> contato_info
# ({"id", "nome_exibicao"}). Só deve ser chamado depois de a DM ter
# sido enviada com sucesso — quem chama (jarvis/pacotes/discord_jarvis/__init__.py)
# é responsável por essa ordem, este módulo só grava o que recebe.
def salvar(nome_normalizado, contato_info):
    with _LOCK:
        dados = _carregar_dados()

        dados[nome_normalizado] = contato_info

        _salvar_dados(dados)
