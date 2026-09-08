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
from jarvis.nucleo import prompts

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

    # Import adiado: só quem realmente usa este provedor paga o custo
    # de carregar o SDK.
    from google import genai
    from google.genai import types

    try:
        # TIMEOUT OBRIGATÓRIO (em milissegundos). O SDK não tem um por
        # padrão, e esta chamada é feita de dentro de um
        # asyncio.to_thread sem wait_for por fora — uma chamada
        # pendurada travaria o turno para sempre sem levantar nada.
        cliente = genai.Client(
            api_key=config.GEMINI_API_KEY,
            http_options=types.HttpOptions(
                timeout=config.TIMEOUT_SEGUNDOS * 1000,
            ),
        )

        resposta = cliente.models.generate_content(
            model=config.MODELO_GEMINI,
            contents=[
                types.Part.from_bytes(
                    data=imagem_bytes,
                    mime_type="image/jpeg",
                ),
                pergunta or prompts.VISAO_PERGUNTA_PADRAO,
            ],
            config=types.GenerateContentConfig(
                # Sem isto o SDK imprime um aviso sobre chamada
                # automática de função a cada chamada — ruído puro no
                # painel de console, já que aqui não há ferramenta
                # nenhuma envolvida.
                automatic_function_calling=(
                    types.AutomaticFunctionCallingConfig(disable=True)
                ),
            ),
        )

        texto = (resposta.text or "").strip()

    except Exception as erro:
        # O SDK levanta tipos próprios (ServerError, ClientError...);
        # capturar amplo é o certo aqui, porque esta função nunca pode
        # deixar uma exceção escapar para o turno de voz.
        return False, _mensagem_indisponivel(
            f"{type(erro).__name__}: {str(erro)[:150]}"
        )

    if not texto:
        return False, _mensagem_indisponivel("a resposta voltou vazia")

    return True, texto


def _mensagem_indisponivel(motivo):
    return prompts.VISAO_INDISPONIVEL.format(
        provedor=NOME_PROVEDOR,
        motivo=motivo,
    )
