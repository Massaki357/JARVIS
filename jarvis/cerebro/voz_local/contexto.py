# Monta o contexto que acompanha cada pedido de resposta falada ao
# alfred-server: os fatos de memória de longo prazo relevantes e o
# histórico recente da conversa.
#
# POR QUE ISTO EXISTE, e por que fica DO LADO DO JARVIS:
#
# Os dois cérebros de voz baseados em sessão resolvem isso uma vez, na
# abertura: o Gemini Live e o OpenAI Realtime montam uma instrução de
# sistema (prompt do perfil + memórias + data/hora) e a mandam junto do
# session.update / LiveConnectConfig. Dali em diante a própria sessão
# guarda o histórico dos turnos — o cliente não reenvia nada.
#
# O alfred-server não tem sessão: cada /responder é uma requisição
# isolada, sem estado entre chamadas. Foi por isso que, no modo local,
# perguntar o nome depois de tê-lo dito no turno anterior não
# funcionava — não era esquecimento do modelo, era ausência de canal.
#
# A decisão de manter o servidor sem conhecimento nenhum sobre o
# jarvis (a mesma já tomada para ferramentas) leva à única divisão
# possível: o JARVIS monta o contexto e manda pronto a cada chamada, e
# o servidor só usa o que recebe, sem guardar nada.
from jarvis.nucleo import prompts
from jarvis.nucleo.config import obter_nome_jarvis


# Quantas mensagens do histórico acompanham cada pedido. Conta
# MENSAGENS, não turnos: 6 são três idas e voltas. Mantido curto de
# propósito — o histórico viaja inteiro em toda chamada, e o servidor
# tem um modelo com janela de contexto para respeitar.
LIMITE_MENSAGENS_HISTORICO = 6

# Teto de caracteres do contexto de sistema. Vale como corte final,
# depois de já ter escolhido o que entra — um vault grande não pode
# transformar cada turno num pedido gigante.
LIMITE_CONTEXTO_CARACTERES = 1200

# Quantas memórias relevantes buscar por turno.
LIMITE_MEMORIAS_RELEVANTES = 4

# Corte de cada memória. As notas do vault podem ser resumos longos;
# aqui só interessa o fato.
LIMITE_CARACTERES_POR_MEMORIA = 180

# Pontuação mínima para uma nota entrar no contexto. Medido contra o
# vault real: a busca dá 4.0 para acerto de verdade (o termo aparece
# no título/palavras-chave) e 1.0 para nota que só encostou no assunto.
# Sem este corte, perguntar "qual é o meu nome" trazia junto notas
# sobre navegador e YouTube — ruído que ocupa espaço do contexto e
# ainda convida o modelo a falar do que ninguém perguntou.
PONTUACAO_MINIMA = 2.0


def montar_contexto_sistema(texto_do_turno):
    """
    Texto curto com identidade, data/hora e os fatos de memória
    relevantes para ESTE turno. Devolve "" se não houver nada a dizer.

    Nunca levanta exceção: contexto é um bônus para a resposta, e uma
    falha de leitura do vault não pode custar o turno inteiro.
    """
    partes = [
        f"Você é {obter_nome_jarvis()}, o assistente pessoal deste "
        "usuário. Responda em português do Brasil, de forma direta e "
        "conversacional — sua resposta será falada em voz alta.",
        prompts.contexto_data_hora().strip(),
    ]

    memorias = _memorias_relevantes(texto_do_turno)

    if memorias:
        partes.append(
            "Fatos que você já sabe sobre o usuário (use quando forem "
            "relevantes, sem mencionar que vieram de uma memória):\n"
            + "\n".join(f"- {linha}" for linha in memorias)
        )

    texto = "\n\n".join(parte for parte in partes if parte)

    if len(texto) > LIMITE_CONTEXTO_CARACTERES:
        texto = texto[:LIMITE_CONTEXTO_CARACTERES].rstrip() + "..."

    return texto


# Busca no vault do Obsidian (jarvis/pacotes/memoria_obsidian/) as
# notas relacionadas ao que o usuário acabou de dizer.
#
# É por AQUI que um fato como "o nome do usuário é Massaki" chega ao
# servidor. No caminho do Gemini isso acontece de outro jeito: o
# modelo chama a tool buscar_memorias_relacionadas quando sente falta
# do dado. Aqui não há como o servidor pedir nada — ele não sabe que
# memória existe —, então a busca é feita ANTES, sobre a fala do
# turno, e o resultado vai junto.
#
# registrar=False de propósito: contar como acesso marcaria as notas
# como usadas a cada turno, deixando last_used sempre fresco e fazendo
# os critérios de poda nunca dispararem. É a mesma decisão já tomada
# em memoria_obsidian.contexto_inicial(), pelo mesmo motivo.
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

        # A seção de wikilinks é navegação do Obsidian, não fato —
        # mandá-la ao modelo só gastaria contexto. Mesmo corte que
        # memoria_obsidian.contexto_inicial() já faz.
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
    """
    As últimas LIMITE_MENSAGENS_HISTORICO mensagens, no formato
    {"role", "content"} que a transcrição já usa.

    Recebe a lista e devolve uma CÓPIA cortada — quem chama não pode
    acabar mandando a referência da lista viva do worker, que continua
    crescendo enquanto o pedido está em voo.
    """
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
