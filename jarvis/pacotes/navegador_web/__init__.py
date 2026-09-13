from google.genai import types

from . import acoes


_FUNCTION_DECLARATIONS = [
    types.FunctionDeclaration(
        name="pesquisar_no_navegador",
        description=(
            "Abre uma pesquisa no Google usando o navegador padrão. "
            "Use somente quando o usuário pedir explicitamente "
            "para abrir, mostrar ou fazer a pesquisa no navegador "
            "ou no Google. Exemplos: 'pesquise no Google', "
            "'abra no navegador', 'mostre os resultados no navegador'. "
            "Não use para perguntas que devem ser respondidas por voz, "
            "como preço do dólar, previsão, explicações ou dúvidas gerais. "
            "Não use para tocar músicas ou vídeos."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "consulta": types.Schema(
                    type="STRING",
                    description=(
                        "Texto exato que deve ser pesquisado "
                        "no Google."
                    ),
                )
            },
            required=["consulta"],
        ),
    ),

    types.FunctionDeclaration(
        name="tocar_no_youtube",
        description=(
            "Pesquisa e abre no YouTube uma música ou vídeo "
            "para reprodução no navegador padrão. Use quando "
            "o usuário pedir claramente para tocar, reproduzir, "
            "colocar ou ouvir uma música ou vídeo no YouTube. "
            "Exemplos: 'toque One do Metallica no YouTube', "
            "'reproduza Bohemian Rhapsody no YouTube'. "
            "Não use para perguntas sobre músicas nem para "
            "pesquisas comuns no Google."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "busca": types.Schema(
                    type="STRING",
                    description=(
                        "Nome da música, artista ou vídeo "
                        "que deve ser aberto no YouTube."
                    ),
                )
            },
            required=["busca"],
        ),
    ),
]


def obter_function_declarations():
    return list(_FUNCTION_DECLARATIONS)


def despachar(nome_funcao, argumentos):
    argumentos = argumentos or {}

    if nome_funcao == "pesquisar_no_navegador":
        return acoes.pesquisar_no_navegador(
            argumentos.get("consulta", "")
        )

    if nome_funcao == "tocar_no_youtube":
        return acoes.tocar_no_youtube(
            argumentos.get("busca", "")
        )

    return None
