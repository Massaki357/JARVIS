from google.genai import types

from . import config
from . import gemini_vision_client
from . import mistral_vision_client


_FUNCTION_DECLARATIONS = [
    types.FunctionDeclaration(
        name="consultar_segunda_opiniao_visual",
        description=(
            "Consulta um segundo modelo de visão, de um provedor "
            "diferente do seu, para confirmar ou contestar a "
            "identificação de um objeto genérico mostrado na "
            "câmera. Reservado especificamente para perguntas de "
            "IDENTIFICAÇÃO ('o que é isso', 'que ferramenta é "
            "essa', 'que modelo é esse') — não para perguntas sobre "
            "cor, contagem ou descrição geral da câmera, que você "
            "responde sozinho, sem chamar esta função. Nunca use "
            "para planta ou flor — nesse caso use identificar_planta "
            "em vez desta. A imagem é capturada automaticamente; "
            "você só precisa informar a pergunta exata que o "
            "usuário fez."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "pergunta": types.Schema(
                    type="STRING",
                    description=(
                        "A pergunta exata que o usuário fez sobre a "
                        "imagem (ex: 'que ferramenta é essa'), para "
                        "o outro modelo responder especificamente a "
                        "ela — não uma paráfrase genérica."
                    ),
                ),
            },
            required=[
                "pergunta",
            ],
        ),
    ),
]


def obter_function_declarations():
    return list(_FUNCTION_DECLARATIONS)


def despachar(nome_funcao, argumentos):
    argumentos = argumentos or {}

    if nome_funcao == "consultar_segunda_opiniao_visual":
        return consultar_segunda_opiniao_visual(
            argumentos.get("imagem_bytes"),
            argumentos.get("pergunta", ""),
        )

    return None


_CLIENTES = {
    "gemini": gemini_vision_client,
    "mistral": mistral_vision_client,
}


def consultar_segunda_opiniao_visual(imagem_bytes, pergunta):
    cliente = _CLIENTES.get(config.provedor_visao()) or _CLIENTES["gemini"]

    sucesso, resultado = cliente.consultar(imagem_bytes, pergunta)

    if not sucesso:
        return resultado

    return (
        f"Segunda opinião ({cliente.NOME_PROVEDOR}) sobre "
        f"'{pergunta}': {resultado}"
    )
