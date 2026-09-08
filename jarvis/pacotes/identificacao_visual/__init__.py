# Usado só para montar a FunctionDeclaration deste pacote — mesmo
# padrão dos demais pacotes isolados (ver docs/INTEGRATION.md).
from google.genai import types

from . import config
from . import gemini_vision_client
from . import mistral_vision_client

# ============================================================
# Contrato padrão do projeto (ver docs/INTEGRATION.md): todo pacote de
# tools expõe obter_function_declarations() e despachar().
#
# Mesma exceção de identificacao_planta: a imagem
# (argumentos["imagem_bytes"]) vem de uma captura de câmera feita
# pelo CLIENTE (jarvis/cerebro/gemini/cliente_live.py) antes de despachar(),
# não do Gemini. A diferença aqui é que este pacote TAMBÉM recebe um
# parâmetro real do Gemini (argumentos["pergunta"]) — a pergunta
# exata que o usuário fez, pro outro modelo responder especificamente
# a ela em vez de um prompt genérico. Ver docs/INTEGRATION.md, seção
# "identificacao_visual".
# ============================================================

_FUNCTION_DECLARATIONS = [
    types.FunctionDeclaration(
        name="consultar_segunda_opiniao_visual",
        # A descrição NÃO nomeia o provedor de propósito: quem
        # responde depende do cérebro de voz ativo (ver
        # config.provedor_visao()), e um nome fixo aqui faria o
        # modelo anunciar ao usuário uma fonte que talvez não tenha
        # sido a consultada. O nome real vai no resultado, montado em
        # consultar_segunda_opiniao_visual() a partir do cliente que
        # de fato respondeu.
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


# Se reconhecer nome_funcao, executa e retorna o resultado (sempre
# uma string, pronta para o Jarvis falar). Se não reconhecer, retorna
# None. Síncrona/bloqueante de propósito (chamada de rede ao provedor
# de visão)
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


# Cliente de cada provedor. Escolhido por config.provedor_visao(),
# que aplica a política documentada no cabeçalho de config.py: a
# variável DESCRICAO_VISUAL_PROVEDOR manda quando definida; sem ela,
# o provedor é automaticamente o OPOSTO do cérebro de voz ativo, para
# a segunda opinião nunca ser o mesmo modelo que acabou de responder.
_CLIENTES = {
    "gemini": gemini_vision_client,
    "mistral": mistral_vision_client,
}


def consultar_segunda_opiniao_visual(imagem_bytes, pergunta):
    # Resolvido a cada chamada, e não no import: assim trocar o
    # cérebro de voz (ou a variável manual) no .env vale já na próxima
    # chamada, sem reiniciar o app — provedor_visao() relê o disco,
    # mesma ideia de provedor_ativo() em jarvis/nucleo/config.py.
    # O fallback sai do PRÓPRIO mapa, não de uma referência direta ao
    # módulo: assim existe um só lugar que decide qual cliente é qual,
    # e o caminho de fallback é observável (uma referência direta
    # furava o mapa e ia para a rede sem passar por ele).
    cliente = _CLIENTES.get(config.provedor_visao()) or _CLIENTES["gemini"]

    sucesso, resultado = cliente.consultar(imagem_bytes, pergunta)

    if not sucesso:
        # resultado já vem formatado como instrução de fallback pelo
        # cliente — repassa como está.
        return resultado

    # Nomeia o provedor que de fato respondeu: dizer "Mistral" quando
    # quem respondeu foi o Gemini faria o cérebro relatar ao usuário
    # uma fonte que não foi consultada.
    return (
        f"Segunda opinião ({cliente.NOME_PROVEDOR}) sobre "
        f"'{pergunta}': {resultado}"
    )
