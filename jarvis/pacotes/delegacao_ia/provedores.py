from jarvis.servicos import agentes

from . import config


def _consultar(
    provedor,
    modelo,
    api_key,
    nome_da_chave,
    prompt,
    json_esperado=False,
    timeout=None,
):
    if not api_key:
        return False, f"{nome_da_chave} não configurada no .env."

    resposta = agentes.executar(
        agentes.PedidoAgente(
            provedor=provedor,
            modelo=modelo,
            api_key=api_key,
            texto=prompt,
            json_esperado=json_esperado,
            timeout=timeout or config.TIMEOUT_SEGUNDOS,
        ),
        agentes.PoliticaRepeticao(rotulo="delegacao_ia"),
    )

    if not resposta.sucesso:
        return False, f"Falha na chamada ao provedor: {resposta.erro}"

    if not resposta.texto:
        return False, "O provedor devolveu uma resposta vazia."

    return True, resposta.texto


def consultar_groq(prompt, json_esperado=False, timeout=None):
    return _consultar(
        "groq",
        config.MODELO_GROQ,
        config.GROQ_API_KEY,
        "GROQ_API_KEY",
        prompt,
        json_esperado=json_esperado,
        timeout=timeout,
    )


def consultar_cerebras(prompt, json_esperado=False, timeout=None):
    return _consultar(
        "cerebras",
        config.MODELO_CEREBRAS,
        config.CEREBRAS_API_KEY,
        "CEREBRAS_API_KEY",
        prompt,
        json_esperado=json_esperado,
        timeout=timeout,
    )


def consultar_openai(prompt, json_esperado=False, timeout=None):
    return _consultar(
        "openai",
        config.MODELO_OPENAI,
        config.OPENAI_API_KEY,
        "OPENAI_API_KEY",
        prompt,
        json_esperado=json_esperado,
        timeout=timeout,
    )


def consultar_gemini(prompt, json_esperado=False, timeout=None):
    return _consultar(
        "gemini",
        config.MODELO_GEMINI,
        config.GEMINI_API_KEY,
        "GEMINI_API_KEY",
        prompt,
        json_esperado=json_esperado,
        timeout=timeout,
    )
