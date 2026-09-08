# Cliente de imagem-para-texto: recebe uma imagem já capturada (bytes
# JPEG em memória, nunca gravada em disco) e devolve a descrição em
# texto.
#
# DOIS PROVEDORES, escolhidos por config.provedor_visao():
#
#   "gemini"  (padrão) — SDK google-genai, a mesma já usada pelo
#             cérebro de voz do Gemini, com a GEMINI_API_KEY que o
#             projeto já exige para funcionar.
#   "mistral" — POST /v1/chat/completions, reaproveitando a
#             MISTRAL_API_KEY de jarvis/pacotes/identificacao_visual/.
#
# POR QUE O PADRÃO É O GEMINI, e não a Mistral (que seria o
# reaproveitamento mais óbvio, já que identificacao_visual usa visão
# da Mistral e está verificada): medido ao vivo enquanto este pacote
# era escrito, a chave da Mistral deste projeto responde 429 com
# "x-ratelimit-limit-req-minute: 0" — o limite é ZERO, não um throttle
# passageiro; a cota do tier gratuito acabou. O Gemini descreveu um
# print real de 467 KB em 5,7s na mesma hora. Entregar o padrão numa
# chave sem cota seria entregar uma ferramenta que não funciona.
#
# Trocar de provedor é uma variável no .env — nenhum código muda. Se
# a cota da Mistral voltar e você preferir tirar mais essa carga do
# Gemini, DESCRICAO_VISUAL_PROVEDOR=mistral resolve.
#
# ATENÇÃO: o padrão DESTE pacote é fixo em "gemini", diferente de
# jarvis/pacotes/identificacao_visual/, cujo padrão automático é
# sempre o provedor OPOSTO ao cérebro de voz ativo. O motivo da
# assimetria está no cabeçalho de config.py: descrever_tela/
# descrever_camera não são uma segunda opinião, são a visão primária,
# e não têm nenhuma independência a preservar.
#
# Formato do request da Mistral confirmado na documentação oficial
# antes de escrever qualquer código: o item de imagem é
# {"type": "image_url", "image_url": "<string>"} — o valor é uma
# STRING PLANA (data URI base64), NÃO um objeto {"url": ...} como a
# OpenAI usa. Errar essa forma não falha de modo óbvio.
import base64

import requests

from jarvis.nucleo import prompts

from . import config

_ENDPOINT_MISTRAL = "https://api.mistral.ai/v1/chat/completions"


# Devolve (sucesso, texto). Nunca levanta exceção — mesma convenção
# de todo pacote deste projeto.
#
# Em caso de falha, o texto já vem pronto para ser dito ao usuário:
# aqui a descrição é a resposta inteira do turno, então esconder a
# falha deixaria o assistente mudo sem explicação. É o oposto da
# convenção de identificacao_visual, onde a falha instrui o cérebro a
# responder com a própria visão — aqui não existe visão própria.
def descrever(imagem_bytes, pergunta, origem):
    if not imagem_bytes:
        return False, _falha(origem, "nenhuma imagem foi capturada")

    texto_pergunta = (pergunta or "").strip() or (
        prompts.DESCRICAO_VISUAL_PERGUNTA_PADRAO.format(origem=origem)
    )

    # Resolvido a cada chamada (nunca fixado na importação): assim
    # tanto a variável manual quanto a regra automática valem já na
    # próxima chamada, sem reiniciar o app.
    if config.provedor_visao() == "mistral":
        return _descrever_mistral(imagem_bytes, texto_pergunta, origem)

    return _descrever_gemini(imagem_bytes, texto_pergunta, origem)


# ====================================================================
# GEMINI
# ====================================================================
def _descrever_gemini(imagem_bytes, pergunta, origem):
    if not config.GEMINI_API_KEY:
        return False, _falha(origem, "a GEMINI_API_KEY não está configurada")

    # Import adiado: só quem realmente usa este provedor paga o custo
    # de carregar o SDK.
    from google import genai
    from google.genai import types

    try:
        # TIMEOUT OBRIGATÓRIO. O SDK não tem um por padrão, e esta
        # chamada roda na thread do roteamento, dentro de um
        # asyncio.to_thread que também não tem wait_for por fora — uma
        # chamada pendurada travaria o turno de voz para sempre, sem
        # levantar nada. É a mesma classe de travamento silencioso já
        # corrigida várias vezes neste projeto. Em milissegundos, que
        # é o que HttpOptions espera.
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
                pergunta,
            ],
            config=types.GenerateContentConfig(
                system_instruction=prompts.DESCRICAO_VISUAL_INSTRUCAO,
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
        return False, _falha(
            origem,
            f"o modelo de visão falhou ({type(erro).__name__}: "
            f"{str(erro)[:150]})",
        )

    if not texto:
        return False, _falha(origem, "a descrição voltou vazia")

    return True, texto


# ====================================================================
# MISTRAL
# ====================================================================
def _descrever_mistral(imagem_bytes, pergunta, origem):
    if not config.MISTRAL_API_KEY:
        return False, _falha(origem, "a MISTRAL_API_KEY não está configurada")

    imagem_base64 = base64.b64encode(imagem_bytes).decode("utf-8")

    try:
        resposta = requests.post(
            _ENDPOINT_MISTRAL,
            headers={
                "Authorization": f"Bearer {config.MISTRAL_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": config.MODELO_MISTRAL,
                "messages": [
                    {
                        "role": "system",
                        "content": prompts.DESCRICAO_VISUAL_INSTRUCAO,
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": pergunta,
                            },
                            {
                                "type": "image_url",
                                "image_url": (
                                    f"data:image/jpeg;base64,{imagem_base64}"
                                ),
                            },
                        ],
                    },
                ],
            },
            timeout=config.TIMEOUT_SEGUNDOS,
        )

    except requests.Timeout:
        return False, _falha(
            origem,
            f"o modelo de visão demorou mais de {config.TIMEOUT_SEGUNDOS}s",
        )

    except requests.RequestException as erro:
        return False, _falha(origem, f"houve uma falha de conexão ({erro})")

    if resposta.status_code == 401:
        return False, _falha(
            origem, "a chave de API da Mistral é inválida ou expirou"
        )

    if resposta.status_code == 429:
        # Distingue "acabou a cota" de "rápido demais". Quando o
        # próprio cabeçalho diz que o limite por minuto é 0, chamar
        # isso de "limite por minuto" mandaria o usuário esperar por
        # algo que não vai reabrir sozinho — foi exatamente esse tipo
        # de mensagem imprecisa que atrasou o diagnóstico do rate
        # limit da Groq.
        limite = resposta.headers.get("x-ratelimit-limit-req-minute")

        if limite is not None and limite.strip() in ("0", "0.0"):
            return False, _falha(
                origem,
                "a chave da Mistral está sem cota disponível "
                "(limite por minuto zerado, não é espera passageira)",
            )

        return False, _falha(
            origem,
            "o limite de requisições por minuto da Mistral foi atingido",
        )

    if resposta.status_code != 200:
        return False, _falha(
            origem,
            f"o modelo de visão retornou um erro (HTTP "
            f"{resposta.status_code}): {_detalhe(resposta)}",
        )

    try:
        dados = resposta.json()
        texto = (dados["choices"][0]["message"]["content"] or "").strip()

    except (ValueError, KeyError, IndexError) as erro:
        return False, _falha(origem, f"a resposta veio inesperada ({erro})")

    if not texto:
        return False, _falha(origem, "a descrição voltou vazia")

    return True, texto


# Mesma lição já aprendida no roteamento hierárquico: sem o corpo da
# resposta, um erro recuperável fica indistinguível de qualquer outro.
def _detalhe(resposta):
    try:
        corpo = resposta.json()

    except ValueError:
        return (resposta.text or "").strip()[:200]

    if isinstance(corpo, dict):
        erro = corpo.get("error")

        if isinstance(erro, dict):
            return str(erro.get("message") or erro)[:200]

        if erro:
            return str(erro)[:200]

        if corpo.get("message"):
            return str(corpo["message"])[:200]

    return str(corpo)[:200]


def _falha(origem, motivo):
    return prompts.DESCRICAO_VISUAL_INDISPONIVEL.format(
        origem=origem,
        motivo=motivo,
    )
