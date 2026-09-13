"""
A lista PACOTES_REGISTRADOS — o registro único dos pacotes de tools.

Antes ela morava dentro de jarvis/cerebro/gemini/cliente_live.py, e adicionar
um pacote novo exigia editar aquele arquivo (um dos três arquivos do
projeto do curso, que devem ser tocados o mínimo possível). Ela saiu
de lá por dois motivos:

1. Passou a existir um SEGUNDO cérebro de voz — o provedor OpenAI
   Realtime (jarvis/cerebro/openai_realtime/cliente_realtime.py) — e os dois
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

# Sub-agente que descobre QUAL ferramenta atende a um pedido, lendo o
# catálogo com a descrição de cada uma. Devolve instruções ao cérebro;
# nunca executa a ferramenta — quem executa é o próprio cérebro.
from jarvis.pacotes import agente_ferramentas

# Execução de comandos de terminal com privilégio de administrador,
# local a esta máquina. Deliberadamente não conectado a rede_jarvis.
from jarvis.pacotes import admin_terminal

# Tela de configurações (visualizar/editar as variáveis do .env).
from jarvis.pacotes import configuracoes

# Identificação de espécie de planta via foto (Pl@ntNet). Exceção ao
# despacho genérico: a captura da câmera acontece no cliente, antes
# de despachar() — ver docs/INTEGRATION.md.
from jarvis.pacotes import identificacao_planta

# Segunda opinião visual independente (Mistral ou Gemini — quem
# responde é sempre o provedor OPOSTO ao cérebro de voz ativo, ver
# jarvis/pacotes/identificacao_visual/config.py). Mesma exceção de
# identificacao_planta.
from jarvis.pacotes import descricao_visual
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


# Tools que NÃO recebem a imagem do modelo: quem captura é o CLIENTE,
# que injeta imagem_bytes em args logo antes de despachar. O valor diz
# de ONDE capturar ("tela" ou "camera") — cada cliente resolve isso com
# a própria função de captura.
#
# Isto vive aqui, e não dentro de cada cliente, por causa de um BUG
# REAL: descrever_tela/descrever_camera (jarvis/pacotes/descricao_visual/)
# nasceram para o cérebro local e só o cliente local aprendeu a
# alimentá-las. Mas o pacote está em PACOTES_REGISTRADOS, que é
# global — então os três cérebros DECLARAM as duas tools, e nos
# workers do Gemini e da OpenAI elas falhavam SEMPRE, com "nenhuma
# imagem foi capturada". Sintoma relatado: pedir para o jarvis olhar
# a tela e ele responder que deu erro ao acessar a câmera e ver a
# tela — o modelo escolhia descrever_tela (que quebra) em vez da
# nativa analisar_tela (que funciona), e não tinha como saber a
# diferença.
#
# Com a lista aqui, registrar um pacote que precise de imagem passa a
# ser uma linha só, e nenhum cliente pode ficar para trás em silêncio.
# Não confundir com TOOLS_QUE_CAPTURAM_SOZINHAS: lá o pacote captura
# por dentro e o cliente só segura o mutex em volta do despacho.
TOOLS_QUE_PRECISAM_DE_IMAGEM = {
    "identificar_planta": "camera",
    "consultar_segunda_opiniao_visual": "camera",
    "descrever_tela": "tela",
    "descrever_camera": "camera",
}


# ============================================================
# VISIBILIDADE: o que o cérebro DECLARA vs. o que ele pode EXECUTAR
# ============================================================
#
# Estas duas coisas deixaram de ser a mesma. Um cérebro de voz caro
# (Gemini Live, OpenAI Realtime) paga o schema de TODA ferramenta
# declarada em TODO turno — eram 10.580 tokens de prefixo, medidos. A
# maior parte disso é manual de ferramenta que ele não vai usar neste
# turno.
#
# Então a maioria das ferramentas deixou de ser declarada: o cérebro
# descobre a certa com buscar_ferramenta e a executa por
# executar_ferramenta (jarvis/pacotes/agente_ferramentas/). Ela
# continua REGISTRADA e executável — só não ocupa espaço no prefixo.
#
# O QUE NUNCA PODE SER OCULTADO, e por quê:
#
# 1. As NATIVAS dos clientes de voz. Elas não são despachadas por
#    pacote nenhum: vivem dentro do worker e dependem da sessão viva.
#    Esta lista nem as enxerga — ela só fala de pacotes.
#
# 2. As três listas acima (TOOLS_QUE_PRECISAM_DE_IMAGEM,
#    TOOLS_SILENCIOSAS, TOOLS_QUE_CAPTURAM_SOZINHAS). Os dois workers
#    decidem pelo NOME DA FUNÇÃO QUE O MODELO CHAMOU se capturam a
#    imagem, se seguram o mutex visual e se descartam o áudio do
#    turno. Chamadas por executar_ferramenta, o nome que chega ao
#    worker é "executar_ferramenta" e os três comportamentos sumiriam
#    EM SILÊNCIO — que é exatamente o bug documentado logo acima em
#    TOOLS_QUE_PRECISAM_DE_IMAGEM (pedir para olhar a tela e ouvir que
#    deu erro na câmera). Elas continuam declaradas, e o cérebro as
#    chama direto.
#
# 3. As tools do PRÓPRIO agente_ferramentas. Esconder a porta de
#    entrada atrás dela mesma tranca o cérebro do lado de fora.
FERRAMENTAS_SEMPRE_DECLARADAS = (
    "buscar_ferramenta",
    "executar_ferramenta",
    "ler_instrucao_ferramenta",
)


def nomes_de_pacote():
    """Todo nome de ferramenta exposto por um pacote registrado."""
    nomes = set()

    for pacote in PACOTES_REGISTRADOS:
        try:
            declaracoes = pacote.obter_function_declarations()

        except Exception:
            continue

        nomes.update(declaracao.name for declaracao in declaracoes)

    return nomes


def ferramentas_ocultas():
    """
    As ferramentas de pacote que NÃO vão no prefixo do cérebro —
    alcançáveis por buscar_ferramenta + executar_ferramenta.

    DERIVADA, nunca escrita à mão: é o conjunto de pacote menos as
    exceções acima. Um pacote novo entra aqui sozinho e já nasce
    barato; um pacote novo que precise de imagem, de mutex ou de
    silêncio entra na lista certa mais acima e é automaticamente
    poupado daqui.
    """
    excecoes = (
        set(TOOLS_QUE_PRECISAM_DE_IMAGEM)
        | set(TOOLS_SILENCIOSAS)
        | set(TOOLS_QUE_CAPTURAM_SOZINHAS)
        | set(FERRAMENTAS_SEMPRE_DECLARADAS)
    )

    return nomes_de_pacote() - excecoes
