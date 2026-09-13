from google.genai import types

from jarvis.servicos.visao.localizador_clique import (
    localizar_elemento_na_tela,
)

from jarvis.pacotes.controle_mouse import acoes as acoes_mouse


_FUNCTION_DECLARATIONS = [
    types.FunctionDeclaration(
        name="clicar_elemento_visual",
        description=(
            "Captura a tela atual, localiza visualmente um elemento "
            "descrito pelo usuário, move o mouse até o centro do alvo "
            "e executa um clique esquerdo. Use somente quando o usuário "
            "pedir claramente para clicar em algo identificado por texto, "
            "posição, cor, ícone ou contexto, como 'clique em Continuar', "
            "'clique no primeiro resultado' ou 'clique no botão vermelho'. "
            "Não use para exclusões, compras, pagamentos, instalações, "
            "ações administrativas ou confirmações sensíveis. "
            "Execute uma única vez por solicitação e permaneça em silêncio."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "alvo": types.Schema(
                    type="STRING",
                    description=(
                        "Descrição objetiva do elemento visível "
                        "que deve receber o clique."
                    ),
                )
            },
            required=["alvo"],
        ),
    ),
]


def obter_function_declarations():
    return list(_FUNCTION_DECLARATIONS)


def despachar(nome_funcao, argumentos):
    argumentos = argumentos or {}

    if nome_funcao != "clicar_elemento_visual":
        return None

    alvo = argumentos.get("alvo", "")

    try:
        localizacao = localizar_elemento_na_tela(alvo)

    except Exception as erro:
        return (
            "Não consegui analisar a tela para localizar esse "
            f"elemento ({type(erro).__name__}). Nenhum clique foi "
            "executado."
        )

    if not localizacao.get("sucesso"):
        return localizacao.get(
            "mensagem",
            "Não consegui localizar esse elemento. Nenhum clique "
            "foi executado.",
        )

    resultado_clique = acoes_mouse.mover_e_clicar(
        localizacao["x"],
        localizacao["y"],
    )

    return (
        f"{resultado_clique} Elemento: "
        f"{localizacao.get('descricao', alvo)}."
    )
