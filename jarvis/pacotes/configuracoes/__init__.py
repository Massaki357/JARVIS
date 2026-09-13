from google.genai import types

from jarvis.nucleo.sinalizador import obter_sinalizador


_FUNCTION_DECLARATIONS = [
    types.FunctionDeclaration(
        name="abrir_configuracoes",
        description=(
            "Abre a tela de configurações do jarvis, onde o usuário "
            "pode ver e editar as variáveis do arquivo .env (chaves "
            "de API, credenciais, tokens, etc). Use somente quando o "
            "usuário pedir explicitamente para abrir as "
            "configurações, os ajustes, ou editar o .env (ex: 'abre "
            "as configurações', 'quero editar minhas chaves de "
            "API'). Nunca use espontaneamente."
        ),
    ),
]


def obter_function_declarations():
    return list(_FUNCTION_DECLARATIONS)


def despachar(nome_funcao, argumentos):
    if nome_funcao == "abrir_configuracoes":
        return abrir_configuracoes()

    return None


def abrir_configuracoes():
    obter_sinalizador().solicitou_abrir_configuracoes.emit()

    return "Abrindo a tela de configurações."
