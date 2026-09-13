# Segunda opinião visual pelo Gemini — alternativa à Mistral,
# escolhida por config.provedor_visao() (ver a política completa no
# cabeçalho de config.py).
#
# ATENÇÃO AO SENTIDO DESTA FERRAMENTA. Ela existe para ser uma fonte
# INDEPENDENTE do cérebro que está raciocinando — por isso nasceu
# usando a Mistral. Com o Gemini:
#
#   - Nos modos de voz LOCAL (jarvis/cerebro/voz_local/, alfred-server +
#     roteamento na Groq) e OPENAI (jarvis/cerebro/openai_realtime/), o Gemini
#     é de fato uma segunda fonte independente. São os casos em que
#     este provedor faz todo sentido, e é neles que a regra automática
#     escolhe justamente ele.
#   - No modo de voz GEMINI, seria o Gemini perguntando ao Gemini: a
#     resposta deixaria de ser uma segunda opinião de verdade e
#     passaria a ser a mesma família de modelo confirmando a si mesma,
#     com a instrução de cruzamento do cliente
#     (enviar_imagem_para_cruzamento) pedindo que ele concorde ou
#     discorde de si próprio. Por isso a regra automática NÃO escolhe
#     este cliente nesse modo — lá ela vai para a Mistral.
#
# Este cliente só roda no modo de voz Gemini se o usuário pedir
# explicitamente (DESCRICAO_VISUAL_PROVEDOR=gemini). Isso é uma opção
# legítima — a chave da Mistral deste projeto está com a cota zerada
# (429 com "x-ratelimit-limit-req-minute: 0"), e quem preferir uma
# segunda passada menos independente a uma falha honesta pode forçá-la
# —, mas é uma escolha consciente do usuário, não mais o padrão
# silencioso que era antes.
#
# A CHAMADA em si passa por jarvis/servicos/agentes/ (LangChain),
# igual à da Mistral aqui do lado. Antes, os dois clientes deste
# pacote mandavam a MESMA imagem para a MESMA pergunta em dois
# formatos diferentes — SDK google-genai com types.Part.from_bytes de
# um lado, POST com data URI base64 do outro — e o timeout de um era
# contado em milissegundos e o do outro em segundos. Agora é um
# PedidoAgente só, com a imagem em bytes e o timeout em segundos, nos
# dois.
from jarvis.nucleo import prompts
from jarvis.servicos import agentes

from . import config

# Nome legível do provedor, usado nas mensagens devolvidas ao cérebro.
NOME_PROVEDOR = "Gemini"


# Mesmo contrato do mistral_vision_client: nunca levanta exceção,
# sempre devolve (sucesso, resultado).
#
#   sucesso=True  -> resultado é o texto da resposta.
#   sucesso=False -> resultado já vem formatado como instrução para o
#                    cérebro responder só com a própria visão e avisar
#                    que não conseguiu confirmar com uma segunda fonte.
def consultar(imagem_bytes, pergunta):
    if not config.GEMINI_API_KEY:
        return False, _mensagem_indisponivel(
            "GEMINI_API_KEY não configurada no .env"
        )

    if not imagem_bytes:
        return False, _mensagem_indisponivel(
            "nenhuma imagem foi capturada da câmera"
        )

    resposta = agentes.executar(
        agentes.PedidoAgente(
            provedor="gemini",
            modelo=config.MODELO_GEMINI,
            api_key=config.GEMINI_API_KEY,
            texto=pergunta or prompts.VISAO_PERGUNTA_PADRAO,
            imagem=imagem_bytes,
            # TIMEOUT OBRIGATÓRIO, em SEGUNDOS. Esta chamada é feita
            # de dentro de um asyncio.to_thread sem wait_for por fora
            # — uma chamada pendurada travaria o turno para sempre sem
            # levantar nada. A camada de agentes não deixa construir
            # um modelo sem timeout, o que fecha essa porta de vez.
            timeout=config.TIMEOUT_SEGUNDOS,
        ),
        agentes.PoliticaRepeticao(rotulo="identificacao_visual"),
    )

    if not resposta.sucesso:
        return False, _mensagem_indisponivel(resposta.erro)

    if not resposta.texto:
        return False, _mensagem_indisponivel("a resposta voltou vazia")

    return True, resposta.texto


def _mensagem_indisponivel(motivo):
    return prompts.VISAO_INDISPONIVEL.format(
        provedor=NOME_PROVEDOR,
        motivo=motivo,
    )
