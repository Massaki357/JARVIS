# Segunda opinião visual pela Mistral — usada como fonte
# independente do Gemini para identificação de objeto genérico (não
# plantas — isso é jarvis/pacotes/identificacao_planta/Pl@ntNet).
#
# A CHAMADA passa por jarvis/servicos/agentes/ (LangChain,
# langchain-mistralai). O que isso resolveu, concretamente: o formato
# da imagem. A Mistral espera o item de imagem como
# {"type": "image_url", "image_url": "<string>"} — uma STRING PLANA
# (data URI base64), NÃO o objeto {"url": ...} que a OpenAI usa. Essa
# diferença estava anotada em dois arquivos deste projeto justamente
# porque errá-la não falha de modo óbvio. Agora quem monta o formato
# de cada provedor é o LangChain, e aqui só existe "imagem=bytes".
#
# O que NÃO foi delegado: a distinção entre os dois 429 da Mistral.
# Ver _motivo_do_erro logo abaixo — é conhecimento específico desta
# API, e perdê-lo na migração teria trocado uma mensagem precisa por
# uma genérica.
from jarvis.nucleo import prompts
from jarvis.servicos import agentes

from . import config

# Nome legível do provedor, usado nas mensagens devolvidas ao cérebro.
# Existe desde que a segunda opinião deixou de ser sempre a Mistral —
# ver gemini_vision_client.py e config.provedor_visao().
NOME_PROVEDOR = "Mistral"


# Envia a imagem (bytes JPEG já em memória — nunca gravada em disco)
# + a pergunta exata que o usuário fez pro modelo de visão atual da
# Mistral. Nunca lança exceção — sempre retorna (sucesso: bool,
# resultado):
#   sucesso=True  -> resultado é o texto da resposta da Mistral.
#   sucesso=False -> resultado já vem formatado como uma instrução
#                     pro Jarvis responder só com a própria visão e
#                     avisar o usuário que não conseguiu confirmar
#                     com uma segunda fonte desta vez — igual à
#                     convenção de 'segunda_opiniao' em
#                     jarvis/pacotes/delegacao_ia/roteador.py.
def consultar(imagem_bytes, pergunta):
    if not config.MISTRAL_API_KEY:
        return False, _mensagem_indisponivel(
            "MISTRAL_API_KEY não configurada no .env"
        )

    if not imagem_bytes:
        return False, _mensagem_indisponivel(
            "nenhuma imagem foi capturada da câmera"
        )

    resposta = agentes.executar(
        agentes.PedidoAgente(
            provedor="mistral",
            modelo=config.MODELO_MISTRAL_VISION,
            api_key=config.MISTRAL_API_KEY,
            texto=pergunta or prompts.VISAO_PERGUNTA_PADRAO,
            imagem=imagem_bytes,
            timeout=config.TIMEOUT_SEGUNDOS,
        ),
        agentes.PoliticaRepeticao(rotulo="identificacao_visual"),
    )

    if not resposta.sucesso:
        return False, _mensagem_indisponivel(_motivo_do_erro(resposta))

    if not resposta.texto:
        return False, _mensagem_indisponivel("a resposta voltou vazia")

    return True, resposta.texto


# Traduz a falha para o motivo que o usuário precisa ouvir.
#
# O caso que justifica esta função existir: a Mistral responde 429
# tanto para "rápido demais" quanto para "acabou a cota". Quando o
# próprio cabeçalho diz que o limite por minuto é 0, chamar isso de
# "limite por minuto" mandaria esperar por algo que não vai reabrir
# sozinho — foi exatamente o que aconteceu com a chave deste projeto.
def _motivo_do_erro(resposta):
    if resposta.tipo_erro == agentes.erros.AUTENTICACAO:
        return "chave de API da Mistral inválida ou expirada"

    if resposta.tipo_erro == agentes.erros.TEMPO:
        return "tempo esgotado ao consultar a Mistral"

    if resposta.tipo_erro == agentes.erros.LIMITE:
        limite = resposta.cabecalho_do_erro("x-ratelimit-limit-req-minute")

        if limite is not None and str(limite).strip() in ("0", "0.0"):
            return (
                "a chave da Mistral está sem cota disponível "
                "(limite por minuto zerado, não é espera passageira)"
            )

        return (
            "limite de requisições por minuto da Mistral atingido "
            "(comum no tier gratuito)"
        )

    return resposta.erro


def _mensagem_indisponivel(motivo):
    return prompts.VISAO_INDISPONIVEL.format(
        provedor=NOME_PROVEDOR,
        motivo=motivo,
    )
