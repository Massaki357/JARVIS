from google.genai import types

from . import acoes


_FUNCTION_DECLARATIONS = [
    types.FunctionDeclaration(
        name="abrir_aplicativo",
        description=(
            "Abre aplicativos, programas ou locais permitidos "
            "do Windows, como meu computador, explorador de "
            "arquivos, navegador, Google, Chrome, Edge, "
            "antivírus, Windows Defender, configurações ou "
            "painel de controle."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "nome": types.Schema(
                    type="STRING",
                    description=(
                        "Nome do aplicativo, programa "
                        "ou local a abrir."
                    ),
                )
            },
            required=["nome"],
        ),
    ),
]


def obter_function_declarations():
    return list(_FUNCTION_DECLARATIONS)


def despachar(nome_funcao, argumentos):
    argumentos = argumentos or {}

    if nome_funcao == "abrir_aplicativo":
        return acoes.abrir_aplicativo(
            argumentos.get("nome", "")
        )

    return None
