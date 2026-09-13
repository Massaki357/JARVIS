from jarvis.nucleo import prompts
from jarvis.servicos import agentes

from . import config

NOME_PROVEDOR = "Gemini"


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
