"""
Descreve o que está na tela ou na câmera, em texto.

É a versão portável de duas nativas do Gemini (analisar_tela e
analisar_camera) para o catálogo genérico, feita para o modo de voz
local — onde aquelas não existem, porque mandam o frame para DENTRO
da sessão via send_realtime_input(video=...) e o alfred-server só
troca áudio.

NOMES DIFERENTES DAS NATIVAS, DE PROPÓSITO: descrever_tela e
descrever_camera, não analisar_tela/analisar_camera. O despacho do
worker do Gemini percorre PACOTES_REGISTRADOS ANTES da cadeia de elif
nativa, então um pacote registrado com o nome nativo sequestraria o
comportamento do Gemini — que manda vídeo de verdade para a sessão e
tem contexto da conversa. Nomes distintos deixam os dois caminhos
coexistirem sem que um pise no outro, e também refletem a diferença
real: aqui é uma captura avulsa descrita por um modelo de visão à
parte, não visão ao vivo dentro da sessão.

Como as demais ferramentas visuais do catálogo (identificar_planta,
consultar_segunda_opiniao_visual), a imagem NÃO vem do modelo: quem
captura é o cliente, que injeta imagem_bytes em argumentos antes do
despacho — no modo local via o gancho preparar_argumentos de
jarvis/roteamento_hierarquico/roteador.py. Ver docs/INTEGRATION.md.
"""
# Usado só para montar as FunctionDeclaration — mesmo padrão dos
# demais pacotes isolados (ver docs/INTEGRATION.md).
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

# Origem legível de cada ferramenta, usada tanto na pergunta padrão
# quanto nas mensagens de falha.
_ORIGENS = {
    "descrever_tela": "tela",
    "descrever_camera": "câmera",
}


def obter_function_declarations():
    return list(_FUNCTION_DECLARATIONS)


# Se reconhecer nome_funcao, executa e devolve uma string pronta para
# ser falada. Se não reconhecer, devolve None. Síncrona/bloqueante de
# propósito (chamada de rede) — quem chama roda fora do event loop,
# igual aos outros pacotes.
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

    # Nos dois casos o texto já está pronto para ser dito: no sucesso
    # é a própria descrição, e na falha é a explicação do que deu
    # errado (ver cliente_visao._falha).
    return texto
