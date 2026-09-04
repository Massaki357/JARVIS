from jarvis.nucleo import prompts

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

# Textos devolvidos ao Gemini como resultado da tool (não prompts
# para Groq/Cerebras/OpenAI em si — ver jarvis/nucleo/prompts/,
# seção DELEGACAO_IA, e o comentário em provedores._chamar_completions
# sobre o "prompt" real ser o conteudo cru vindo do próprio Gemini).
MENSAGEM_INDISPONIVEL = prompts.DELEGACAO_INDISPONIVEL

# Diferente de MENSAGEM_INDISPONIVEL: aqui a falha PRECISA ser
# mencionada ao usuário, porque "segunda_opiniao" existe justamente
# pra decisão de peso — o usuário precisa saber que a resposta não
# foi conferida por uma segunda IA desta vez.
MENSAGEM_SEGUNDA_OPINIAO_INDISPONIVEL = (
    prompts.DELEGACAO_SEGUNDA_OPINIAO_INDISPONIVEL
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

    return prompts.DELEGACAO_SEGUNDA_OPINIAO_RESULTADO.format(
        resultado=resultado
    )


# Provedor de cada valor possível de PROVEDOR_IA (jarvis/nucleo/
# config.py). São só dois porque só existem dois cérebros de voz.
MAPA_CEREBRO_CONFIGURADO = {
    "openai": provedores.consultar_openai,
    "gemini": provedores.consultar_gemini,
}


def delegar_para_cerebro_configurado(
    conteudo,
    json_esperado=False,
    timeout=None,
):
    """
    Manda um pedido de texto para O MESMO cérebro que o usuário
    escolheu em PROVEDOR_IA (.env) — Gemini ou OpenAI.

    Diferente de delegar(): esta rota NÃO escolhe provedor por tipo de
    tarefa, não tem fallback para outro provedor, e devolve
    (sucesso, texto) cru em vez de uma mensagem pronta para o modelo
    de voz falar. Quem chama é a criação de perfil por IA
    (jarvis/nucleo/perfis/geracao.py), que precisa do texto para
    validar em código, e para quem "tentar outro provedor" seria
    errado: o requisito é usar o cérebro configurado, não qualquer um
    que responda.

    Fallback seria pior que o erro aqui. Se o cérebro configurado não
    responde, a tela diz isso e o usuário tenta de novo — em vez de
    receber, calado, um perfil escrito por outra IA que ele não
    escolheu.

    Esta função é também o motivo de o Gemini ter entrado neste
    pacote: com ela, a criação de perfil alcança a OpenAI SEM abrir
    uma terceira porta fora daqui (ver a regra das duas portas
    sancionadas no CLAUDE.md).
    """
    # Import adiado: roteador.py é carregado no import do pacote, que
    # entra em PACOTES_REGISTRADOS, e jarvis.nucleo.config lê o .env
    # em tempo de importação. Adiando, a leitura acontece na hora da
    # chamada — que é o que faz uma troca de PROVEDOR_IA valer sem
    # reiniciar o app.
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
