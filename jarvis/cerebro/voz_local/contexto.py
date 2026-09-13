from jarvis.nucleo import prompts
from jarvis.nucleo.config import obter_nome_jarvis


LIMITE_MENSAGENS_HISTORICO = 6

LIMITE_CONTEXTO_CARACTERES = 1200

LIMITE_MEMORIAS_RELEVANTES = 4

LIMITE_CARACTERES_POR_MEMORIA = 180

PONTUACAO_MINIMA = 2.0


def montar_contexto_sistema(texto_do_turno):
    partes = [
        f"Você é {obter_nome_jarvis()}, o assistente pessoal deste "
        "usuário. Responda em português do Brasil, de forma direta e "
        "conversacional — sua resposta será falada em voz alta.",
        prompts.contexto_data_hora().strip(),
    ]

    memorias = _memorias_relevantes(texto_do_turno)

    if memorias:
        partes.append(
            prompts.CONTEXTO_MEMORIAS_INTRO
            + "\n"
            + "\n".join(f"- {linha}" for linha in memorias)
        )

    texto = "\n\n".join(parte for parte in partes if parte)

    if len(texto) > LIMITE_CONTEXTO_CARACTERES:
        texto = texto[:LIMITE_CONTEXTO_CARACTERES].rstrip() + "..."

    return texto


def _memorias_relevantes(texto_do_turno):
    consulta = (texto_do_turno or "").strip()

    if not consulta:
        return []

    try:
        from jarvis.pacotes.memoria_obsidian import busca, config as config_memoria

        if not config_memoria.configurado():
            return []

        notas = busca.buscar_memorias(
            consulta,
            limite=LIMITE_MEMORIAS_RELEVANTES,
            registrar=False,
        )

    except Exception as erro:
        print(f"[VOZ LOCAL] Não consegui ler a memória: {erro}")

        return []

    linhas = []

    for nota in notas or []:
        if float(nota.get("pontuacao") or 0) < PONTUACAO_MINIMA:
            continue

        corpo = str(nota.get("corpo") or "")

        posicao = corpo.find("## Relacionados")

        if posicao != -1:
            corpo = corpo[:posicao]

        corpo = " ".join(corpo.split())

        if not corpo:
            continue

        if len(corpo) > LIMITE_CARACTERES_POR_MEMORIA:
            corpo = corpo[:LIMITE_CARACTERES_POR_MEMORIA].rstrip() + "..."

        linhas.append(corpo)

    return linhas


def historico_para_envio(transcricao):
    if not transcricao:
        return []

    recentes = list(transcricao)[-LIMITE_MENSAGENS_HISTORICO:]

    return [
        {
            "role": mensagem.get("role", "user"),
            "content": str(mensagem.get("content") or ""),
        }
        for mensagem in recentes
        if str(mensagem.get("content") or "").strip()
    ]
