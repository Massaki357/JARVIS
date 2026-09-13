from jarvis.nucleo import prompts
from jarvis.servicos import agentes

from . import config

_PROVEDORES = {
    "gemini": ("GEMINI_API_KEY", "MODELO_GEMINI"),
    "mistral": ("MISTRAL_API_KEY", "MODELO_MISTRAL"),
}


def descrever(imagem_bytes, pergunta, origem):
    if not imagem_bytes:
        return False, _falha(origem, "nenhuma imagem foi capturada")

    texto_pergunta = (pergunta or "").strip() or (
        prompts.DESCRICAO_VISUAL_PERGUNTA_PADRAO.format(origem=origem)
    )

    provedor = config.provedor_visao()

    if provedor not in _PROVEDORES:
        provedor = "gemini"

    nome_chave, nome_modelo = _PROVEDORES[provedor]
    api_key = getattr(config, nome_chave, None)

    if not api_key:
        return False, _falha(
            origem, f"a {nome_chave} não está configurada"
        )

    resposta = agentes.executar(
        agentes.PedidoAgente(
            provedor=provedor,
            modelo=getattr(config, nome_modelo),
            api_key=api_key,
            texto=texto_pergunta,
            imagem=imagem_bytes,
            instrucao_sistema=prompts.DESCRICAO_VISUAL_INSTRUCAO,
            timeout=config.TIMEOUT_SEGUNDOS,
        ),
        agentes.PoliticaRepeticao(rotulo="descricao_visual"),
    )

    if not resposta.sucesso:
        return False, _falha(origem, _motivo_do_erro(resposta, provedor))

    if not resposta.texto:
        return False, _falha(origem, "a descrição voltou vazia")

    return True, resposta.texto


def _motivo_do_erro(resposta, provedor):
    if resposta.tipo_erro == agentes.erros.TEMPO:
        return (
            f"o modelo de visão demorou mais de "
            f"{config.TIMEOUT_SEGUNDOS}s"
        )

    if resposta.tipo_erro == agentes.erros.AUTENTICACAO:
        return f"a chave de API da {provedor} é inválida ou expirou"

    if resposta.tipo_erro == agentes.erros.LIMITE:
        limite = resposta.cabecalho_do_erro("x-ratelimit-limit-req-minute")

        if limite is not None and str(limite).strip() in ("0", "0.0"):
            return (
                f"a chave da {provedor} está sem cota disponível "
                "(limite por minuto zerado, não é espera passageira)"
            )

        return (
            f"o limite de requisições por minuto da {provedor} foi "
            "atingido"
        )

    return f"o modelo de visão falhou ({resposta.erro})"


def _falha(origem, motivo):
    return prompts.DESCRICAO_VISUAL_INDISPONIVEL.format(
        origem=origem,
        motivo=motivo,
    )
