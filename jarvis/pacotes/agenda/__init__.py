from google.genai import types

from . import acoes


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
