# Usado só para montar a FunctionDeclaration deste pacote — mesmo
# padrão dos demais pacotes isolados (ver INTEGRATION.md).
from google.genai import types

from . import mistral_vision_client

# ============================================================
# Contrato padrão do projeto (ver INTEGRATION.md): todo pacote de
# tools expõe obter_function_declarations() e despachar().
#
# Mesma exceção de identificacao_planta: a imagem
# (argumentos["imagem_bytes"]) vem de uma captura de câmera feita
# pelo CLIENTE (gemini/live_client_basic.py) antes de despachar(),
# não do Gemini. A diferença aqui é que este pacote TAMBÉM recebe um
# parâmetro real do Gemini (argumentos["pergunta"]) — a pergunta
# exata que o usuário fez, pra Mistral responder especificamente a
# ela em vez de um prompt genérico. Ver INTEGRATION.md, seção
# "identificacao_visual".
# ============================================================

_FUNCTION_DECLARATIONS = [
    types.FunctionDeclaration(
        name="consultar_segunda_opiniao_visual",
        description=(
            "Consulta um segundo modelo de visão (Mistral), "
            "independente do Gemini, para confirmar ou contestar a "
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
                        "a Mistral responder especificamente a ela "
                        "— não uma paráfrase genérica."
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


# Se reconhecer nome_funcao, executa e retorna o resultado (sempre
# uma string, pronta para o Jarvis falar). Se não reconhecer, retorna
# None. Síncrona/bloqueante de propósito (chamada de rede à Mistral)
# — quem chama é responsável por rodar isso fora do event loop
# (asyncio.to_thread), igual aos outros pacotes.
def despachar(nome_funcao, argumentos):
    argumentos = argumentos or {}

    if nome_funcao == "consultar_segunda_opiniao_visual":
        return consultar_segunda_opiniao_visual(
            argumentos.get("imagem_bytes"),
            argumentos.get("pergunta", ""),
        )

    return None


def consultar_segunda_opiniao_visual(imagem_bytes, pergunta):
    sucesso, resultado = mistral_vision_client.consultar(
        imagem_bytes, pergunta
    )

    if not sucesso:
        # resultado já vem formatado como instrução de fallback pelo
        # mistral_vision_client — repassa como está.
        return resultado

    return (
        f"Segunda opinião da Mistral sobre '{pergunta}': {resultado}"
    )
