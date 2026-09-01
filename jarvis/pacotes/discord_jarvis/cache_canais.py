# Cache técnico de resolução nome falado -> canal do Discord (ID +
# nome), separado do cache de contatos (jarvis/pacotes/discord_jarvis/
# cache_contatos.py) — arquivo próprio, mesma técnica de escrita
# segura (arquivo temporário + replace, lock de thread) usada em
# jarvis/servicos/memoria/gerenciador.py e reaproveitada em todo o resto do
# projeto, copiada aqui de propósito (cada cache deste projeto é um
# arquivo independente, sem compartilhar lógica entre si).
import json
import threading
from jarvis.caminhos import PASTA_DADOS, garantir_pasta

PASTA_CACHE = garantir_pasta(PASTA_DADOS)
ARQUIVO_CACHE = PASTA_CACHE / "discord_canais.json"

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


# Retorna {"id", "nome"} se nome_normalizado já foi resolvido e
# salvo antes, ou None se não estiver no cache.
def obter(nome_normalizado):
    with _LOCK:
        dados = _carregar_dados()

    return dados.get(nome_normalizado)


# Retorna todos os canais já conhecidos (dict nome_normalizado ->
# {"id", "nome"}) — usado só pra decidir se existe exatamente UM
# canal conhecido, quando o usuário pede pra enviar mensagem sem
# especificar qual (ver jarvis/pacotes/discord_jarvis/__init__.py).
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
