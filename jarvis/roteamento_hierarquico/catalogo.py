CATEGORIAS = (
    ("controle_apps", "Controle de aplicativos"),
    ("arquivos", "Arquivos e Área de Trabalho"),
    ("navegacao_web", "Navegação e pesquisa na web"),
    ("automacao_residencial", "Automação residencial"),
    ("comunicacao", "Comunicação (rede jarvis e Discord)"),
    ("administracao", "Administração do sistema"),
    ("visao_camera", "Visão e câmera"),
    ("memoria", "Memória"),
    ("produtividade", "Produtividade (chat, arquivos, agenda)"),
    ("financeiro", "Mercado financeiro"),
    ("automacao_pc", "Automação de mouse e teclado"),
    ("delegacao", "Delegação de tarefas"),
)

CATALOGO_CURTO = {
    "abrir_aplicativo": (
        "controle_apps",
        "Abre programas, pastas do sistema ou locais do Windows, "
        "como navegador, calculadora, painel de controle ou o "
        "Explorador de Arquivos.",
    ),
    "fechar_app": (
        "controle_apps",
        "Fecha um aplicativo que já está aberto nesta máquina, "
        "pelo nome.",
    ),

    "criar_arquivo": (
        "arquivos",
        "Cria um arquivo de texto simples numa pasta permitida "
        "(Área de Trabalho, Documentos ou Downloads).",
    ),
    "criar_pasta_area_trabalho": (
        "arquivos",
        "Cria uma pasta nova na Área de Trabalho.",
    ),
    "listar_area_de_trabalho": (
        "arquivos",
        "Lista os arquivos e pastas presentes na Área de Trabalho.",
    ),
    "organizar_area_de_trabalho_basico": (
        "arquivos",
        "Organiza os arquivos soltos da Área de Trabalho em pastas "
        "por tipo (imagens, PDFs, documentos, compactados).",
    ),
    "copiar_item_area_trabalho": (
        "arquivos",
        "Prepara um arquivo ou pasta da Área de Trabalho para ser "
        "copiado.",
    ),
    "recortar_item_area_trabalho": (
        "arquivos",
        "Prepara um arquivo ou pasta da Área de Trabalho para ser "
        "movido.",
    ),
    "colar_item_area_trabalho": (
        "arquivos",
        "Cola o último item copiado ou recortado da Área de "
        "Trabalho num destino.",
    ),
    "renomear_item_area_trabalho": (
        "arquivos",
        "Renomeia um arquivo ou pasta da Área de Trabalho.",
    ),
    "cancelar_transferencia_area_trabalho": (
        "arquivos",
        "Cancela uma cópia ou recorte pendente que ainda não foi "
        "colado.",
    ),

    "pesquisar_no_navegador": (
        "navegacao_web",
        "Abre uma pesquisa no Google pelo navegador padrão.",
    ),
    "tocar_no_youtube": (
        "navegacao_web",
        "Pesquisa e abre um vídeo ou música no YouTube pelo "
        "navegador padrão.",
    ),
    "pesquisar_informacao_atual": (
        "navegacao_web",
        "Pesquisa na internet uma informação atual ou que muda com "
        "o tempo (cotação, clima, placar, notícia).",
    ),

    "controlar_dispositivo_casa": (
        "automacao_residencial",
        "Liga ou desliga um dispositivo da casa inteligente "
        "(interruptor, tomada, ar-condicionado, etc.).",
    ),

    "enviar_comando_remoto": (
        "comunicacao",
        "Executa uma ação ou envia um arquivo para outro "
        "computador do jarvis, numa rede local de máquinas.",
    ),
    "responder_permissao_remota": (
        "comunicacao",
        "Responde a um pedido de permissão remota que outra "
        "máquina do jarvis está aguardando.",
    ),
    "listar_maquinas_remotas": (
        "comunicacao",
        "Lista quais máquinas do jarvis estão online agora.",
    ),
    "enviar_dm_discord": (
        "comunicacao",
        "Envia uma mensagem direta (DM) no Discord para um amigo "
        "específico, pelo nome.",
    ),
    "enviar_mensagem_discord": (
        "comunicacao",
        "Envia uma mensagem num canal de texto do Discord.",
    ),

    "executar_comando_admin": (
        "administracao",
        "Executa um comando de terminal do Windows com privilégio "
        "de administrador nesta máquina.",
    ),
    "confirmar_comando_admin": (
        "administracao",
        "Confirma ou nega um comando administrativo pendente de "
        "aprovação.",
    ),
    "abrir_configuracoes": (
        "administracao",
        "Abre a tela de configurações do jarvis para ver ou editar "
        "as variáveis do .env.",
    ),

    "descrever_tela": (
        "visao_camera",
        "Olha a tela do computador e descreve em voz alta o que "
        "está aparecendo nela, incluindo textos e mensagens de "
        "erro. Use quando pedirem para ver, olhar, conferir ou ler "
        "a tela.",
    ),
    "descrever_camera": (
        "visao_camera",
        "Olha pela webcam e descreve o que está sendo mostrado na "
        "frente dela. Use quando pedirem para ver, olhar ou "
        "conferir a câmera.",
    ),
    "identificar_planta": (
        "visao_camera",
        "Identifica a espécie de uma planta a partir de uma foto "
        "da câmera, usando uma API especializada em botânica.",
    ),
    "consultar_segunda_opiniao_visual": (
        "visao_camera",
        "Consulta um segundo modelo de visão, independente, para "
        "confirmar a identificação de um objeto mostrado na "
        "câmera.",
    ),
    "abrir_camera": (
        "visao_camera",
        "Abre uma janela com o vídeo ao vivo da webcam.",
    ),
    "fechar_camera": (
        "visao_camera",
        "Fecha a janela de vídeo ao vivo da webcam.",
    ),

    "salvar_memoria": (
        "memoria",
        "Guarda permanentemente uma informação que o usuário "
        "pediu para lembrar.",
    ),
    "buscar_memorias_relacionadas": (
        "memoria",
        "Procura na memória persistente o que já se sabe sobre um "
        "assunto.",
    ),
    "esquecer_memoria": (
        "memoria",
        "Apaga uma memória guardada, pelo título.",
    ),
    "listar_memorias": (
        "memoria",
        "Lista os títulos de tudo o que está guardado na memória.",
    ),

    "abrir_chat": (
        "produtividade",
        "Abre uma janela de chat de texto conectada à mesma "
        "conversa por voz.",
    ),
    "abrir_envio_arquivo": (
        "produtividade",
        "Abre uma janela para o usuário enviar um arquivo (imagem, "
        "PDF ou texto) como contexto da conversa.",
    ),
    "criar_evento_agenda": (
        "produtividade",
        "Salva um compromisso na agenda local, com data e "
        "horário.",
    ),
    "listar_agenda": (
        "produtividade",
        "Lista os próximos compromissos salvos na agenda.",
    ),
    "cancelar_evento_agenda": (
        "produtividade",
        "Cancela um compromisso da agenda.",
    ),

    "consultar_cotacao_acao": (
        "financeiro",
        "Consulta a cotação atual de uma ou mais ações (preço, "
        "variação, volume).",
    ),
    "consultar_historico_acao": (
        "financeiro",
        "Consulta o histórico recente de preços de uma ação "
        "específica.",
    ),

    "rolar_pagina": (
        "automacao_pc",
        "Rola a janela ou página sob o ponteiro do mouse, para "
        "cima ou para baixo.",
    ),
    "clicar_mouse": (
        "automacao_pc",
        "Executa um clique esquerdo na posição atual do ponteiro.",
    ),
    "duplo_clique_mouse": (
        "automacao_pc",
        "Executa um clique duplo na posição atual do ponteiro.",
    ),
    "clique_direito_mouse": (
        "automacao_pc",
        "Executa um clique com o botão direito na posição atual do "
        "ponteiro.",
    ),
    "escrever_no_campo_ativo": (
        "automacao_pc",
        "Digita um texto no campo que estiver ativo na tela, onde "
        "o cursor estiver piscando.",
    ),
    "clicar_elemento_visual": (
        "automacao_pc",
        "Localiza visualmente um elemento na tela pela descrição "
        "do usuário e clica nele.",
    ),

    "delegar_tarefa": (
        "delegacao",
        "Delega uma tarefa de texto pontual (pergunta rápida, "
        "resumo, ou segunda opinião) para outro provedor de IA.",
    ),
    "buscar_ferramenta": (
        "delegacao",
        "Pergunta a um sub-agente qual ferramenta atende a um pedido "
        "do usuário, e devolve as instruções de como executá-la.",
    ),
    "executar_ferramenta": (
        "delegacao",
        "Executa uma ferramenta pelo nome, para um cérebro que não a "
        "tem declarada na própria sessão.",
    ),
    "ler_instrucao_ferramenta": (
        "delegacao",
        "Devolve as instruções de uso de uma ferramenta antes de o "
        "cérebro usá-la.",
    ),
}


# Circulares aqui: a etapa 1 já é a pergunta 'qual ferramenta'.
FERRAMENTAS_FORA_DO_ROTEAMENTO = {
    "buscar_ferramenta",
    "executar_ferramenta",
    "ler_instrucao_ferramenta",
}


def montar_texto_catalogo():
    por_categoria = {chave: [] for chave, _rotulo in CATEGORIAS}

    for nome, (categoria, resumo) in CATALOGO_CURTO.items():
        if nome in FERRAMENTAS_FORA_DO_ROTEAMENTO:
            continue

        por_categoria[categoria].append((nome, resumo))

    blocos = []

    for chave, rotulo in CATEGORIAS:
        ferramentas = por_categoria[chave]

        if not ferramentas:
            continue

        linhas = [f"## {rotulo}"]

        linhas.extend(
            f"- {nome}: {resumo}" for nome, resumo in ferramentas
        )

        blocos.append("\n".join(linhas))

    return "\n\n".join(blocos)


TEXTO_CATALOGO = montar_texto_catalogo()


def verificar_catalogo_atualizado(pacotes_registrados):
    nomes_reais = set()

    for pacote in pacotes_registrados:
        try:
            declaracoes = pacote.obter_function_declarations()

        except Exception:
            continue

        for declaracao in declaracoes:
            nomes_reais.add(declaracao.name)

    nomes_catalogo = set(CATALOGO_CURTO.keys())

    faltando = sorted(nomes_reais - nomes_catalogo)
    sobrando = sorted(nomes_catalogo - nomes_reais)

    if faltando:
        print(
            "[roteamento_hierarquico] Ferramentas registradas mas "
            f"ausentes do catálogo curto (nunca serão oferecidas na "
            f"etapa 1): {faltando}"
        )

    if sobrando:
        print(
            "[roteamento_hierarquico] Entradas no catálogo curto "
            f"sem ferramenta registrada correspondente (inofensivo, "
            f"mas provavelmente desatualizado): {sobrando}"
        )

    return not faltando and not sobrando
