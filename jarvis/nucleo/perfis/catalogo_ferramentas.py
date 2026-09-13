ORIGEM_PACOTE = "pacote"
ORIGEM_NATIVA_GEMINI = "nativa_gemini"
ORIGEM_NATIVA_AMBOS = "nativa_ambos"


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


NOMES_NATIVAS_OPENAI = (
    "analisar_tela",
    "analisar_camera",
    "encerrar_chamada",
    "pausar_chamada",
)


FERRAMENTAS_SEMPRE_ATIVAS = (
    "encerrar_chamada",
    "pausar_chamada",
)


CATEGORIAS_NATIVAS = (
    ("visao_camera", "Visão e câmera"),
    ("email", "E-mail"),
    ("comunicacao", "Comunicação (rede jarvis e Discord)"),
    ("chamada", "Controle da chamada"),
)


def _catalogo_curto_pacotes():
    from jarvis.roteamento_hierarquico import catalogo

    return catalogo.CATALOGO_CURTO, catalogo.CATEGORIAS


def nomes_de_pacotes():
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
    return set(NATIVAS_GEMINI) | set(nomes_de_pacotes())


def resumo_de(nome):
    for item in catalogo_completo():
        if item["nome"] == nome:
            return item["resumo"]

    return ""


def nome_do_cerebro(usar_openai):
    return "OpenAI Realtime" if usar_openai else "Gemini Live"


def nomes_do_cerebro(usar_openai):
    if not usar_openai:
        return nomes_disponiveis()

    return set(NOMES_NATIVAS_OPENAI) | set(nomes_de_pacotes())


def cerebro_atual_usa_openai():
    from jarvis.nucleo.config import usar_provedor_openai

    return usar_provedor_openai()


def verificar_catalogo():
    tudo_certo = True

    try:
        from jarvis.cerebro.openai_realtime.cliente_realtime import (
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
