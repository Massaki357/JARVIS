# Catálogo curto das ferramentas de pacote (as 45 registradas em
# jarvis/nucleo/registro_pacotes.py — NUNCA as 15 nativas de
# jarvis/gemini/cliente_live.py, que dependem de estado de sessão de
# um GeminiLiveWorker vivo e não fazem sentido despachadas por uma
# chamada de texto sem sessão).
#
# Por que escrito à mão, e não derivado automaticamente das
# descrições completas de cada FunctionDeclaration: as descrições
# completas não têm uma estrutura consistente onde a primeira frase
# já é um resumo do que a função faz — boa parte delas começa com a
# ressalva de uso ("Use esta função somente quando..."), não com a
# ação em si. Uma extração posicional ("primeira frase") acertaria
# às vezes e erraria bastante, então cada resumo aqui foi escrito a
# partir da descrição completa real, mantendo só o que a ferramenta
# FAZ — nunca as travas de segurança, que continuam intactas e
# completas no schema da etapa 2 (ver esquema_groq.py).
#
# Isto é uma duplicação deliberada da mesma informação que os
# schemas completos já carregam — mesmo padrão já aceito neste
# projeto para as declarações nativas (cliente_live.py e
# cliente_realtime.py mantêm cada um sua própria cópia dos nomes
# nativos, sem um módulo compartilhado). Para essa duplicação não
# desatualizar em silêncio quando um pacote ganhar/perder/renomear
# uma ferramenta, ver verificar_catalogo_atualizado() no fim deste
# arquivo.
#
# A ORDEM deste dicionário é o que vira o texto fixo da etapa 1 (via
# montar_texto_catalogo) — não reordenar sem necessidade: é esse
# texto que precisa ficar idêntico entre requisições pra se
# beneficiar do cache automático de prompt da Groq.

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
    # --- controle_apps ---
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

    # --- arquivos ---
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

    # --- navegacao_web ---
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

    # --- automacao_residencial ---
    "controlar_dispositivo_casa": (
        "automacao_residencial",
        "Liga ou desliga um dispositivo da casa inteligente "
        "(interruptor, tomada, ar-condicionado, etc.).",
    ),

    # --- comunicacao ---
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

    # --- administracao ---
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

    # --- visao_camera ---
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

    # --- memoria ---
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

    # --- produtividade ---
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

    # --- financeiro ---
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

    # --- automacao_pc ---
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

    # --- delegacao ---
    "delegar_tarefa": (
        "delegacao",
        "Delega uma tarefa de texto pontual (pergunta rápida, "
        "resumo, ou segunda opinião) para outro provedor de IA.",
    ),
}


# Monta o texto fixo do catálogo curto, agrupado por categoria na
# ordem de CATEGORIAS, listando as ferramentas na ordem em que
# aparecem em CATALOGO_CURTO. Chamado uma vez (module-level, ver
# TEXTO_CATALOGO abaixo) — o resultado é sempre o mesmo texto, byte a
# byte, entre chamadas, o que é exatamente o que o cache automático
# de prompt da Groq precisa pra dar hit.
def montar_texto_catalogo():
    por_categoria = {chave: [] for chave, _rotulo in CATEGORIAS}

    for nome, (categoria, resumo) in CATALOGO_CURTO.items():
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


# Construído uma única vez, na importação do módulo — texto estável
# reaproveitado por roteador.py em toda chamada da etapa 1.
TEXTO_CATALOGO = montar_texto_catalogo()


# Confere se CATALOGO_CURTO ainda bate com as ferramentas de pacote
# realmente registradas em PACOTES_REGISTRADOS. Nunca lança — só
# imprime um aviso, porque um catálogo levemente desatualizado não
# deve derrubar o roteador (uma ferramenta faltando no catálogo
# simplesmente nunca é oferecida na etapa 1; uma sobrando é apenas
# ignorada, já que roteador.py sempre filtra os nomes que a etapa 1
# apontar contra o catálogo).
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
