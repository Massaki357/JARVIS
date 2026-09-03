"""
A lista PACOTES_REGISTRADOS — o registro único dos pacotes de tools.

Antes ela morava dentro de jarvis/gemini/cliente_live.py, e adicionar
um pacote novo exigia editar aquele arquivo (um dos três arquivos do
projeto do curso, que devem ser tocados o mínimo possível). Ela saiu
de lá por dois motivos:

1. Passou a existir um SEGUNDO cérebro de voz — o provedor OpenAI
   Realtime (jarvis/openai_realtime/cliente_realtime.py) — e os dois
   precisam da mesma lista. O cliente OpenAI não pode importar
   cliente_live.py só pra pegar a lista (seria arrastar a sessão
   Gemini inteira junto), e cliente_live.py também não pode importar
   do OpenAI: um módulo neutro resolve os dois lados.
2. Com a lista aqui, registrar um pacote novo não toca mais NENHUM
   dos três arquivos do curso — é uma linha neste arquivo e pronto.
   Ver docs/INTEGRATION.md.

Todo pacote listado aqui expõe exatamente obter_function_declarations()
e despachar() — o contrato padrão descrito em docs/INTEGRATION.md.

Pacotes que NÃO entram nesta lista (de propósito):

- explorador_windows e ativacao_voz: seguem o formato do contrato mas
  não expõem tool nenhuma (obter_function_declarations() devolve []),
  então entrar aqui só adicionaria um despachar() eternamente None a
  cada tool call.
"""

# Pacote isolado com toda a lógica de comunicação e comando remoto
# entre instâncias do jarvis via MQTT.
from jarvis.pacotes import rede_jarvis

# Controle de dispositivos de casa inteligente (Tuya, por enquanto).
from jarvis.pacotes import casa_inteligente

# Delegação de tarefas de texto pontuais pra outras APIs de LLM
# (Groq/Cerebras/OpenAI).
from jarvis.pacotes import delegacao_ia

# Execução de comandos de terminal com privilégio de administrador,
# local a esta máquina. Deliberadamente não conectado a rede_jarvis.
from jarvis.pacotes import admin_terminal

# Tela de configurações (visualizar/editar as variáveis do .env).
from jarvis.pacotes import configuracoes

# Identificação de espécie de planta via foto (Pl@ntNet). Exceção ao
# despacho genérico: a captura da câmera acontece no cliente, antes
# de despachar() — ver docs/INTEGRATION.md.
from jarvis.pacotes import identificacao_planta

# Segunda opinião visual independente (Mistral). Mesma exceção de
# identificacao_planta.
from jarvis.pacotes import identificacao_visual

# Janelas de chat de texto e envio de arquivo, ligadas à MESMA sessão
# em andamento.
from jarvis.pacotes import chat_jarvis

# Conexão persistente com o bot do Discord (DM e mensagem em canal).
from jarvis.pacotes import discord_jarvis

# Janela de vídeo AO VIVO da webcam.
from jarvis.pacotes import camera_preview

# Fecha um app já aberto nesta máquina, pelo nome.
from jarvis.pacotes import fechar_app

# Cria um arquivo de texto simples, só em pastas permitidas.
from jarvis.pacotes import criar_arquivo

# Memória persistente em um vault do Obsidian.
from jarvis.pacotes import memoria_obsidian

# ============================================================
# Pacotes vindos do JARVIS COMPLETO (pasta actions/ do curso)
# ============================================================

# Arquivos e pastas da Área de Trabalho (criar, listar, organizar,
# copiar/recortar/colar, renomear). Nunca exclui, nunca sobrescreve.
from jarvis.pacotes import arquivos_area_trabalho

# Abre aplicativos, programas e locais do Windows. SUBSTITUIU o
# pacote abrir_app_local.
from jarvis.pacotes import abrir_aplicativo

# Pesquisa no Google e reprodução no YouTube pelo navegador padrão.
# SUBSTITUIU o pacote navegador_jarvis (Playwright).
from jarvis.pacotes import navegador_web

# Pesquisa invisível de informação atual (DuckDuckGo), com filtro
# local decidindo antes se a pergunta realmente precisa de internet.
from jarvis.pacotes import pesquisa_web

# Rolagem e cliques do mouse pela API nativa do Windows.
from jarvis.pacotes import controle_mouse

# Escrita de texto no campo ativo do Windows.
from jarvis.pacotes import escrita_texto

# Clique em um elemento da tela descrito por voz (localizador visual
# + mouse). CAPTURA A TELA por dentro — por isso o cliente segura o
# mutex de função visual em volta do despacho dele.
from jarvis.pacotes import clique_visual

# Agenda local persistente de compromissos (dados/agenda.json).
from jarvis.pacotes import agenda

# Cotação e histórico de ações (Twelve Data).
from jarvis.pacotes import consulta_acoes


# A ORDEM importa: o despacho percorre esta lista e para no primeiro
# pacote que reconhece o nome da função. Nenhum nome de tool se
# repete entre pacotes hoje, mas manter uma ordem estável evita que
# um pacote novo passe a interceptar sem querer a tool de outro.
PACOTES_REGISTRADOS = [
    rede_jarvis,
    casa_inteligente,
    delegacao_ia,
    admin_terminal,
    configuracoes,
    identificacao_planta,
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


# Tools que capturam a tela ou a câmera POR DENTRO do próprio
# despachar(), sem receber a imagem como parâmetro. O cliente precisa
# segurar self._mutex_funcao_visual() em volta do despacho delas —
# ver a regra em CLAUDE.md ("Any new code path that captures a screen
# or camera frame outside of processar_funcao_visual...").
#
# Não confundir com identificar_planta/consultar_segunda_opiniao_visual:
# nessas duas é o CLIENTE quem captura e injeta imagem_bytes em args,
# então elas têm um tratamento próprio, à parte.
TOOLS_QUE_CAPTURAM_SOZINHAS = (
    "clicar_elemento_visual",
)


# Tools cuja resposta falada atrapalha em vez de ajudar: o usuário
# pediu uma AÇÃO na tela dele, e ouvir "pronto, rolei a página" a
# cada rolagem é ruído. O cliente descarta o áudio do turno inteiro
# quando uma destas é executada (silenciar_audio_ate_fim_turno).
# Comportamento herdado do JARVIS COMPLETO.
TOOLS_SILENCIOSAS = (
    "rolar_pagina",
    "escrever_no_campo_ativo",
    "clicar_elemento_visual",
)
