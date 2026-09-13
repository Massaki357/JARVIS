from jarvis.nucleo import prompts
from jarvis.servicos import agentes

from . import config

NOME_PROVEDOR = "Mistral"


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
