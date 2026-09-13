from . import catalogo_ferramentas

_OUTRAS_MAQUINAS_E_PESSOAS = {
    "enviar_comando_remoto",
    "responder_permissao_remota",
    "enviar_dm_discord",
    "enviar_mensagem_discord",
    "enviar_captura_remoto",
}

_ADMINISTRACAO = {
    "executar_comando_admin",
    "confirmar_comando_admin",
}

_MUNDO_FISICO = {
    "controlar_dispositivo_casa",
}

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

_DADOS_PRA_FORA = {
    "preparar_email",
    "confirmar_envio_email",
    "ler_emails",
    "enviar_captura_email",
    "enviar_captura_discord_dm",
    "enviar_captura_discord_canal",
    "delegar_tarefa",
}

_VISAO_E_CAMERA = {
    "analisar_tela",
    "analisar_camera",
    "salvar_print_tela",
    "tirar_foto_camera",
    "iniciar_visualizacao_continua",
    "abrir_camera",
    "identificar_planta",
    "consultar_segunda_opiniao_visual",
    "descrever_tela",
    "descrever_camera",
}

_ENTRADA_CEGA = {
    "clicar_mouse",
    "duplo_clique_mouse",
    "clique_direito_mouse",
    "escrever_no_campo_ativo",
    "clicar_elemento_visual",
}


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
    return nome in FERRAMENTAS_SENSIVEIS


def motivo_de(nome):
    for rotulo, nomes in GRUPOS_SENSIVEIS:
        if nome in nomes:
            return rotulo

    return ""


def separar(nomes):
    comuns = []
    sensiveis = []

    for nome in nomes:
        (sensiveis if e_sensivel(nome) else comuns).append(nome)

    return comuns, sensiveis


def verificar_classificacao():
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
