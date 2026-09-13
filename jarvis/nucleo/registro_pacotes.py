from jarvis.pacotes import rede_jarvis

from jarvis.pacotes import casa_inteligente

from jarvis.pacotes import delegacao_ia

from jarvis.pacotes import agente_ferramentas

from jarvis.pacotes import admin_terminal

from jarvis.pacotes import configuracoes

from jarvis.pacotes import identificacao_planta

from jarvis.pacotes import descricao_visual
from jarvis.pacotes import identificacao_visual

from jarvis.pacotes import chat_jarvis

from jarvis.pacotes import discord_jarvis

from jarvis.pacotes import camera_preview

from jarvis.pacotes import fechar_app

from jarvis.pacotes import criar_arquivo

from jarvis.pacotes import memoria_obsidian


from jarvis.pacotes import arquivos_area_trabalho

from jarvis.pacotes import abrir_aplicativo

from jarvis.pacotes import navegador_web

from jarvis.pacotes import pesquisa_web

from jarvis.pacotes import controle_mouse

from jarvis.pacotes import escrita_texto

from jarvis.pacotes import clique_visual

from jarvis.pacotes import agenda

from jarvis.pacotes import consulta_acoes


PACOTES_REGISTRADOS = [
    rede_jarvis,
    casa_inteligente,
    delegacao_ia,
    agente_ferramentas,
    admin_terminal,
    configuracoes,
    identificacao_planta,
    descricao_visual,
    identificacao_visual,
    chat_jarvis,
    discord_jarvis,
    camera_preview,
    memoria_obsidian,
    fechar_app,
    criar_arquivo,
    arquivos_area_trabalho,
    abrir_aplicativo,
    navegador_web,
    pesquisa_web,
    controle_mouse,
    escrita_texto,
    clique_visual,
    agenda,
    consulta_acoes,
]


# Os workers reconhecem estas 3 listas pelo nome da tool call: nunca ocultar (docs/agente_ferramentas.md).
TOOLS_QUE_CAPTURAM_SOZINHAS = (
    "clicar_elemento_visual",
)


TOOLS_SILENCIOSAS = (
    "rolar_pagina",
    "escrever_no_campo_ativo",
    "clicar_elemento_visual",
)


TOOLS_QUE_PRECISAM_DE_IMAGEM = {
    "identificar_planta": "camera",
    "consultar_segunda_opiniao_visual": "camera",
    "descrever_tela": "tela",
    "descrever_camera": "camera",
}


FERRAMENTAS_SEMPRE_DECLARADAS = (
    "buscar_ferramenta",
    "executar_ferramenta",
    "ler_instrucao_ferramenta",
)


def nomes_de_pacote():
    nomes = set()

    for pacote in PACOTES_REGISTRADOS:
        try:
            declaracoes = pacote.obter_function_declarations()

        except Exception:
            continue

        nomes.update(declaracao.name for declaracao in declaracoes)

    return nomes


def ferramentas_ocultas():
    excecoes = (
        set(TOOLS_QUE_PRECISAM_DE_IMAGEM)
        | set(TOOLS_SILENCIOSAS)
        | set(TOOLS_QUE_CAPTURAM_SOZINHAS)
        | set(FERRAMENTAS_SEMPRE_DECLARADAS)
    )

    return nomes_de_pacote() - excecoes
