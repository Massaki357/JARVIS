# Usado só para montar a FunctionDeclaration deste pacote — mesmo
# padrão dos demais pacotes isolados (ver INTEGRATION.md).
from google.genai import types

from . import buscador, cache, executor
from .buscador import _normalizar

# ============================================================
# Contrato padrão do projeto (ver INTEGRATION.md): todo pacote de
# tools expõe obter_function_declarations() e despachar().
#
# Independente de admin_terminal (privilégio elevado, whitelist fixa
# de manutenção) e de rede_jarvis (abrir_app REMOTO, outra máquina
# executando a pedido) — este pacote é só busca+abertura LOCAL,
# comum, sem privilégio elevado e sem lista fixa de nomes. Nenhum
# cache, lógica ou estado é compartilhado com nenhum dos dois.
# ============================================================

_FUNCTION_DECLARATIONS = [
    types.FunctionDeclaration(
        name="abrir_app_local",
        description=(
            "Abre um aplicativo já instalado nesta máquina, pelo "
            "nome, sem privilégio de administrador (ex: 'abre o "
            "Spotify', 'abre o bloco de notas'). A busca é "
            "automática entre os apps que já aparecem na busca do "
            "menu Iniciar do Windows — nunca abre um caminho ou "
            "comando arbitrário que não esteja nessa lista. Use "
            "somente quando o usuário pedir explicitamente para "
            "abrir, iniciar ou executar um aplicativo local. Se a "
            "função retornar mais de um candidato, pergunte ao "
            "usuário qual deles antes de chamar de novo — nunca "
            "escolha sozinho. Se não encontrar nenhum, avise e não "
            "tente de novo sozinho."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "nome": types.Schema(
                    type="STRING",
                    description=(
                        "Nome do aplicativo exatamente como o "
                        "usuário falou."
                    ),
                ),
            },
            required=[
                "nome",
            ],
        ),
    ),
]


def obter_function_declarations():
    return list(_FUNCTION_DECLARATIONS)


def despachar(nome_funcao, argumentos):
    argumentos = argumentos or {}

    if nome_funcao == "abrir_app_local":
        return abrir_app_local(
            argumentos.get("nome", "")
        )

    return None


# Fluxo: cache primeiro (rápido, sem bater no Get-StartApps de
# novo) -> busca -> abertura. Só grava no cache depois de abrir com
# sucesso — uma busca que "achou" mas nunca chegou a abrir não é
# cacheada, pra não fixar um resultado nunca confirmado na prática.
def abrir_app_local(nome_falado):
    nome_falado = (nome_falado or "").strip()

    if not nome_falado:
        return "Nenhum nome de aplicativo foi informado."

    nome_normalizado = _normalizar(nome_falado)

    app_do_cache = cache.obter(nome_normalizado)

    if app_do_cache:
        sucesso, mensagem = executor.abrir(app_do_cache)

        if sucesso:
            return mensagem

        # O cache pode ter ficado desatualizado (app desinstalado,
        # AppID mudou) — não trava nisso, cai pra uma busca nova.
        print(
            f"[abrir_app_local] Falha ao abrir '{nome_falado}' pelo "
            f"cache ({mensagem}) — buscando de novo."
        )

    candidato, ambiguos_ou_vazio = buscador.buscar_app(nome_falado)

    if candidato is None:
        if ambiguos_ou_vazio:
            nomes = ", ".join(
                app["nome"] for app in ambiguos_ou_vazio[:8]
            )

            return (
                f"Encontrei mais de um aplicativo parecido com "
                f"'{nome_falado}': {nomes}. Qual deles?"
            )

        return (
            f"Não encontrei nenhum aplicativo chamado "
            f"'{nome_falado}' instalado."
        )

    sucesso, mensagem = executor.abrir(candidato)

    if sucesso:
        cache.salvar(nome_normalizado, candidato)

    return mensagem
