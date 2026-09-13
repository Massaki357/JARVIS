from google.genai import types

from . import acoes


_FUNCTION_DECLARATIONS = [
    types.FunctionDeclaration(
        name="rolar_pagina",
        description=(
            "Rola a janela ou página que estiver sob o ponteiro "
            "do mouse. Use somente quando o usuário pedir "
            "claramente para rolar para cima ou para baixo. "
            "Use quantidade 3 como padrão, 2 para um pouco "
            "e 5 quando pedir mais."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "direcao": types.Schema(
                    type="STRING",
                    description="Direção: cima ou baixo.",
                ),
                "quantidade": types.Schema(
                    type="INTEGER",
                    description="Quantidade de 1 a 10 passos.",
                ),
            },
            required=["direcao", "quantidade"],
        ),
    ),

    types.FunctionDeclaration(
        name="clicar_mouse",
        description=(
            "Executa um clique esquerdo na posição atual "
            "do ponteiro. Use somente quando solicitado."
        ),
    ),

    types.FunctionDeclaration(
        name="duplo_clique_mouse",
        description=(
            "Executa um clique duplo na posição atual "
            "do ponteiro. Use somente quando solicitado."
        ),
    ),

    types.FunctionDeclaration(
        name="clique_direito_mouse",
        description=(
            "Executa um clique com o botão direito na posição "
            "atual do ponteiro. Use somente quando solicitado."
        ),
    ),
]


def obter_function_declarations():
    return list(_FUNCTION_DECLARATIONS)


def despachar(nome_funcao, argumentos):
    argumentos = argumentos or {}

    if nome_funcao == "rolar_pagina":
        return acoes.rolar_pagina(
            argumentos.get("direcao", ""),
            argumentos.get("quantidade", 3),
        )

    if nome_funcao == "clicar_mouse":
        return acoes.clicar_mouse()

    if nome_funcao == "duplo_clique_mouse":
        return acoes.duplo_clique_mouse()

    if nome_funcao == "clique_direito_mouse":
        return acoes.clique_direito_mouse()

    return None
