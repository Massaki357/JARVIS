from jarvis.nucleo import prompts

from . import provedores

MAPA_PROVEDOR_PRINCIPAL = {
    "pergunta_rapida": provedores.consultar_groq,
    "resumo": provedores.consultar_cerebras,
}

MAPA_PROVEDOR_FALLBACK = {
    "pergunta_rapida": provedores.consultar_cerebras,
    "resumo": provedores.consultar_groq,
}

MENSAGEM_INDISPONIVEL = prompts.DELEGACAO_INDISPONIVEL

MENSAGEM_SEGUNDA_OPINIAO_INDISPONIVEL = (
    prompts.DELEGACAO_SEGUNDA_OPINIAO_INDISPONIVEL
)


def delegar(tipo_tarefa, conteudo):
    if tipo_tarefa == "segunda_opiniao":
        return _delegar_segunda_opiniao(conteudo)

    funcao_principal = MAPA_PROVEDOR_PRINCIPAL.get(tipo_tarefa)

    if not funcao_principal:
        return (
            f"Tipo de tarefa '{tipo_tarefa}' não é reconhecido. "
            "Responda a solicitação você mesmo."
        )

    sucesso, resultado = funcao_principal(conteudo)

    if sucesso:
        return resultado

    print(
        f"[delegacao_ia] Falha no provedor principal de "
        f"'{tipo_tarefa}': {resultado}"
    )

    funcao_fallback = MAPA_PROVEDOR_FALLBACK.get(tipo_tarefa)

    if funcao_fallback:
        sucesso, resultado = funcao_fallback(conteudo)

        if sucesso:
            return resultado

        print(
            f"[delegacao_ia] Falha no fallback de '{tipo_tarefa}': "
            f"{resultado}"
        )

    return MENSAGEM_INDISPONIVEL


# OpenAI: sem fallback de propósito, é a porta cara (CLAUDE.md).
def _delegar_segunda_opiniao(conteudo):
    sucesso, resultado = provedores.consultar_openai(conteudo)

    if not sucesso:
        print(
            "[delegacao_ia] Falha ao consultar segunda opinião "
            f"(OpenAI): {resultado}"
        )

        return MENSAGEM_SEGUNDA_OPINIAO_INDISPONIVEL

    return prompts.DELEGACAO_SEGUNDA_OPINIAO_RESULTADO.format(
        resultado=resultado
    )


MAPA_CEREBRO_CONFIGURADO = {
    "openai": provedores.consultar_openai,
    "gemini": provedores.consultar_gemini,
}


def delegar_para_cerebro_configurado(
    conteudo,
    json_esperado=False,
    timeout=None,
):
    from jarvis.nucleo.config import usar_provedor_openai

    nome_cerebro = "openai" if usar_provedor_openai() else "gemini"

    funcao = MAPA_CEREBRO_CONFIGURADO[nome_cerebro]

    sucesso, resultado = funcao(
        conteudo,
        json_esperado=json_esperado,
        timeout=timeout,
    )

    if sucesso:
        return True, resultado

    return False, f"[{nome_cerebro}] {resultado}"
