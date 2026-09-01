from . import provedores

# Mapa fixo de tipo de tarefa -> provedor principal, para os tipos
# "de uso livre" (baratos/rápidos). "segunda_opiniao" (OpenAI, cara)
# é tratado à parte, em _delegar_segunda_opiniao — não entra nesse
# mapa nem no de fallback, de propósito.
MAPA_PROVEDOR_PRINCIPAL = {
    "pergunta_rapida": provedores.consultar_groq,
    "resumo": provedores.consultar_cerebras,
}

# Se o provedor principal falhar (erro, timeout, chave ausente),
# tenta UM fallback antes de desistir — sempre um provedor rápido,
# pra não empilhar timeouts longos numa resposta de voz.
MAPA_PROVEDOR_FALLBACK = {
    "pergunta_rapida": provedores.consultar_cerebras,
    "resumo": provedores.consultar_groq,
}

MENSAGEM_INDISPONIVEL = (
    "Delegação indisponível no momento (todos os provedores "
    "falharam). Responda a solicitação você mesmo, com seu próprio "
    "raciocínio, sem mencionar essa falha ao usuário."
)

# Diferente de MENSAGEM_INDISPONIVEL: aqui a falha PRECISA ser
# mencionada ao usuário, porque "segunda_opiniao" existe justamente
# pra decisão de peso — o usuário precisa saber que a resposta não
# foi conferida por uma segunda IA desta vez.
MENSAGEM_SEGUNDA_OPINIAO_INDISPONIVEL = (
    "Não foi possível consultar uma segunda opinião agora (falha ao "
    "acessar a OpenAI). Responda a solicitação você mesmo, com seu "
    "próprio raciocínio, e avise ao usuário que não conseguiu "
    "confirmar essa resposta com uma segunda IA neste momento."
)


# Delega conteudo pro provedor mapeado em tipo_tarefa. Se falhar,
# tenta o fallback. Se os dois falharem (ou tipo_tarefa não for
# reconhecido), retorna uma mensagem clara pro Jarvis responder por
# conta própria — nunca lança exceção, nunca trava sem resposta.
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


# "segunda_opiniao" é tratado à parte do fluxo genérico acima, por
# dois motivos:
# 1. Não tem fallback pra Groq/Cerebras — isso deixaria de ser uma
#    "segunda opinião" de verdade (seriam provedores que o Jarvis já
#    usa rotineiramente pros outros tipos de tarefa, não uma IA
#    independente conferindo).
# 2. A resposta de sucesso vem embrulhada numa instrução de
#    comparar/sintetizar, e a mensagem de falha é diferente
#    (MENSAGEM_SEGUNDA_OPINIAO_INDISPONIVEL, que pede pra avisar o
#    usuário — ao contrário do resto, onde a falha fica em silêncio).
def _delegar_segunda_opiniao(conteudo):
    sucesso, resultado = provedores.consultar_openai(conteudo)

    if not sucesso:
        print(
            "[delegacao_ia] Falha ao consultar segunda opinião "
            f"(OpenAI): {resultado}"
        )

        return MENSAGEM_SEGUNDA_OPINIAO_INDISPONIVEL

    return (
        "[SEGUNDA OPINIÃO — OPENAI]\n"
        f"{resultado}\n\n"
        "Compare essa resposta com o seu próprio raciocínio sobre o "
        "mesmo assunto e responda ao usuário sintetizando os dois "
        "pontos de vista: onde concordam, onde divergem, e qual "
        "conclusão parece mais sólida. Não repasse a resposta acima "
        "como se fosse a única opinião."
    )
