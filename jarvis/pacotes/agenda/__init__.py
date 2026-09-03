"""
Agenda local persistente de compromissos.

Trazida do JARVIS COMPLETO (actions/agenda_actions.py) e reembalada no
contrato padrão de pacote isolado deste projeto — ver
docs/INTEGRATION.md. É a agenda inteira: o memoria_obsidian (memória
conversacional) não tem nada a ver com isto.

Único ajuste em acoes.py: o arquivo saiu de memory/agenda.json para
dados/agenda.json, via jarvis/caminhos.py — neste projeto nenhum
módulo grava um arquivo de estado ao lado do próprio código, e nenhum
conta ".parent" pra achar a raiz. A gravação atômica (.tmp + fsync +
Path.replace) e o threading.Lock são os originais.

Estas funções NÃO criam alarme nenhum: guardam e listam compromissos,
e só.
"""

# Usado só para montar as FunctionDeclaration deste pacote — mesmo
# padrão dos demais pacotes isolados (ver docs/INTEGRATION.md).
from google.genai import types

from . import acoes

# ============================================================
# Contrato padrão do projeto (ver docs/INTEGRATION.md): todo pacote de
# tools expõe obter_function_declarations() e despachar().
# ============================================================

_FUNCTION_DECLARATIONS = [
    types.FunctionDeclaration(
        name="criar_evento_agenda",
        description=(
            "Salva um compromisso na agenda local persistente "
            "do ALFRED. Use quando o usuário pedir para agendar, "
            "marcar ou anotar um compromisso para uma data e "
            "horário específicos. Converta a data para o formato "
            "YYYY-MM-DD HH:MM. Esta função não cria alarmes."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "titulo": types.Schema(
                    type="STRING",
                    description="Descrição curta do compromisso.",
                ),
                "data_hora": types.Schema(
                    type="STRING",
                    description=(
                        "Data e hora local no formato "
                        "YYYY-MM-DD HH:MM."
                    ),
                ),
            },
            required=[
                "titulo",
                "data_hora",
            ],
        ),
    ),

    types.FunctionDeclaration(
        name="listar_agenda",
        description=(
            "Lista os próximos compromissos salvos na agenda. "
            "Use quando o usuário perguntar o que está agendado, "
            "quais são os próximos compromissos."
        ),
    ),

    types.FunctionDeclaration(
        name="cancelar_evento_agenda",
        description=(
            "Cancela um compromisso da agenda. Use "
            "somente quando o usuário pedir claramente para cancelar. "
            "Aceita o número do compromisso ou parte do título."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "referencia": types.Schema(
                    type="STRING",
                    description=(
                        "Número ou trecho do nome do compromisso."
                    ),
                ),
            },
            required=["referencia"],
        ),
    ),
]


def obter_function_declarations():
    return list(_FUNCTION_DECLARATIONS)


def despachar(nome_funcao, argumentos):
    argumentos = argumentos or {}

    if nome_funcao == "criar_evento_agenda":
        return acoes.criar_evento_agenda(
            argumentos.get("titulo", ""),
            argumentos.get("data_hora", ""),
        )

    if nome_funcao == "listar_agenda":
        return acoes.listar_agenda()

    if nome_funcao == "cancelar_evento_agenda":
        return acoes.cancelar_evento_agenda(
            argumentos.get("referencia", "")
        )

    return None
