from google.genai import types

from . import cliente_visao

_FUNCTION_DECLARATIONS = [
    types.FunctionDeclaration(
        name="descrever_tela",
        description=(
            "Olha a tela do computador e descreve o que está nela, "
            "respondendo à pergunta do usuário sobre o que aparece "
            "ali. Use quando o usuário pedir para você ver, olhar, "
            "conferir ou ler a tela dele. A captura é feita "
            "automaticamente no monitor onde o cursor está; você só "
            "precisa informar a pergunta."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "pergunta": types.Schema(
                    type="STRING",
                    description=(
                        "A pergunta exata que o usuário fez sobre a "
                        "tela (ex: 'que erro apareceu aqui'), para a "
                        "descrição responder especificamente a ela. "
                        "Se ele só pediu para olhar, deixe vazio."
                    ),
                ),
            },
            required=[],
        ),
    ),
    types.FunctionDeclaration(
        name="descrever_camera",
        description=(
            "Olha pela webcam e descreve o que está sendo mostrado, "
            "respondendo à pergunta do usuário. Use quando ele pedir "
            "para ver, olhar ou conferir a câmera. Para identificar "
            "uma planta use identificar_planta, e para uma segunda "
            "opinião sobre a identificação de um objeto use "
            "consultar_segunda_opiniao_visual. A foto é tirada "
            "automaticamente; você só precisa informar a pergunta."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "pergunta": types.Schema(
                    type="STRING",
                    description=(
                        "A pergunta exata que o usuário fez sobre a "
                        "imagem da câmera (ex: 'quantos dedos estou "
                        "mostrando'). Se ele só pediu para olhar, "
                        "deixe vazio."
                    ),
                ),
            },
            required=[],
        ),
    ),
]

_ORIGENS = {
    "descrever_tela": "tela",
    "descrever_camera": "câmera",
}


def obter_function_declarations():
    return list(_FUNCTION_DECLARATIONS)


def despachar(nome_funcao, argumentos):
    argumentos = argumentos or {}

    if nome_funcao not in _ORIGENS:
        return None

    return descrever(
        _ORIGENS[nome_funcao],
        argumentos.get("imagem_bytes"),
        argumentos.get("pergunta", ""),
    )


def descrever(origem, imagem_bytes, pergunta):
    sucesso, texto = cliente_visao.descrever(
        imagem_bytes,
        pergunta,
        origem,
    )

    return texto
