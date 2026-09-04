# Fonte única sobre QUAIS ferramentas existem no projeto, para o
# sistema de perfis.
#
# Um perfil guarda uma lista de NOMES de ferramentas. Para validar
# essa lista (nome inexistente é erro, nunca passa em silêncio) e
# para montar a tela de marcar/desmarcar ferramentas, alguém precisa
# saber o conjunto real de nomes. Este módulo é esse alguém — e ele
# NÃO inventa uma segunda lista:
#
# - As ferramentas de pacote saem de PACOTES_REGISTRADOS
#   (jarvis/nucleo/registro_pacotes.py), perguntando a cada pacote o
#   próprio obter_function_declarations(). É informação derivada,
#   então nunca desatualiza: um pacote novo aparece aqui sozinho.
# - O resumo de uma linha de cada ferramenta de pacote vem de
#   jarvis/roteamento_hierarquico/catalogo.py (CATALOGO_CURTO), que já
#   existia exatamente para isso. Não foi escrita uma segunda versão
#   desses resumos.
#
# O único pedaço escrito à mão aqui são os nomes das ferramentas
# NATIVAS, que não pertencem a pacote nenhum e vivem dentro dos dois
# clientes de voz. As do cliente OpenAI são importáveis
# (FUNCTION_DECLARATIONS_NATIVAS, nível de módulo) e são conferidas de
# verdade em verificar_catalogo(); as do Gemini estão declaradas
# dentro de um método de GeminiLiveWorker, inalcançáveis sem uma
# sessão, então continuam listadas à mão — mesma duplicação
# deliberada que jarvis/roteamento_hierarquico/catalogo.py já
# documenta e aceita para os nomes nativos.
#
# IMPORTANTE: os dois provedores NÃO têm as mesmas ferramentas
# nativas. O Gemini tem 16 (visão, e-mail, envio de captura,
# encerramento); o OpenAI Realtime tem 4. Um perfil pode listar uma
# ferramenta que só existe em um dos dois — quem resolve isso é a
# integração com o início da chamada (Fase 5), que intersecta a lista
# do perfil com o que o provedor daquela chamada realmente oferece.
# Aqui a lista é a UNIÃO: o catálogo descreve o projeto inteiro.

# Origem de cada ferramenta, usada para agrupar na interface e para
# a integração saber de onde ela vem.
ORIGEM_PACOTE = "pacote"
ORIGEM_NATIVA_GEMINI = "nativa_gemini"
ORIGEM_NATIVA_AMBOS = "nativa_ambos"


# Ferramentas nativas do cliente Gemini Live
# (jarvis/gemini/cliente_live.py, function_declarations_nativas).
# nome -> (categoria, resumo de uma linha)
NATIVAS_GEMINI = {
    "analisar_tela": (
        "visao_camera",
        "Olha a tela do computador e descreve o que está sendo "
        "mostrado, sem salvar nada.",
    ),
    "salvar_print_tela": (
        "visao_camera",
        "Captura o monitor onde o cursor está e salva a imagem em "
        "arquivo.",
    ),
    "analisar_camera": (
        "visao_camera",
        "Olha pela webcam e descreve o que está na frente dela, sem "
        "salvar nada.",
    ),
    "tirar_foto_camera": (
        "visao_camera",
        "Tira uma foto pela webcam e salva a imagem em arquivo.",
    ),
    "iniciar_visualizacao_continua": (
        "visao_camera",
        "Começa a acompanhar a tela continuamente, quadro a quadro, "
        "enquanto a conversa segue.",
    ),
    "parar_visualizacao_continua": (
        "visao_camera",
        "Para o acompanhamento contínuo da tela.",
    ),
    "preparar_email": (
        "email",
        "Prepara um rascunho de e-mail para ser lido em voz alta e "
        "confirmado — nunca envia nada sozinha.",
    ),
    "confirmar_envio_email": (
        "email",
        "Envia de fato o rascunho de e-mail já preparado, depois da "
        "confirmação do usuário.",
    ),
    "ler_emails": (
        "email",
        "Lista os e-mails mais recentes da caixa de entrada ou do "
        "spam.",
    ),
    "baixar_anexo_email": (
        "email",
        "Baixa o anexo de um e-mail para uma pasta local.",
    ),
    "enviar_captura_email": (
        "email",
        "Envia por e-mail o último print ou foto (ou captura um "
        "novo), passando pela mesma confirmação de envio.",
    ),
    "enviar_captura_discord_dm": (
        "comunicacao",
        "Envia o último print ou foto por mensagem direta no Discord.",
    ),
    "enviar_captura_discord_canal": (
        "comunicacao",
        "Envia o último print ou foto para um canal de texto do "
        "Discord.",
    ),
    "enviar_captura_remoto": (
        "comunicacao",
        "Envia o último print ou foto para outra máquina do jarvis.",
    ),
    "encerrar_chamada": (
        "chamada",
        "Encerra a chamada de voz atual.",
    ),
    "pausar_chamada": (
        "chamada",
        "Pausa a chamada sem encerrar, para continuar de onde parou "
        "na próxima ativação.",
    ),
}


# Ferramentas nativas do cliente OpenAI Realtime
# (jarvis/openai_realtime/cliente_realtime.py,
# FUNCTION_DECLARATIONS_NATIVAS). Subconjunto das de cima — os
# resumos são reaproveitados de NATIVAS_GEMINI, não reescritos.
NOMES_NATIVAS_OPENAI = (
    "analisar_tela",
    "analisar_camera",
    "encerrar_chamada",
    "pausar_chamada",
)


# Ferramentas que NENHUM perfil pode desligar. Sem elas o usuário
# fica sem como terminar a chamada por voz, que é a única saída que
# não depende de olhar para a tela — não é uma capacidade opcional
# do assistente, é o botão de sair.
FERRAMENTAS_SEMPRE_ATIVAS = (
    "encerrar_chamada",
    "pausar_chamada",
)


# Rótulo legível de cada categoria. As de pacote vêm de
# roteamento_hierarquico.catalogo.CATEGORIAS; estas quatro só existem
# para as nativas, que aquele catálogo não cobre (ele é explicitamente
# só das ferramentas de pacote).
CATEGORIAS_NATIVAS = (
    ("visao_camera", "Visão e câmera"),
    ("email", "E-mail"),
    ("comunicacao", "Comunicação (rede jarvis e Discord)"),
    ("chamada", "Controle da chamada"),
)


def _catalogo_curto_pacotes():
    """
    Resumos de uma linha das ferramentas de pacote, reaproveitados de
    jarvis/roteamento_hierarquico/catalogo.py. Import adiado porque
    este módulo é importado pela camada de dados dos perfis, que roda
    em contextos (testes, scripts) onde carregar o roteador inteiro
    seria peso à toa.
    """
    from jarvis.roteamento_hierarquico import catalogo

    return catalogo.CATALOGO_CURTO, catalogo.CATEGORIAS


def nomes_de_pacotes():
    """
    Nomes das ferramentas realmente expostas pelos pacotes de
    PACOTES_REGISTRADOS, perguntados a cada pacote na hora. Informação
    derivada: um pacote novo entra aqui sozinho, sem editar nada.

    Um pacote que levante exceção ao declarar as próprias tools é
    ignorado com aviso, nunca derruba a listagem de perfis inteira.
    """
    from jarvis.nucleo.registro_pacotes import PACOTES_REGISTRADOS

    nomes = []

    for pacote in PACOTES_REGISTRADOS:
        try:
            declaracoes = pacote.obter_function_declarations()

        except Exception as erro:
            nome_pacote = getattr(pacote, "__name__", pacote)

            print(
                f"[perfis] Pacote {nome_pacote} falhou ao declarar as "
                f"próprias ferramentas ({erro}) — ignorado no catálogo."
            )
            continue

        for declaracao in declaracoes:
            nomes.append(declaracao.name)

    return nomes


def _origem_nativa(nome):
    if nome in NOMES_NATIVAS_OPENAI:
        return ORIGEM_NATIVA_AMBOS

    return ORIGEM_NATIVA_GEMINI


def catalogo_completo():
    """
    Catálogo de TODAS as ferramentas do projeto, na ordem em que
    devem aparecer numa lista: primeiro as nativas, depois as de
    pacote.

    Devolve uma lista de dicts:

        {
          "nome": "analisar_tela",
          "resumo": "Olha a tela do computador e ...",
          "categoria": "visao_camera",
          "rotulo_categoria": "Visão e câmera",
          "origem": "nativa_ambos",
          "sempre_ativa": False,
        }
    """
    curto_pacotes, categorias_pacotes = _catalogo_curto_pacotes()

    rotulos = dict(CATEGORIAS_NATIVAS)
    rotulos.update(dict(categorias_pacotes))

    itens = []

    for nome, (categoria, resumo) in NATIVAS_GEMINI.items():
        itens.append(
            {
                "nome": nome,
                "resumo": resumo,
                "categoria": categoria,
                "rotulo_categoria": rotulos.get(categoria, categoria),
                "origem": _origem_nativa(nome),
                "sempre_ativa": nome in FERRAMENTAS_SEMPRE_ATIVAS,
            }
        )

    for nome in nomes_de_pacotes():
        categoria, resumo = curto_pacotes.get(
            nome,
            ("outros", "(sem resumo no catálogo curto)"),
        )

        itens.append(
            {
                "nome": nome,
                "resumo": resumo,
                "categoria": categoria,
                "rotulo_categoria": rotulos.get(categoria, categoria),
                "origem": ORIGEM_PACOTE,
                "sempre_ativa": nome in FERRAMENTAS_SEMPRE_ATIVAS,
            }
        )

    return itens


def nomes_disponiveis():
    """
    Conjunto de todos os nomes de ferramenta válidos do projeto —
    a união das nativas dos dois provedores com as de pacote. É o
    conjunto contra o qual a lista de um perfil é validada.
    """
    return set(NATIVAS_GEMINI) | set(nomes_de_pacotes())


def resumo_de(nome):
    """Resumo de uma linha de uma ferramenta, ou string vazia."""
    for item in catalogo_completo():
        if item["nome"] == nome:
            return item["resumo"]

    return ""


def verificar_catalogo():
    """
    Confere o pedaço escrito à mão deste módulo contra a realidade,
    até onde a realidade é importável.

    Nunca levanta exceção — só imprime aviso e devolve True/False,
    mesma postura de
    roteamento_hierarquico.catalogo.verificar_catalogo_atualizado():
    um catálogo levemente desatualizado não pode derrubar a tela de
    perfis.

    O que dá para conferir de verdade:

    - As nativas do OpenAI, que são importáveis.
    - Que nenhuma nativa listada aqui colide com nome de ferramenta
      de pacote (colisão silenciosa faria o perfil habilitar a
      ferramenta errada).
    - Que FERRAMENTAS_SEMPRE_ATIVAS existe mesmo no catálogo.

    O que NÃO dá: as 16 nativas do Gemini, declaradas dentro de um
    método de GeminiLiveWorker. Se uma nativa for adicionada ou
    renomeada lá, NATIVAS_GEMINI precisa ser atualizada à mão.
    """
    tudo_certo = True

    try:
        from jarvis.openai_realtime.cliente_realtime import (
            FUNCTION_DECLARATIONS_NATIVAS,
        )

        reais_openai = {
            declaracao.name
            for declaracao in FUNCTION_DECLARATIONS_NATIVAS
        }

    except Exception as erro:
        print(
            "[perfis] Não consegui conferir as nativas do OpenAI "
            f"Realtime ({erro})."
        )
        reais_openai = None

    if reais_openai is not None:
        declaradas = set(NOMES_NATIVAS_OPENAI)

        if reais_openai != declaradas:
            tudo_certo = False

            print(
                "[perfis] NOMES_NATIVAS_OPENAI está desatualizado. "
                f"Faltando: {sorted(reais_openai - declaradas)} "
                f"Sobrando: {sorted(declaradas - reais_openai)}"
            )

        fora_do_gemini = reais_openai - set(NATIVAS_GEMINI)

        if fora_do_gemini:
            tudo_certo = False

            print(
                "[perfis] Nativas do OpenAI ausentes de NATIVAS_GEMINI "
                f"(sem resumo no catálogo): {sorted(fora_do_gemini)}"
            )

    nomes_pacotes = set(nomes_de_pacotes())
    colisoes = nomes_pacotes & set(NATIVAS_GEMINI)

    if colisoes:
        tudo_certo = False

        print(
            "[perfis] Nome de ferramenta nativa colidindo com "
            f"ferramenta de pacote: {sorted(colisoes)}"
        )

    ausentes = set(FERRAMENTAS_SEMPRE_ATIVAS) - (
        nomes_pacotes | set(NATIVAS_GEMINI)
    )

    if ausentes:
        tudo_certo = False

        print(
            "[perfis] FERRAMENTAS_SEMPRE_ATIVAS aponta para "
            f"ferramenta que não existe: {sorted(ausentes)}"
        )

    return tudo_certo
