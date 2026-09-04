# Quais ferramentas do projeto são SENSÍVEIS.
#
# Uma ferramenta sensível nunca entra sozinha num perfil criado pela
# IA. Se o cérebro escolher uma delas, ela aparece destacada numa
# etapa de confirmação e o usuário aprova item a item — a lista que
# volta do modelo é uma SUGESTÃO para as sensíveis, nunca uma decisão.
#
# O CRITÉRIO — DUAS DIMENSÕES, NÃO UMA
# ====================================
#
# 1. AÇÃO IRREVERSÍVEL. A ferramenta age FORA da conversa, de um jeito
#    que o usuário não desfaz sozinho e na hora: agir em outra
#    máquina, mexer em arquivo, mandar dado pra fora, injetar
#    clique/tecla no sistema, privilégio de administrador.
#
# 2. EXPOSIÇÃO DE INFORMAÇÃO. A ferramenta não altera nada, mas revela
#    coisa do usuário que aquele perfil não deveria ver. É por isso
#    que listar_area_de_trabalho é sensível apesar de ser só leitura:
#    um perfil de atendimento a cliente lendo os nomes dos arquivos do
#    computador pessoal não deveria acontecer, mesmo sem nada
#    irreversível envolvido. ler_emails, analisar_tela e
#    analisar_camera entram pela mesma porta.
#
# Uma ferramenta é sensível se bate em QUALQUER uma das duas. Ao
# classificar uma ferramenta nova, checar as duas — a segunda é a que
# passa despercebido, porque "não faz nada, só lê" soa inofensivo.
#
# O custo dos dois erros é assimétrico, e é isso que decide os casos
# duvidosos: marcar algo inofensivo como sensível custa UMA caixa de
# confirmação, uma vez, na criação do perfil. Deixar de marcar algo
# perigoso dá ao perfil uma capacidade que ninguém aprovou. Na dúvida,
# marca-se.
#
# COMO MUDAR ESTA CLASSIFICAÇÃO
# =============================
#
# Mexer no conjunto abaixo, e mais nada. Nenhuma outra parte do código
# tem lista de ferramenta sensível escrita à mão — a tela de
# confirmação, a validação e o prompt enviado ao modelo perguntam
# todos a e_sensivel(). Uma ferramenta nova entra aqui se for o caso;
# não entrando, ela é tratada como não sensível, que é o padrão
# deliberado (o contrário — tudo sensível por omissão — faria a
# confirmação virar ruído e o usuário carimbar tudo sem ler).
from . import catalogo_ferramentas

# --- Age em outra máquina ou fala com outras pessoas ---------------
# Sai desta máquina. O estrago não é local e o usuário pode nem ficar
# sabendo que aconteceu.
_OUTRAS_MAQUINAS_E_PESSOAS = {
    "enviar_comando_remoto",
    "responder_permissao_remota",
    "enviar_dm_discord",
    "enviar_mensagem_discord",
    "enviar_captura_remoto",
}

# --- Privilégio de administrador ----------------------------------
# O poder máximo que o app tem nesta máquina.
#
# abrir_configuracoes foi avaliada aqui e ficou de FORA, por decisão
# explícita: ela só abre uma janela, os valores sensíveis já aparecem
# mascarados nela, e funcionalmente não é diferente de abrir_chat ou
# abrir_camera, que também não são sensíveis. Marcar seria confirmar
# uma janela, não uma capacidade.
_ADMINISTRACAO = {
    "executar_comando_admin",
    "confirmar_comando_admin",
}

# --- Mundo físico -------------------------------------------------
# Liga e desliga coisa de verdade dentro da casa.
_MUNDO_FISICO = {
    "controlar_dispositivo_casa",
}

# --- Arquivos e processos desta máquina ---------------------------
# Escrever, mover, renomear e apagar não se desfazem com um "ctrl+z"
# na conversa. copiar/recortar_item_area_trabalho ficam DE FORA de
# propósito: elas só marcam o item numa área de transferência interna
# do pacote e não mexem em nada — quem de fato move o arquivo é
# colar_item_area_trabalho, e é essa que é sensível.
_ARQUIVOS_E_PROCESSOS = {
    "criar_arquivo",
    "criar_pasta_area_trabalho",
    "listar_area_de_trabalho",
    "organizar_area_de_trabalho_basico",
    "colar_item_area_trabalho",
    "renomear_item_area_trabalho",
    "baixar_anexo_email",
    "fechar_app",
    "esquecer_memoria",
}

# --- Manda dado do usuário pra fora -------------------------------
# E-mail lido, e-mail enviado, captura enviada. Note que
# preparar_email já tem confirmação por voz em tempo de execução; isto
# aqui é outra camada, na criação do perfil: a pergunta não é "envio
# este e-mail?", é "este perfil pode mandar e-mail?".
_DADOS_PRA_FORA = {
    "preparar_email",
    "confirmar_envio_email",
    "ler_emails",
    "enviar_captura_email",
    "enviar_captura_discord_dm",
    "enviar_captura_discord_canal",
    "delegar_tarefa",
}

# --- Vê a tela ou a câmera ----------------------------------------
# Privacidade. identificar_planta e consultar_segunda_opiniao_visual
# entram porque, além de capturar, mandam a imagem pra uma API de
# terceiro (Pl@ntNet e Mistral). parar_visualizacao_continua e
# fechar_camera ficam de fora: só desligam.
_VISAO_E_CAMERA = {
    "analisar_tela",
    "analisar_camera",
    "salvar_print_tela",
    "tirar_foto_camera",
    "iniciar_visualizacao_continua",
    "abrir_camera",
    "identificar_planta",
    "consultar_segunda_opiniao_visual",
}

# --- Entrada cega no sistema --------------------------------------
# Clica e digita no que estiver na frente, seja o que for.
# escrever_no_campo_ativo ainda por cima SUBSTITUI a área de
# transferência real do Windows. rolar_pagina fica de fora: rolar não
# altera nada.
_ENTRADA_CEGA = {
    "clicar_mouse",
    "duplo_clique_mouse",
    "clique_direito_mouse",
    "escrever_no_campo_ativo",
    "clicar_elemento_visual",
}


# Rótulo de cada grupo, mostrado na etapa de confirmação para o
# usuário entender POR QUE aquilo está sendo perguntado.
GRUPOS_SENSIVEIS = (
    ("Age em outra máquina ou fala com outras pessoas",
     _OUTRAS_MAQUINAS_E_PESSOAS),
    ("Privilégio de administrador", _ADMINISTRACAO),
    ("Controla dispositivos físicos da casa", _MUNDO_FISICO),
    ("Mexe em arquivos e programas desta máquina",
     _ARQUIVOS_E_PROCESSOS),
    ("Manda dados seus para fora", _DADOS_PRA_FORA),
    ("Vê sua tela ou sua câmera", _VISAO_E_CAMERA),
    ("Clica e digita no sistema por você", _ENTRADA_CEGA),
)


FERRAMENTAS_SENSIVEIS = frozenset().union(
    *(nomes for _rotulo, nomes in GRUPOS_SENSIVEIS)
)


def e_sensivel(nome):
    """Única pergunta que o resto do código faz sobre sensibilidade."""
    return nome in FERRAMENTAS_SENSIVEIS


def motivo_de(nome):
    """
    Rótulo do grupo que tornou a ferramenta sensível, para a etapa de
    confirmação. String vazia se ela não for sensível.
    """
    for rotulo, nomes in GRUPOS_SENSIVEIS:
        if nome in nomes:
            return rotulo

    return ""


def separar(nomes):
    """
    Divide uma lista de nomes em (comuns, sensiveis), preservando a
    ordem de entrada. É o que a tela de criação usa para montar a
    etapa de confirmação.
    """
    comuns = []
    sensiveis = []

    for nome in nomes:
        (sensiveis if e_sensivel(nome) else comuns).append(nome)

    return comuns, sensiveis


def verificar_classificacao():
    """
    Confere que toda ferramenta listada aqui existe mesmo no projeto,
    e que nenhuma aparece em dois grupos.

    Nunca levanta exceção — imprime e devolve True/False, mesma
    postura de catalogo_ferramentas.verificar_catalogo(): uma
    classificação levemente desatualizada não pode derrubar a tela de
    perfis. Um nome órfão aqui é inofensivo (nunca casa com nada), mas
    quase sempre significa que a ferramenta foi renomeada — e aí a
    versão nova está passando como NÃO sensível, que é o caso que
    importa pegar.
    """
    tudo_certo = True

    reais = catalogo_ferramentas.nomes_disponiveis()
    orfas = sorted(FERRAMENTAS_SENSIVEIS - reais)

    if orfas:
        tudo_certo = False

        print(
            "[perfis] Ferramentas marcadas como sensíveis que não "
            f"existem no projeto (renomeadas?): {orfas}"
        )

    vistas = set()

    for _rotulo, nomes in GRUPOS_SENSIVEIS:
        repetidas = sorted(vistas & nomes)

        if repetidas:
            tudo_certo = False

            print(
                "[perfis] Ferramenta sensível em mais de um grupo "
                f"(motivo_de fica ambíguo): {repetidas}"
            )

        vistas |= nomes

    # As obrigatórias nunca podem ser sensíveis: elas entram em todo
    # perfil automaticamente, então exigir confirmação delas seria
    # perguntar algo que não dá pra recusar.
    obrigatorias_sensiveis = sorted(
        set(catalogo_ferramentas.FERRAMENTAS_SEMPRE_ATIVAS)
        & FERRAMENTAS_SENSIVEIS
    )

    if obrigatorias_sensiveis:
        tudo_certo = False

        print(
            "[perfis] Ferramenta obrigatória marcada como sensível — "
            f"a confirmação seria impossível de recusar: "
            f"{obrigatorias_sensiveis}"
        )

    return tudo_certo
