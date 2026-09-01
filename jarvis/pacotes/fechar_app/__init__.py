# Usado só para montar a FunctionDeclaration deste pacote — mesmo
# padrão dos demais pacotes isolados (ver docs/INTEGRATION.md).
from google.genai import types

from . import fechador, processos

# ============================================================
# Contrato padrão do projeto (ver docs/INTEGRATION.md): todo pacote de
# tools expõe obter_function_declarations() e despachar().
#
# Independente de admin_terminal (comandos de manutenção com
# privilégio elevado) e de rede_jarvis (listar_processos remoto, só
# leitura) — este pacote fecha um app já aberto NESTA máquina, sem
# privilégio elevado, resolvendo o nome contra processos que já estão
# rodando de verdade (nunca um nome/comando arbitrário vindo direto
# da fala).
# ============================================================

_FUNCTION_DECLARATIONS = [
    types.FunctionDeclaration(
        name="fechar_app",
        description=(
            "Fecha um aplicativo/programa que já está aberto nesta "
            "máquina, pelo nome (ex: 'fecha o Spotify', 'feche o "
            "navegador'). Tenta fechar do jeito normal primeiro (o "
            "próprio programa pode perguntar se quer salvar antes de "
            "fechar) e só força o fechamento se ele não responder a "
            "tempo. NUNCA fecha processos do próprio Windows nem o "
            "ALFRED — nesses casos a função recusa e explica por quê. "
            "Se houver mais de uma janela do mesmo aplicativo aberta, "
            "fecha todas e informa quantas foram fechadas. Use "
            "somente quando o usuário pedir explicitamente para "
            "fechar, encerrar ou sair de um aplicativo. Se a função "
            "retornar mais de um candidato pra desambiguar, pergunte "
            "ao usuário qual deles antes de chamar de novo — nunca "
            "escolha sozinho. Se não encontrar nenhum, avise e não "
            "tente de novo sozinho."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "nome_falado": types.Schema(
                    type="STRING",
                    description=(
                        "Nome do aplicativo/programa exatamente como "
                        "o usuário falou."
                    ),
                ),
            },
            required=[
                "nome_falado",
            ],
        ),
    ),
]


def obter_function_declarations():
    return list(_FUNCTION_DECLARATIONS)


def despachar(nome_funcao, argumentos):
    argumentos = argumentos or {}

    if nome_funcao == "fechar_app":
        return fechar_app(
            argumentos.get("nome_falado", "")
        )

    return None


def fechar_app(nome_falado):
    nome_falado = (nome_falado or "").strip()

    if not nome_falado:
        return "Nenhum nome de aplicativo foi informado pra fechar."

    nome_processo, ambiguos_ou_vazio = processos.buscar_processo(
        nome_falado
    )

    if nome_processo is None:
        if ambiguos_ou_vazio:
            nomes = ", ".join(
                sorted(set(ambiguos_ou_vazio))[:8]
            )

            return (
                f"Encontrei mais de um processo parecido com "
                f"'{nome_falado}': {nomes}. Qual deles?"
            )

        return (
            f"Não encontrei nenhum aplicativo chamado "
            f"'{nome_falado}' em execução."
        )

    return fechador.fechar_processos_por_nome(nome_processo)
