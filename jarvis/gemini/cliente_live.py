# asyncio permite executar várias tarefas assíncronas ao mesmo tempo.
# Neste arquivo, ele coordena microfone, recebimento de áudio,
# reprodução da resposta e chamadas de funções do Gemini Live.
import asyncio
# contextlib.asynccontextmanager monta _mutex_funcao_visual() — ver
# essa função, logo depois de processar_funcao_visual.
import contextlib
# concurrent.futures fornece o ThreadPoolExecutor exclusivo da
# reprodução de áudio — ver reproduzir_audio.
import concurrent.futures
# time é utilizado para controlar intervalos e medir o tempo
# entre chamadas de funções visuais.
import time
# os é usado só para extrair o nome do arquivo do caminho completo
# de um anexo, ao ler de volta um rascunho de email pendente.
import os
# winsound toca um beep local, sem depender do Gemini, assim que a
# chamada conecta — ver FREQUENCIA_BEEP_CHAMADA_INICIADA logo abaixo.
import winsound
# collections.deque guarda, sob DEBUG_TIMING_FILA_SAIDA, o instante em
# que cada bloco de áudio de resposta entrou em fila_saida — usado só
# pra medir o atraso fila->reprodução (ver _debug_fila_timestamps).
import collections

# Lê config.json (raiz do projeto) e diz se o usuário pode interromper
# a fala do jarvis falando por cima — ver jarvis/nucleo/preferencias.py e
# docs/INTEGRATION.md, seção "Interrupção de fala (config.json)".
from jarvis.nucleo.preferencias import interrupcao_ativa

# Todo texto de instrução enviado ao Gemini a partir deste arquivo
# (instrução de sistema, bloco de autenticação, anúncio espontâneo,
# cruzamento de segunda opinião, análise pontual de imagem) mora
# centralizado em jarvis/nucleo/prompts/ — ver o cabeçalho daquele
# módulo pra critério e organização.
from jarvis.nucleo import prompts

# array converte os bytes de áudio em amostras numéricas.
# Isso permite calcular o nível de volume da voz do ALFRED.
from array import array

# sounddevice captura o áudio do microfone e reproduz
# o áudio recebido do Gemini.
import sounddevice as sd

# QThread executa o cliente Gemini Live em uma thread separada,
# evitando que a interface PySide6 fique travada.
# Signal permite enviar status, erros e níveis de áudio para a interface.
from PySide6.QtCore import QThread, Signal
# genai é o cliente oficial usado para se conectar à API do Gemini.
from google import genai
# types contém as estruturas usadas pela API,
# como configurações, ferramentas, conteúdos, partes e respostas.
from google.genai import types

# Importa as configurações centrais do projeto,
# incluindo chave da API, modelo Live e voz escolhida.
from jarvis.nucleo.config import (
    EXIGIR_AUTENTICACAO,
    GEMINI_API_KEY,
    GEMINI_LIVE_MODEL,
    GEMINI_VOICE,
    TIMEOUT_INATIVIDADE_SEGUNDOS,
)

# Função responsável por capturar, em bytes, o monitor onde o
# cursor do mouse está agora (não o monitor principal fixo) — usada
# tanto na análise pontual de tela quanto na visualização contínua
# local, já que o usuário tem vários monitores e o que importa é o
# que ele está de fato olhando/mostrando no momento.
from jarvis.servicos.visao.captura_tela import (
    capturar_monitor_do_cursor_bytes,
    salvar_print_bytes,
)
# Função responsável por capturar a webcam e retornar a imagem em
# bytes, e função responsável por salvar esses bytes em disco (mesmo
# padrão de salvar_print_bytes, ver jarvis/servicos/visao/captura_camera.py).
from jarvis.servicos.visao.captura_camera import capturar_camera_bytes, salvar_foto_bytes
# Classe responsável pelo loop de captura contínua da tela.
from jarvis.servicos.visao.monitor_continuo import MonitorTelaContinuo

# Função responsável por enviar emails via SMTP.
from jarvis.servicos.email.remetente import enviar_email
# Função responsável por ler emails da caixa de entrada via IMAP.
from jarvis.servicos.email.leitor import ler_emails, baixar_anexo

# Descobre o arquivo selecionado na janela do Explorer em primeiro
# plano — e, na falta dela, na própria Área de Trabalho — usado pelo
# fluxo "envie este arquivo que eu selecionei" de preparar_email. Não
# expõe nenhuma tool de voz própria (por isso não entra em
# PACOTES_REGISTRADOS — ver docs/INTEGRATION.md, seção
# "explorador_windows"), é chamado diretamente igual
# capturar_camera_bytes().
from jarvis.pacotes import explorador_windows

# Pacote isolado com toda a lógica de comunicação e comando remoto
# entre instâncias do jarvis via MQTT (ver jarvis/pacotes/rede_jarvis/__init__.py
# para o ponto de entrada e a lista de funções expostas).
from jarvis.pacotes import rede_jarvis

# Pacote isolado com o controle de dispositivos de casa inteligente
# (Tuya, por enquanto) — ver jarvis/pacotes/casa_inteligente/__init__.py.
from jarvis.pacotes import casa_inteligente

# Pacote isolado com a delegação de tarefas de texto pontuais pra
# outras APIs de LLM (Groq/Cerebras/OpenAI) — ver
# jarvis/pacotes/delegacao_ia/__init__.py.
from jarvis.pacotes import delegacao_ia

# Pacote isolado com execução de comandos de terminal com privilégio
# de administrador, local a esta máquina — ver
# jarvis/pacotes/admin_terminal/__init__.py. Deliberadamente não conectado a
# rede_jarvis (comando remoto entre máquinas) nesta etapa.
from jarvis.pacotes import admin_terminal

# Pacote isolado com a tela de configurações (visualizar/editar as
# variáveis do .env) — ver jarvis/pacotes/configuracoes/__init__.py. despachar()
# aqui só emite um sinal (ver jarvis/nucleo/sinalizador.py); a
# janela em si é criada na thread principal, conectada em
# main.py.
from jarvis.pacotes import configuracoes

# Pacote isolado com identificação de espécie de planta via foto,
# usando a API especializada Pl@ntNet em vez da visão geral do
# Gemini — ver jarvis/pacotes/identificacao_planta/__init__.py. A única exceção ao
# padrão genérico de despacho: a captura de câmera precisa acontecer
# aqui no cliente antes de despachar() (ver
# processar_chamada_de_funcao logo abaixo e docs/INTEGRATION.md, seção
# "identificacao_planta").
from jarvis.pacotes import identificacao_planta

# Pacote isolado com uma segunda opinião visual independente
# (Mistral) para identificação de objeto genérico (não plantas) —
# ver jarvis/pacotes/identificacao_visual/__init__.py. Mesma exceção de
# identificacao_planta (captura de câmera feita aqui antes de
# despachar()), mais um parâmetro real (pergunta) vindo do Gemini.
from jarvis.pacotes import identificacao_visual

# Pacote isolado com as janelas de chat de texto e envio de arquivo,
# conectadas à MESMA sessão Live em andamento — ver
# jarvis/pacotes/chat_jarvis/__init__.py. Mesmo padrão de configuracoes (despachar()
# só emite sinal), mais uma ponte thread-safe extra (ver
# enviar_texto_da_ui/enviar_imagem_da_ui logo abaixo e
# docs/INTEGRATION.md, seção "chat_jarvis") pro texto digitado/arquivo
# enviado chegar na sessão — esse é o único touch point deste pacote
# que passa do padrão mínimo dos outros.
from jarvis.pacotes import chat_jarvis

# Pacote isolado com abertura de aplicativo LOCAL por nome, sem
# privilégio elevado e sem lista fixa — busca automática via
# Get-StartApps (ver jarvis/pacotes/abrir_app_local/__init__.py). Diferente de
# admin_terminal (privilégio elevado, whitelist fixa de manutenção)
# e de rede_jarvis (abre app em OUTRA máquina, a pedido remoto) —
# nenhum cache ou lógica é compartilhado com nenhum dos dois.
from jarvis.pacotes import abrir_app_local

# Pacote isolado com conexão persistente ao bot do Discord e envio
# de DM pra um amigo pelo nome (ver jarvis/pacotes/discord_jarvis/__init__.py). A
# conexão precisa ficar de pé o tempo todo (não só durante um
# despachar() pontual) — por isso, além do contrato padrão, também
# precisa de iniciar_discord_jarvis() chamado uma vez no __init__ do
# worker, mesmo padrão de rede_jarvis.iniciar_rede_jarvis.
from jarvis.pacotes import discord_jarvis

# Pacote isolado com a janela de vídeo AO VIVO da webcam (ver
# jarvis/pacotes/camera_preview/__init__.py). despachar() aqui só emite um sinal
# (ver jarvis/nucleo/sinalizador.py) — mesmo padrão de
# configuracoes; a janela em si é criada/fechada na thread principal,
# conectada em main.py. Diferente de analisar_camera (um único
# frame, sem janela) e tirar_foto_camera (salva um único frame).
from jarvis.pacotes import camera_preview

# Pacote isolado que fecha um app já aberto NESTA máquina, pelo
# nome, resolvendo contra processos que já estão rodando de verdade
# (via psutil) — ver jarvis/pacotes/fechar_app/__init__.py. Tenta
# fechamento gracioso (WM_CLOSE) antes de forçar, e nunca fecha
# processos protegidos do sistema nem o próprio ALFRED.
from jarvis.pacotes import fechar_app

# Pacote isolado que cria um arquivo de texto simples por pedido de
# voz, só dentro de pastas explicitamente permitidas — ver
# jarvis/pacotes/criar_arquivo/__init__.py. Nunca sobrescreve um
# arquivo existente e nunca escreve fora da lista permitida.
from jarvis.pacotes import criar_arquivo

# Pacote isolado com controle real de navegador via Playwright (abrir
# site, buscar e tocar música no YouTube, pausar/retomar) — ver
# jarvis/pacotes/navegador_jarvis/__init__.py. Diferente de abrir_app_local (que só
# abre o programa e para por aí): aqui o jarvis controla de verdade a
# página (clica, navega, aperta tecla). A sessão do navegador (um
# browser/contexto/página do Playwright) é aberta sob demanda na
# PRIMEIRA ação pedida, não no __init__ do worker (ao contrário de
# rede_jarvis e discord_jarvis) — não faz sentido abrir um Chromium
# antes de qualquer pedido — e fica de pé entre chamadas depois disso,
# rodando numa thread de fundo com loop próprio dedicado (mesmo padrão
# de jarvis/pacotes/discord_jarvis/cliente.py), pra "pausar a música" agir na mesma
# aba onde ela foi colocada.
from jarvis.pacotes import navegador_jarvis

# Pacote isolado com a ativação por voz (palavra-chave) e o
# encerramento por inatividade — ver jarvis/pacotes/ativacao_voz/__init__.py e
# jarvis/pacotes/ativacao_voz/detector.py. Não expõe tool nenhuma (não entra em
# PACOTES_REGISTRADOS, mesmo caso de explorador_windows) — pausar()/
# retomar() são chamados diretamente aqui, ao redor do ciclo de vida
# do microfone desta própria chamada (ver executar()).
from jarvis.pacotes import ativacao_voz

# Pacote isolado que assume a conversa por voz quando a sessão do
# Gemini falha — ver jarvis/pacotes/cerebro_reserva/__init__.py. Não é
# um pacote de tools (não entra em PACOTES_REGISTRADOS): é chamado
# direto no fim de executar(), mesmo padrão de ativacao_voz.
from jarvis.pacotes import cerebro_reserva

# Sinalizador genérico (ver jarvis/nucleo/sinalizador.py) — aqui
# usado só pra ENTREGAR a transcrição da resposta falada do Gemini
# pra uma eventual janela de chat aberta (resposta_texto_recebida),
# não pra abrir janela nenhuma (isso é feito pelos pacotes acima).
from jarvis.nucleo.sinalizador import obter_sinalizador

# Todo pacote de tools isolado (rede_jarvis, casa_inteligente,
# delegacao_ia, admin_terminal, configuracoes, identificacao_planta,
# identificacao_visual, chat_jarvis, abrir_app_local,
# discord_jarvis, camera_preview, e outros que vierem depois) expõe
# obter_function_declarations()/despachar() — ver docs/INTEGRATION.md na
# raiz do projeto para o padrão completo e o trecho pronto pra
# copiar em outro arquivo cliente. Adicionar um pacote novo é só
# importar e incluir aqui, nada mais muda neste arquivo.
# Memória persistente do jarvis, agora em um vault do Obsidian (pasta
# de arquivos .md ligados por [[links]]) — ver
# jarvis/pacotes/memoria_obsidian/. As tools de memória (salvar,
# buscar, esquecer, listar) são expostas pelo contrato padrão do
# pacote; daqui só é usado o contexto inicial leve da sessão. O
# gerenciador antigo (jarvis/servicos/memoria/gerenciador.py) continua
# no projeto, mas fora do fluxo: é a origem da migração e a cópia de
# segurança do que existia antes.
from jarvis.pacotes import memoria_obsidian

PACOTES_REGISTRADOS = [
    rede_jarvis,
    casa_inteligente,
    delegacao_ia,
    admin_terminal,
    configuracoes,
    identificacao_planta,
    identificacao_visual,
    chat_jarvis,
    abrir_app_local,
    discord_jarvis,
    camera_preview,
    navegador_jarvis,
    memoria_obsidian,
    fechar_app,
    criar_arquivo,
]



# Taxa de amostragem do microfone em 16 kHz.
TAXA_ENTRADA = 16000
# Taxa de amostragem do áudio de resposta em 24 kHz.
TAXA_SAIDA = 24000
# O áudio é mono, portanto utiliza apenas um canal.
CANAIS = 1
# Quantidade de amostras processadas por bloco de áudio.
BLOCO = 1024

# Tempo de segurança, em segundos, antes de reabrir o microfone
# depois que o assistente termina de falar.
# Um valor maior ajuda computadores com retorno de áudio ou drivers lentos.
ATRASO_REABRIR_MICROFONE = 0.8

# Limite de blocos aguardando envio. Evita acúmulo excessivo
# caso o computador ou a conexão fiquem temporariamente lentos.
LIMITE_FILA_MICROFONE = 50

# Liga logs temporários de tempo no console (diagnóstico de
# travamento perceptível entre falas, relacionado à execução de
# tools) — desligado por padrão. Só ativar pontualmente pra
# investigar um travamento reportado; nunca deixar True em uso
# normal. Ver processar_chamada_de_funcao pra onde os tempos são
# medidos (despacho por pacote + tempo total de cada chamada). Não
# mede mais nada em receber_audio — desde que
# processar_chamada_de_funcao passou a rodar em asyncio.Task própria
# (ver _executar_chamada_de_funcao_com_timeout), receber_audio nunca
# mais fica bloqueado esperando uma função terminar, então não havia
# mais nada útil pra medir ali.
DEBUG_TIMING_DISPATCH = False

# Liga logs temporários de tempo no console (diagnóstico de "o
# microfone demora muito pra reabrir depois que o ALFRED fala/executa
# uma ação") — desligado por padrão, mesma convenção de
# DEBUG_TIMING_DISPATCH. Mede quanto tempo self.alfred_falando fica
# True (microfone mudo) a cada vez, do primeiro bloco de áudio
# reproduzido até liberar_microfone_apos_fala de fato zerar a flag.
# Combinado com DEBUG_TIMING_DISPATCH (que já mostra qual tool rodou
# e quanto tempo levou), dá pra ver se o microfone fica mudo por mais
# tempo do que a própria tool + a fala de resposta explicam.
DEBUG_TIMING_MICROFONE = False

# [DIAGNÓSTICO DE ATRASO EM CONVERSAS LONGAS] Liga logs temporários no
# console (mesma convenção de DEBUG_TIMING_DISPATCH/DEBUG_TIMING_MICROFONE
# — desligado por padrão, só ligar pontualmente pra investigar, nunca
# deixar True em uso normal). Investiga o relato de que, em conversas
# longas, o ALFRED para de responder por um tempo e depois "volta"
# respondendo a algo que o usuário falou bem antes — como se as
# respostas estivessem enfileiradas tocando com atraso crescente, não
# travadas de vez. Mede três coisas, sem mudar nenhum comportamento
# real: (1) o tamanho de fila_saida amostrado a cada
# INTERVALO_VIGILANCIA_SEGUNDOS (curva de crescimento durante toda a
# chamada, não só se cruzou LIMITE_FILA_SAIDA_PARADA — ver
# vigiar_travamento); (2) o atraso entre um bloco de resposta entrar em
# fila_saida (receber_audio) e ser efetivamente tocado
# (_laco_reproducao), via _debug_fila_timestamps; (3) quanto tempo cada
# resposta leva pra começar a gerar áudio depois do último bloco de
# microfone realmente enviado ao Gemini, e a fila RESIDUAL (que já
# deveria estar zerada) no início de cada turno — ver
# _debug_timestamp_ultimo_envio_mic/_debug_numero_turno em receber_audio.
# LIGADO agora, de propósito, pra esta investigação — voltar pra False
# depois de coletar os dados da chamada de reprodução, mesma disciplina
# das outras duas DEBUG_TIMING_*.
DEBUG_TIMING_FILA_SAIDA = True

# Intervalo mínimo, em segundos, entre chamadas visuais repetidas.
# Isso evita capturas duplicadas para o mesmo pedido.
COOLDOWN_FUNCAO_VISUAL = 8.0

# Intervalo entre capturas de frame durante a visualização
# contínua da tela.
INTERVALO_VISUALIZACAO_CONTINUA = 1.5

# Tempo máximo, em segundos, que a visualização contínua pode
# ficar ativa antes de se encerrar sozinha por segurança.
TIMEOUT_VISUALIZACAO_CONTINUA = 90

# Tempo máximo, em segundos, que um rascunho de email preparado por
# preparar_email fica válido aguardando confirmar_envio_email antes
# de ser descartado automaticamente — evita confirmar por engano um
# rascunho antigo que o usuário já esqueceu, numa parte totalmente
# diferente da conversa.
TIMEOUT_RASCUNHO_EMAIL = 120

# Tempo máximo, em segundos, que a última captura desta sessão
# (self.ultima_captura_caminho — um print OU uma foto, o que tiver
# sido capturado por último) continua válida pra reaproveitar em
# enviar_captura_email/enviar_captura_discord_dm/enviar_captura_remoto
# sem capturar de novo — evita reenviar uma captura velha quando o
# usuário pede "envie isso" bem depois da última captura.
TIMEOUT_ULTIMA_CAPTURA_SEGUNDOS = 300

# Frequência (Hz) e duração (ms) do beep tocado localmente (via
# winsound, sem depender do Gemini) assim que a chamada conecta e o
# microfone está prestes a começar a captar — ver o
# "async with client.aio.live.connect" em executar(). Substitui a
# antiga fala "Chamada iniciada." gerada pelo próprio modelo: aquela
# dependia de round-trip até o Gemini e da detecção de atividade de
# voz do lado do servidor pra decidir que o turno tinha "terminado",
# o que na prática demorava demais pra avisar o usuário que já podia
# falar — reportado ao vivo pelo usuário.
FREQUENCIA_BEEP_CHAMADA_INICIADA = 880
DURACAO_BEEP_CHAMADA_INICIADA_MS = 150

# Quantas chamadas de função (cada uma vinda de um resposta.tool_call)
# podem rodar ao mesmo tempo. BUG REAL corrigido: antes,
# processar_chamada_de_funcao era aguardado direto dentro do "async
# for" de receber_audio — uma função lenta ou travada (email, Discord,
# comando de terminal) bloqueava TUDO (áudio, outra função) até
# terminar. Agora cada tool_call vira sua própria asyncio.Task,
# rastreada em self.tarefas_funcao_ativas, permitindo várias rodando
# em paralelo. Esse limite existe só pra não deixar a lista crescer
# sem controle se o modelo pedir muitas funções rápido demais — ver
# receber_audio/_ao_finalizar_tarefa_funcao. Valor pequeno de
# propósito: a maioria das chamadas do dia a dia é sequencial (uma
# pergunta por vez), então isso raramente é atingido na prática.
LIMITE_TAREFAS_FUNCAO_SIMULTANEAS = 4

# Tempo máximo, em segundos, que uma única chamada de função pode
# rodar antes de ser cancelada automaticamente (sem tentar de novo —
# só informa a falha por voz). Valor único simples pra toda função,
# de propósito — nada de timeout diferente por tipo de função por
# enquanto. Ver _executar_chamada_de_funcao_com_timeout.
TIMEOUT_TAREFA_FUNCAO_SEGUNDOS = 20

# Exceção necessária ao "valor único" acima — não por preferência, mas
# porque executar_comando_admin/confirmar_comando_admin JÁ têm seu
# próprio timeout interno, bem maior e testado (ver
# jarvis/pacotes/admin_terminal/config.py: até TIMEOUT_COMANDO_LONGO_SEGUNDOS, padrão
# 300s, + MARGEM_ESPERA_TAREFA_SEGUNDOS de margem, quando
# execucao_longa=true). Se essas duas funções usassem o timeout
# genérico de 20s, este mecanismo cortaria a execução ANTES do
# comando administrativo terminar sozinho — regredindo, na prática, a
# funcionalidade de execução longa já corrigida e testada
# separadamente nesta mesma conversa. Por isso o timeout usado pra
# elas (ver _obter_timeout_funcao) é sempre o maior valor entre os
# dois, com folga — nunca o padrão genérico. Usado dentro de
# _executar_chamada_de_funcao_com_timeout.
TIMEOUTS_TAREFA_FUNCAO_POR_NOME = {
    "executar_comando_admin": (
        admin_terminal.config.TIMEOUT_COMANDO_LONGO_SEGUNDOS
        + admin_terminal.config.MARGEM_ESPERA_TAREFA_SEGUNDOS
        + 15
    ),
    "confirmar_comando_admin": (
        admin_terminal.config.TIMEOUT_COMANDO_LONGO_SEGUNDOS
        + admin_terminal.config.MARGEM_ESPERA_TAREFA_SEGUNDOS
        + 15
    ),
}

# Quanto tempo, em segundos, uma chamada de função pode rodar antes do
# jarvis mandar uma resposta provisória ("comecei, aviso quando
# terminar") e liberar a conversa pra qualquer outro assunto, em vez
# de ficar preso esperando o resultado real da função em silêncio —
# limitação do protocolo de function-calling da Live API: o modelo só
# volta a falar livremente depois de receber o tool_response daquela
# chamada. Funções mais rápidas que isso continuam respondendo do
# jeito de sempre, na hora, com o resultado real — esse aviso
# intermediário só entra quando realmente necessário. Ver
# _executar_chamada_de_funcao_com_timeout (FASE 1/FASE 2).
LIMITE_RESPOSTA_IMEDIATA_SEGUNDOS = 5

# Tempo máximo, em segundos, que qualquer envio pra sessão do Gemini
# (send_client_content ou send_realtime_input) pode esperar antes de
# ser considerado travado. BUG REAL relatado pelo usuário: a conexão
# Live pode travar silenciosamente (sem erro, sem fechar a conexão) —
# sem esse timeout, qualquer envio nela ficaria esperando pra sempre,
# travando o app inteiro (nenhuma resposta, impossível encerrar a
# chamada ou fechar o app, só pelo Gerenciador de Tarefas). Ver
# _enviar_para_sessao/monitorar_conexao/self.conexao_travada.
TIMEOUT_ENVIO_SESSAO_SEGUNDOS = 10

# Folga do buffer de saída de áudio. "high" é o padrão do próprio
# sounddevice e o que o app já usava sem dizer — explicitado aqui pra
# ficar claro que é uma escolha, e pra poder ser aumentado se a fala
# picotar. Medido nesta máquina: "low" dá 128ms de buffer (3 blocos de
# folga), "high" dá 213ms (5 blocos). Aumentar isso NÃO consome CPU
# nem memória de forma perceptível — só atrasa em milissegundos o
# começo da fala em troca de tolerar mais engasgo do sistema.
LATENCIA_SAIDA = "high"

# Tempo limite para ESCREVER um único bloco de áudio no dispositivo
# de saída. Um bloco tem BLOCO/TAXA_SAIDA = ~43ms, então 10s é ~230x
# o normal — só estoura se o dispositivo parar de consumir de vez
# (caso real: um jogo em tela cheia assumindo a placa de som em modo
# exclusivo). Sem isso, saida.write() fica preso para sempre dentro
# do asyncio.to_thread, sem lançar exceção nenhuma: a reprodução
# morre calada, o jarvis continua "respondendo" mas nada mais é
# ouvido, e fila_saida (que é ilimitada) só cresce.
TIMEOUT_ESCRITA_AUDIO_SEGUNDOS = 10

# De quanto em quanto tempo vigiar_travamento() confere os estados
# que nunca deveriam ficar presos, e por quanto tempo cada um pode
# ficar assim antes de ser reportado. Ver vigiar_travamento().
INTERVALO_VIGILANCIA_SEGUNDOS = 5.0
LIMITE_FALANDO_PRESO_SEGUNDOS = 60.0
LIMITE_FUNCAO_VISUAL_PRESA_SEGUNDOS = 120.0
LIMITE_FILA_SAIDA_PARADA = 200

# Por quanto tempo o microfone pode ficar SEM entregar um único bloco
# antes de ser considerado morto. O callback do sounddevice é chamado
# a cada BLOCO/TAXA_ENTRADA = ~64ms enquanto o stream estiver vivo,
# independente de haver silêncio ou fala (áudio bruto: silêncio é só
# zeros), então 10s equivale a ~156 blocos perdidos — não acontece
# num stream saudável.
LIMITE_MICROFONE_MUDO_SEGUNDOS = 10.0


# Classe principal responsável pela sessão em tempo real com o Gemini.
# Como herda de QThread, roda separadamente da interface gráfica.
class GeminiLiveWorker(QThread):

    # Sinal usado para enviar mensagens de status para a interface.
    status_recebido = Signal(str)
    # Sinal usado para enviar mensagens de erro para a interface.
    erro_recebido = Signal(str)
    # Sinal emitido quando a sessão termina.
    chamada_encerrada = Signal()

    # Sinal utilizado para animar a interface de acordo com o volume da voz.
    nivel_audio = Signal(float)

    # Solicita que a interface encerre a chamada
    # usando o mesmo método acionado pelo botão.
    # Sinal emitido quando o usuário pede para encerrar a chamada por voz.
    solicitou_encerramento = Signal()

    # Inicializa os estados internos do worker.
    def __init__(self):
        super().__init__()

        # Controla se a sessão continua em execução.
        self.ativo = True
        # Guardará o loop assíncrono criado pela thread.
        self.loop = None
        # Guardará a sessão ativa do Gemini Live.
        self.sessao = None

        # Indica quando o ALFRED está reproduzindo áudio.
        # Enquanto isso, o microfone é ignorado para evitar eco.
        self.alfred_falando = False

        # Lido UMA VEZ aqui, na criação do worker — não recarrega em
        # tempo real no meio de uma chamada; trocar config.json exige
        # reiniciar a chamada/app pra valer. Com False (padrão), o
        # comportamento é idêntico ao de sempre: o microfone é
        # ignorado enquanto self.alfred_falando (as três checagens em
        # enviar_microfone). Com True, essas checagens são
        # contornadas — o usuário pode falar por cima do jarvis — e
        # receber_audio passa a tratar resposta.server_content.interrupted
        # pra cortar o áudio antigo na hora. RISCO CONHECIDO E ACEITO
        # do modo True: sem fone de ouvido, o próprio áudio dos
        # alto-falantes pode ser captado pelo microfone como se fosse
        # o usuário falando (eco) — não é um bug a corrigir aqui, é
        # uma limitação deste modo simples.
        self.interrupcao_habilitada = interrupcao_ativa()

        # True quando um envio pra sessão do Gemini trava ou falha
        # (ver _enviar_para_sessao) — monitorar_conexao detecta isso e
        # encerra a chamada automaticamente, sem tentar avisar por voz
        # (um aviso por voz também é um envio pra sessão, que também
        # poderia travar do mesmo jeito).
        self.conexao_travada = False

        # [DIAGNÓSTICO DE MICROFONE] Marca o instante (time.perf_counter())
        # em que o microfone ficou mudo pela última vez — só usado sob
        # DEBUG_TIMING_MICROFONE, ver constante no topo do arquivo.
        self._debug_inicio_mudo = None

        # [DIAGNÓSTICO DE ATRASO EM CONVERSAS LONGAS] Só usado sob
        # DEBUG_TIMING_FILA_SAIDA, ver constante no topo do arquivo.
        # _debug_fila_timestamps guarda, na mesma ordem FIFO de
        # fila_saida, o instante (time.monotonic()) em que cada bloco
        # foi colocado na fila — _laco_reproducao usa popleft() ao
        # tirar cada bloco pra calcular o atraso fila->reprodução.
        # Também precisa ser esvaziado junto de fila_saida sempre que
        # ela for descartada fora do fluxo normal (ver
        # limpar_fila_saida em receber_audio), senão os dois ficam
        # dessincronizados e o atraso medido depois fica sem sentido.
        self._debug_fila_timestamps = collections.deque()
        self._debug_atraso_max_desde_tick = 0.0
        self._debug_atraso_soma_desde_tick = 0.0
        self._debug_atraso_contagem_desde_tick = 0
        # Contador de turnos (uma resposta completa do ALFRED) e
        # instante do último bloco de MICROFONE realmente enviado ao
        # Gemini (não só capturado) — usados pra medir quanto tempo
        # cada resposta leva pra começar a gerar áudio depois que o
        # usuário parou de falar, e se isso cresce com o número de
        # turnos acumulados na sessão. Ver receber_audio/enviar_microfone.
        self._debug_numero_turno = 0
        self._debug_timestamp_ultimo_envio_mic = None
        # Instante em que esta chamada começou, só pra exibir "t=Ns
        # desde o início" nos logs de diagnóstico acima.
        self._debug_inicio_chamada = time.monotonic()
        # Referência para a tarefa que libera o microfone após a fala.
        self.tarefa_liberar_microfone = None
        # Referência para a tarefa que encerra a chamada após a despedida.
        self.tarefa_encerramento = None

        # Lista de asyncio.Task, uma por resposta.tool_call em
        # andamento — permite várias chamadas de função rodando ao
        # mesmo tempo, em vez de uma de cada vez bloqueando tudo. Ver
        # LIMITE_TAREFAS_FUNCAO_SIMULTANEAS/TIMEOUT_TAREFA_FUNCAO_SEGUNDOS
        # acima e receber_audio/_ao_finalizar_tarefa_funcao.
        self.tarefas_funcao_ativas = []

        # Instante (time.monotonic()) da última atividade REAL da
        # chamada — atualizado só quando o ALFRED fala (resposta.data
        # chega) ou processa uma chamada de função (ver
        # receber_audio), nunca por ruído captado pelo microfone.
        # Usado por verificar_inatividade() pra decidir quando
        # encerrar a chamada sozinha (TIMEOUT_INATIVIDADE_SEGUNDOS).
        # Iniciado agora (não None) pra não parecer inativa desde o
        # início antes mesmo da sessão conectar.
        self.timestamp_ultima_atividade = time.monotonic()

        # Impede duas análises visuais simultâneas.
        self.executando_funcao_visual = False

        # Quando o último bloco de áudio terminou de ser escrito no
        # dispositivo de saída, e as tarefas simultâneas da chamada —
        # os dois usados só por vigiar_travamento().
        self.timestamp_ultima_reproducao = 0.0

        # Quando o callback do sounddevice entregou o último bloco de
        # microfone. 0.0 = o stream ainda não começou (vigiar_travamento
        # ignora esse caso, pra não acusar nada durante a abertura).
        self.timestamp_ultimo_bloco_microfone = 0.0

        # True quando a chamada terminou por FALHA (conexão travada,
        # tarefa morta, microfone morto) e não porque o usuário mandou
        # encerrar. Só nesse caso o cérebro reserva assume, no fim de
        # executar().
        self.encerrou_por_falha = False

        # Quantas vezes a fala foi cortada por interrupção nesta
        # chamada — ver o tratamento de server_content.interrupted em
        # receber_audio. Só faz sentido com interrupcao_habilitada.
        self.interrupcoes_na_chamada = 0

        # True enquanto o cérebro reserva está conduzindo a conversa.
        # parar() zera isto também, senão encerrar a chamada não teria
        # efeito nenhum depois da troca.
        self.reserva_ativa = False
        self.tarefas_chamada = []
        self.ultima_funcao_visual = None
        self.tempo_ultima_funcao_visual = 0.0

        # Guarda o monitor de visualização contínua da tela
        # enquanto estiver ativo. É None quando não há captura
        # contínua em andamento.
        self.monitor_tela_continuo = None

        # Acumula o texto transcrito da resposta falada em
        # andamento (ver receber_audio) até o turno terminar, quando
        # é entregue de uma vez pra uma eventual janela de chat
        # aberta — ver jarvis.nucleo.sinalizador.resposta_texto_recebida.
        self._buffer_transcricao_atual = ""

        # Rascunho de email preparado por preparar_email, aguardando
        # confirmar_envio_email — None quando não há nenhum pendente.
        # Só existe um por vez: uma nova chamada de preparar_email
        # substitui o anterior (ver o dispatch de preparar_email
        # abaixo). Dict com destinatario/assunto/corpo/caminho_anexo/
        # criado_em (usado pra checar TIMEOUT_RASCUNHO_EMAIL).
        self.email_pendente = None

        # Caminho e instante (time.monotonic()) da última captura
        # visual salva em disco nesta sessão — print OU foto, o que
        # tiver acontecido por último (salvar_print_tela,
        # tirar_foto_camera, ou indiretamente por
        # enviar_captura_email/enviar_captura_discord_dm/
        # enviar_captura_remoto quando elas mesmas capturam). "Última
        # captura" única, não uma pra cada tipo — reaproveitada pelas
        # três tools de envio quando o pedido é só "envie isso"/"envie
        # este print"/"envie essa foto", sem precisar capturar de novo
        # (ver _obter_ou_capturar_ultima_captura e
        # TIMEOUT_ULTIMA_CAPTURA_SEGUNDOS).
        self.ultima_captura_caminho = None
        self.ultima_captura_timestamp = None

        # Sobe (ou apenas reconecta os callbacks de, se já estiver de
        # pé) o listener de comandos remotos via MQTT. Roda aqui —
        # no construtor, chamado pela thread da UI antes de .start() —
        # para que fique de pé mesmo fora de uma chamada de voz ativa,
        # e para que o pacote crie seus componentes Qt na thread certa.
        rede_jarvis.iniciar_rede_jarvis(
            callback_falar=self._falar_espontaneamente,
            callback_frame_remoto=self._receber_frame_remoto,
        )

        # Registra o mesmo callback genérico de fala espontânea para
        # admin_terminal anunciar por voz o resultado de um comando
        # confirmado pela notificação do Windows (a confirmação por
        # voz não precisa disso — ver jarvis/pacotes/admin_terminal/confirmacao.py).
        # Não há acoplamento entre os dois pacotes: cada um só recebe
        # uma referência a este método do worker.
        admin_terminal.iniciar_admin_terminal(
            callback_falar=self._falar_espontaneamente,
        )

        # Sobe (ou apenas confirma que já está de pé) a conexão
        # persistente com o bot do Discord — idempotente, mesmo
        # motivo de rede_jarvis acima: GeminiLiveWorker é recriado a
        # cada chamada, mas a conexão com o Discord deve continuar
        # viva independente disso.
        discord_jarvis.iniciar_discord_jarvis()

    # Callback genérico usado por pacotes isolados (rede_jarvis,
    # admin_terminal) para o ALFRED anunciar algo por voz de forma
    # espontânea (fora do fluxo normal pergunta-resposta), mesmo que
    # o evento tenha chegado fora de uma sessão Live ativa nesta
    # instância específica — nesse caso self.sessao é None e o método
    # simplesmente não faz nada, deixando outro canal (ex: a
    # notificação do Windows) como única confirmação visível.
    def _falar_espontaneamente(self, texto):
        if not self.loop or not self.sessao:
            return

        asyncio.run_coroutine_threadsafe(
            self._enviar_anuncio_espontaneo(texto),
            self.loop,
        )

    # Envolve QUALQUER envio pra sessão do Gemini (send_client_content
    # ou send_realtime_input, passado aqui como corrotina já
    # construída e ainda não aguardada — ex:
    # self._enviar_para_sessao(self.sessao.send_client_content(...)))
    # com um timeout. Se travar (ou falhar por qualquer outro motivo),
    # marca self.conexao_travada — monitorar_conexao detecta isso e
    # encerra a chamada sozinha, SEM tentar avisar por voz (isso
    # também seria um envio pra sessão, que também poderia travar).
    # Sempre repropaga a exceção original (TimeoutError ou a que a
    # corrotina lançou), pra quem chamou continuar tratando do jeito
    # que já tratava antes — este método só adiciona o timeout e o
    # registro do travamento, nunca engole o erro.
    async def _enviar_para_sessao(self, corrotina):
        try:
            return await asyncio.wait_for(
                corrotina,
                timeout=TIMEOUT_ENVIO_SESSAO_SEGUNDOS,
            )

        except asyncio.TimeoutError:
            print(
                "[CONEXÃO] Envio pra sessão do Gemini travou "
                f"(timeout de {TIMEOUT_ENVIO_SESSAO_SEGUNDOS}s) — "
                "marcando a conexão como travada."
            )
            self.conexao_travada = True
            raise

        except Exception as erro:
            print(
                f"[CONEXÃO] Envio pra sessão do Gemini falhou: "
                f"{erro!r} — marcando a conexão como travada."
            )
            self.conexao_travada = True
            raise

    async def _enviar_anuncio_espontaneo(self, texto):
        await self._enviar_para_sessao(
            self.sessao.send_client_content(
                turns=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part(
                                text=prompts.ANUNCIO_ESPONTANEO.format(
                                    texto=texto
                                )
                            )
                        ],
                    )
                ],
                turn_complete=True,
            )
        )

    # Usado por identificar_planta e consultar_segunda_opiniao_visual
    # (chamado de processar_chamada_de_funcao, antes do tool_response
    # ser enviado — mesma ordem já usada por
    # analisar_tela/analisar_camera via processar_funcao_visual):
    # reenvia a MESMA imagem já usada na consulta a uma fonte externa
    # (Pl@ntNet ou Mistral), pedindo pro Gemini olhar a imagem com a
    # própria visão e comparar com o resultado externo — em vez de só
    # repassar esse resultado sem checagem.
    async def enviar_imagem_para_cruzamento(
        self,
        imagem_bytes,
        resultado_externo,
        contexto,
    ):
        if not self.sessao or not imagem_bytes:
            return

        await self._enviar_para_sessao(
            self.sessao.send_client_content(
                turns=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part(
                                inline_data=types.Blob(
                                    data=imagem_bytes,
                                    mime_type="image/jpeg",
                                )
                            ),
                            types.Part(
                                text=prompts.CRUZAMENTO_SEGUNDA_OPINIAO.format(
                                    contexto=contexto,
                                    resultado_externo=resultado_externo,
                                )
                            ),
                        ],
                    )
                ],
                turn_complete=True,
            )
        )

    # Chamado pela janela de chat (thread principal — ver
    # jarvis/ui/janela_chat.py e main.py) pra mandar um texto digitado
    # pelo usuário pra sessão Live ativa. Caminho inverso de
    # _falar_espontaneamente (que é o worker "falando" pra fora) —
    # aqui é de fora pra dentro, mas a mesma técnica de ponte
    # (run_coroutine_threadsafe no loop do worker). Retorna False sem
    # fazer nada se não houver sessão ativa (chamada terminou ou
    # ainda não começou), pra quem chamou poder avisar o usuário em
    # vez de perder a mensagem silenciosamente.
    #
    # Usa send_realtime_input(text=...) — NÃO send_client_content,
    # ao contrário de _enviar_anuncio_espontaneo/
    # enviar_imagem_para_cruzamento acima. A documentação oficial do
    # modelo configurado em jarvis/nucleo/config.py
    # (gemini-3.1-flash-live-preview) diz que send_client_content só
    # é garantido pra semear o histórico inicial da sessão, não pra
    # atualizações durante a conversa — "to send text updates during
    # the conversation, use send_realtime_input instead". Os usos
    # existentes de send_client_content acima já funcionam na
    # prática e não foram tocados (decisão consciente, não descoberta
    # nesta tarefa — ver CLAUDE.md), mas este código é novo, então
    # usa o mecanismo oficialmente correto pra esse modelo desde o
    # início.
    def enviar_texto_da_ui(self, texto):
        if not self.loop or not self.sessao:
            return False

        asyncio.run_coroutine_threadsafe(
            self._enviar_texto_da_ui_para_sessao(texto),
            self.loop,
        )

        return True

    async def _enviar_texto_da_ui_para_sessao(self, texto):
        await self._enviar_para_sessao(
            self.sessao.send_realtime_input(
                text=texto,
            )
        )

    # Mesma ponte que enviar_texto_da_ui, pra uma imagem vinda da
    # janela de chat ou de envio de arquivo (arrastar-e-soltar ou
    # diálogo de seleção) — ver jarvis/ui/janela_envio_arquivo.py. Também
    # usa send_realtime_input, agora com o campo video (mesmo campo
    # já usado por _injetar_frame_remoto pra frames de visualização
    # remota) em vez de media/inline_data — send_realtime_input não
    # combina mídia e texto numa única chamada, por isso o texto de
    # contexto (se houver) é uma segunda chamada logo em seguida.
    def enviar_imagem_da_ui(self, imagem_bytes, mime_type, texto_contexto=None):
        if not self.loop or not self.sessao:
            return False

        asyncio.run_coroutine_threadsafe(
            self._enviar_imagem_da_ui_para_sessao(
                imagem_bytes,
                mime_type,
                texto_contexto,
            ),
            self.loop,
        )

        return True

    async def _enviar_imagem_da_ui_para_sessao(
        self,
        imagem_bytes,
        mime_type,
        texto_contexto,
    ):
        await self._enviar_para_sessao(
            self.sessao.send_realtime_input(
                video=types.Blob(
                    data=imagem_bytes,
                    mime_type=mime_type,
                )
            )
        )

        if texto_contexto:
            await self._enviar_para_sessao(
                self.sessao.send_realtime_input(
                    text=texto_contexto,
                )
            )

    # Callback usado pelo pacote rede_jarvis para injetar, na sessão
    # Live local, cada frame recebido de uma visualização remota
    # (iniciada por esta máquina em outra). Reaproveita exatamente o
    # mesmo mecanismo de streaming usado pela visualização contínua
    # local (send_realtime_input).
    def _receber_frame_remoto(self, frame_bytes, origem):
        if not self.loop or not self.sessao:
            return

        asyncio.run_coroutine_threadsafe(
            self._injetar_frame_remoto(frame_bytes),
            self.loop,
        )

    async def _injetar_frame_remoto(self, frame_bytes):
        await self._enviar_para_sessao(
            self.sessao.send_realtime_input(
                video=types.Blob(
                    data=frame_bytes,
                    mime_type="image/jpeg",
                )
            )
        )

    # Método chamado automaticamente quando a thread é iniciada.
    def run(self):
        try:
            # Cria e executa o ambiente assíncrono desta thread.
            asyncio.run(
                self.executar()
            )

        except Exception as erro:
            self.erro_recebido.emit(
                str(erro)
            )

        # Este bloco sempre é executado, mesmo se ocorrer erro.
        finally:
            self.nivel_audio.emit(
                0.0
            )

            self.chamada_encerrada.emit()

    # Configura o Gemini Live, cria as filas de áudio
    # e mantém a sessão funcionando enquanto o worker estiver ativo.
    async def executar(self):
        # Para o detector de ativação por voz (jarvis/pacotes/ativacao_voz/) e libera
        # o microfone dele ANTES de qualquer coisa nesta chamada — os
        # dois nunca podem ter o microfone aberto ao mesmo tempo (ver
        # jarvis/pacotes/ativacao_voz/detector.py). Bloqueia até o microfone estar
        # de fato livre. Idempotente: não faz nada se a chamada não
        # começou por ativação por voz (detector já parado, ou nunca
        # chegou a iniciar por falha ao carregar o modelo/abrir o
        # microfone).
        ativacao_voz.pausar()

        # Impede a conexão quando a chave da API não foi configurada.
        if not GEMINI_API_KEY:
            raise ValueError(
                "GEMINI_API_KEY não encontrada no arquivo .env"
            )

        # Obtém o loop assíncrono atual para permitir chamadas
        # futuras vindas dos botões da interface.
        self.loop = asyncio.get_running_loop()

        # Cria o cliente autenticado do Gemini.
        client = genai.Client(
            api_key=GEMINI_API_KEY
        )

        # Lista de ferramentas nativas que o modelo pode chamar por
        # voz. Cada FunctionDeclaration descreve quando e como usar
        # uma função. As tools dos pacotes registrados (ver
        # PACOTES_REGISTRADOS e docs/INTEGRATION.md) são adicionadas a
        # essa lista logo abaixo — não ficam listadas aqui.
        function_declarations_nativas = [
                    types.FunctionDeclaration(
                        name="analisar_tela",
                        description=(
                            "Use esta função somente quando o usuário pedir "
                            "explicitamente para analisar, ver, observar ou "
                            "explicar a tela do computador. Só descreve o que "
                            "está sendo mostrado — nunca salva nada em disco. "
                            "Se o usuário pedir pra salvar, guardar ou tirar "
                            "um print, use salvar_print_tela em vez desta. "
                            "Não use espontaneamente e não repita para o "
                            "mesmo pedido."
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="salvar_print_tela",
                        description=(
                            "Captura o monitor onde o cursor do mouse está "
                            "agora e SALVA a imagem em arquivo (pasta "
                            "JarvisRecebidos na Área de Trabalho) — diferente "
                            "de analisar_tela, que só descreve o que está "
                            "sendo mostrado, sem gravar nada em disco. Use "
                            "esta função somente quando o usuário pedir "
                            "explicitamente para salvar, guardar, tirar e "
                            "guardar um print, ou capturar e salvar a tela. "
                            "Se o usuário só pedir pra você ver, olhar ou "
                            "analisar a tela, use analisar_tela em vez "
                            "desta — não salve nada nesse caso. Não use "
                            "espontaneamente."
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="analisar_camera",
                        description=(
                            "Use esta função somente quando o usuário pedir "
                            "explicitamente para analisar, ver, observar ou "
                            "explicar a webcam ou câmera. Só descreve o que "
                            "está sendo mostrado — nunca salva nada em disco. "
                            "Se o usuário pedir pra tirar, salvar ou guardar "
                            "uma foto, use tirar_foto_camera em vez desta. "
                            "Não use espontaneamente e não repita para o "
                            "mesmo pedido."
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="tirar_foto_camera",
                        description=(
                            "Captura uma imagem da webcam e SALVA a foto em "
                            "arquivo (pasta JarvisRecebidos na Área de "
                            "Trabalho) — diferente de analisar_camera, que só "
                            "descreve o que está sendo mostrado, sem gravar "
                            "nada em disco. Use esta função somente quando o "
                            "usuário pedir explicitamente para tirar, salvar "
                            "ou guardar uma foto, ou fotografar algo pela "
                            "câmera. Se o usuário só pedir pra você ver, "
                            "olhar ou analisar a câmera, use analisar_camera "
                            "em vez desta — não salve nada nesse caso. Não "
                            "use espontaneamente."
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="iniciar_visualizacao_continua",
                        description=(
                            "Use esta função somente quando o usuário pedir "
                            "explicitamente para você acompanhar, ver "
                            "continuamente ou observar o que ele está fazendo "
                            "na tela, como em 'veja o que eu preciso que você "
                            "faça' ou 'acompanhe minha tela'. Inicia uma "
                            "captura contínua de frames da tela até que o "
                            "usuário indique que terminou. Não use "
                            "espontaneamente e não use no lugar de "
                            "analisar_tela quando o pedido for de uma "
                            "análise única."
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="parar_visualizacao_continua",
                        description=(
                            "Use esta função somente quando o usuário pedir "
                            "explicitamente para parar, encerrar ou finalizar "
                            "a visualização contínua da tela, como em "
                            "'pronto, acabei de mostrar como fazer' ou 'pode "
                            "parar de ver minha tela'. Encerra a captura "
                            "contínua iniciada por iniciar_visualizacao_continua. "
                            "Não use espontaneamente."
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="preparar_email",
                        description=(
                            "PRIMEIRO passo pra enviar um email — NÃO "
                            "envia nada, só monta um rascunho pendente de "
                            "confirmação. Use somente depois que o "
                            "usuário tiver informado claramente o "
                            "destinatário, o assunto e o conteúdo. Nunca "
                            "invente, complete ou adivinhe nenhum desses "
                            "três. Se alguma informação estiver faltando, "
                            "peça ao usuário antes de chamar a função. "
                            "Depois de chamar esta função, leia o "
                            "resultado dela em voz alta pro usuário "
                            "(destinatário, assunto, conteúdo e anexo se "
                            "houver) terminando com uma pergunta clara "
                            "tipo 'posso enviar assim?', e PARE — não "
                            "chame nenhuma outra função neste mesmo "
                            "turno. Só depois que o usuário responder, na "
                            "fala seguinte dele, chame "
                            "confirmar_envio_email. Se o usuário pedir "
                            "pra anexar 'este arquivo', 'esse arquivo "
                            "aqui' ou 'o arquivo que eu selecionei' (se "
                            "referindo ao Explorer do Windows), defina "
                            "usar_arquivo_selecionado=true — o anexo é "
                            "descoberto automaticamente, não peça o "
                            "caminho do arquivo ao usuário nesse caso. Se "
                            "o usuário pedir pra preparar outro email "
                            "antes de confirmar o anterior, chame esta "
                            "função de novo normalmente — o rascunho "
                            "anterior é substituído pelo novo."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "destinatario": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Endereço de email do destinatário, "
                                        "informado explicitamente pelo "
                                        "usuário."
                                    ),
                                ),
                                "assunto": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Assunto do email, informado ou "
                                        "confirmado pelo usuário."
                                    ),
                                ),
                                "corpo": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Conteúdo do email, informado ou "
                                        "confirmado pelo usuário."
                                    ),
                                ),
                                "usar_arquivo_selecionado": types.Schema(
                                    type="BOOLEAN",
                                    description=(
                                        "Verdadeiro somente se o usuário "
                                        "pediu pra anexar o arquivo que "
                                        "está selecionado no Explorer do "
                                        "Windows agora (ex: 'envie este "
                                        "arquivo que eu selecionei'). "
                                        "Padrão: falso."
                                    ),
                                ),
                            },
                            required=[
                                "destinatario",
                                "assunto",
                                "corpo",
                            ],
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="confirmar_envio_email",
                        description=(
                            "SEGUNDO e último passo pra enviar um email — "
                            "só use depois de ter chamado preparar_email, "
                            "lido o rascunho em voz alta pro usuário, e "
                            "literalmente ouvido a resposta dele na fala "
                            "seguinte. Nunca chame isso com confirmar=true "
                            "sem ter ouvido uma resposta afirmativa clara "
                            "depois da leitura do rascunho — não assuma "
                            "concordância. Use confirmar=true se o "
                            "usuário confirmou o envio (ex: 'sim', 'pode "
                            "mandar', 'envia'); confirmar=false se ele "
                            "negou ou pediu pra cancelar (ex: 'não', "
                            "'cancela', 'espera'). Se não houver nenhum "
                            "rascunho pendente no momento, a função avisa "
                            "isso — não invente nem repita um envio "
                            "antigo."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "confirmar": types.Schema(
                                    type="BOOLEAN",
                                    description=(
                                        "Verdadeiro se o usuário confirmou "
                                        "o envio, falso se negou ou "
                                        "cancelou."
                                    ),
                                ),
                            },
                            required=[
                                "confirmar",
                            ],
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="ler_emails",
                        description=(
                            "Use esta função somente quando o usuário pedir "
                            "explicitamente para ler, checar, verificar ou "
                            "mostrar os emails da caixa de entrada ou do "
                            "spam. Lista os emails mais recentes com "
                            "remetente, assunto e data, sem abrir o "
                            "conteúdo completo de nenhum deles. Não use "
                            "espontaneamente e não repita para o mesmo "
                            "pedido."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "quantidade": types.Schema(
                                    type="INTEGER",
                                    description=(
                                        "Quantidade de emails mais recentes "
                                        "a listar. Use 5 se o usuário não "
                                        "especificar um número."
                                    ),
                                ),
                                "apenas_nao_lidos": types.Schema(
                                    type="BOOLEAN",
                                    description=(
                                        "Verdadeiro somente se o usuário "
                                        "pedir especificamente pelos emails "
                                        "não lidos. Caso contrário, falso."
                                    ),
                                ),
                                "pasta": types.Schema(
                                    type="STRING",
                                    enum=[
                                        "INBOX",
                                        "SPAM",
                                    ],
                                    description=(
                                        "Use INBOX para a caixa de entrada "
                                        "normal. Use SPAM somente quando o "
                                        "usuário pedir explicitamente para "
                                        "ver o spam, lixo eletrônico ou "
                                        "emails indesejados. Use INBOX se "
                                        "o usuário não especificar."
                                    ),
                                ),
                            },
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="baixar_anexo_email",
                        description=(
                            "Baixa o(s) anexo(s) de um email específico da "
                            "caixa de entrada para uma pasta local. Use "
                            "somente quando o usuário pedir explicitamente "
                            "para baixar, salvar ou guardar um anexo/arquivo "
                            "de um email (ex: 'baixa o anexo do email que o "
                            "fulano mandou', 'salva o arquivo do último "
                            "email', 'baixa o anexo do email sobre a "
                            "reunião'). Nunca invente ou adivinhe qual "
                            "email é — se a função retornar mais de um "
                            "candidato, pergunte ao usuário qual deles "
                            "antes de chamar de novo. O conteúdo baixado "
                            "nunca é aberto ou executado automaticamente, "
                            "só salvo em disco."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "criterio": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Como o usuário descreveu o email: "
                                        "remetente, assunto, ou 'mais "
                                        "recente'/'último' quando o usuário "
                                        "só quer o anexo mais recente "
                                        "disponível sem especificar qual "
                                        "email."
                                    ),
                                ),
                            },
                            required=[
                                "criterio",
                            ],
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="enviar_captura_email",
                        description=(
                            "Captura um print da tela OU uma foto da "
                            "câmera (ou reaproveita a última captura já "
                            "feita, se recente — print ou foto, o que "
                            "tiver sido capturado por último) e prepara "
                            "um email com ela anexada — MESMO fluxo de "
                            "confirmação de preparar_email, nunca envia "
                            "direto. Use quando o usuário pedir pra "
                            "tirar/enviar um print ou uma foto por email "
                            "(ex: 'tire um print e manda por email pro "
                            "fulano', 'tira uma foto e envia pro meu "
                            "email', 'envia esse print/essa foto pro meu "
                            "email'). destinatario é sempre obrigatório e "
                            "nunca deve ser inventado. assunto e corpo "
                            "são opcionais — se o usuário não "
                            "especificar, um padrão razoável é usado, já "
                            "que ele pode não ter dado esses detalhes ao "
                            "pedir isso rapidamente. Depois de chamar "
                            "esta função, o fluxo de confirmação normal "
                            "do email continua igual — leia o rascunho "
                            "de volta e espere a resposta do usuário "
                            "antes de chamar confirmar_envio_email."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "destinatario": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Endereço de email do "
                                        "destinatário, informado "
                                        "explicitamente pelo usuário."
                                    ),
                                ),
                                "assunto": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Assunto do email. Opcional — "
                                        "deixe vazio se o usuário não "
                                        "especificar."
                                    ),
                                ),
                                "corpo": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Conteúdo do email. Opcional — "
                                        "deixe vazio se o usuário não "
                                        "especificar."
                                    ),
                                ),
                                "capturar_novo": types.Schema(
                                    type="BOOLEAN",
                                    description=(
                                        "Verdadeiro se o usuário pediu "
                                        "explicitamente pra tirar um "
                                        "print ou uma foto NOVA agora "
                                        "(ex: 'tire um print e manda...', "
                                        "'tira uma foto e envia...'). "
                                        "Falso (ou omitido) se ele está "
                                        "se referindo a uma captura já "
                                        "feita antes (ex: 'envie este "
                                        "print', 'manda essa foto', "
                                        "'envie isso')."
                                    ),
                                ),
                                "tipo_captura": types.Schema(
                                    type="STRING",
                                    enum=["print", "foto"],
                                    description=(
                                        "'print' ou 'foto', conforme o "
                                        "usuário pediu. Só é usado quando "
                                        "capturar_novo é verdadeiro, ou "
                                        "quando não há nenhuma captura "
                                        "recente pra reaproveitar — nesses "
                                        "casos a função precisa saber o "
                                        "que capturar. Se capturar_novo "
                                        "for falso e já existir uma "
                                        "captura recente, pode deixar "
                                        "vazio."
                                    ),
                                ),
                            },
                            required=[
                                "destinatario",
                            ],
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="enviar_captura_discord_dm",
                        description=(
                            "Captura um print da tela OU uma foto da "
                            "câmera (ou reaproveita a última captura já "
                            "feita, se recente) e manda direto (DM) pro "
                            "amigo especificado pelo Discord, com a "
                            "captura anexada — mesma resolução de "
                            "contato de enviar_dm_discord. Use quando o "
                            "usuário pedir pra tirar/enviar um print ou "
                            "uma foto pra alguém pelo Discord (ex: 'tire "
                            "um print e manda pro Luan no discord', "
                            "'tira uma foto e manda pro Luan'). "
                            "nome_amigo é sempre obrigatório. texto é "
                            "opcional. Se a função retornar mais de um "
                            "candidato parecido, pergunte qual antes de "
                            "chamar de novo — nunca escolha sozinho."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "nome_amigo": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Nome do amigo, exatamente como "
                                        "o usuário falou."
                                    ),
                                ),
                                "texto": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Mensagem a acompanhar a "
                                        "captura. Opcional."
                                    ),
                                ),
                                "capturar_novo": types.Schema(
                                    type="BOOLEAN",
                                    description=(
                                        "Verdadeiro se o usuário pediu "
                                        "explicitamente pra tirar um "
                                        "print ou uma foto NOVA agora. "
                                        "Falso (ou omitido) se ele está "
                                        "se referindo a uma captura já "
                                        "feita antes."
                                    ),
                                ),
                                "tipo_captura": types.Schema(
                                    type="STRING",
                                    enum=["print", "foto"],
                                    description=(
                                        "'print' ou 'foto', conforme o "
                                        "usuário pediu. Só é usado quando "
                                        "capturar_novo é verdadeiro, ou "
                                        "quando não há nenhuma captura "
                                        "recente pra reaproveitar. Se "
                                        "capturar_novo for falso e já "
                                        "existir uma captura recente, "
                                        "pode deixar vazio."
                                    ),
                                ),
                            },
                            required=[
                                "nome_amigo",
                            ],
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="enviar_captura_discord_canal",
                        description=(
                            "Captura um print da tela OU uma foto da "
                            "câmera (ou reaproveita a última captura já "
                            "feita, se recente) e manda num CANAL de "
                            "texto do Discord, com a captura anexada — "
                            "mesma resolução de canal de "
                            "enviar_mensagem_discord. Diferente de "
                            "enviar_captura_discord_dm, que manda pra "
                            "uma pessoa específica por DM. Use quando o "
                            "usuário pedir pra tirar/enviar um print ou "
                            "uma foto num canal do Discord, sem "
                            "mencionar uma pessoa específica (ex: 'tire "
                            "um print e manda no canal geral do "
                            "discord', 'manda uma foto no canal de "
                            "jogos'). Se o usuário mencionar uma pessoa "
                            "específica em vez de um canal, use "
                            "enviar_captura_discord_dm. Se o usuário não "
                            "especificar o canal, deixe o campo canal "
                            "vazio — a função decide sozinha se dá pra "
                            "usar um canal já conhecido como padrão, ou "
                            "se precisa perguntar qual usar."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "canal": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Nome do canal, se o usuário "
                                        "especificou (ex: 'geral', "
                                        "'jogos'). Deixe vazio se ele "
                                        "não mencionou nenhum canal."
                                    ),
                                ),
                                "texto": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Mensagem a acompanhar a "
                                        "captura. Opcional."
                                    ),
                                ),
                                "capturar_novo": types.Schema(
                                    type="BOOLEAN",
                                    description=(
                                        "Verdadeiro se o usuário pediu "
                                        "explicitamente pra tirar um "
                                        "print ou uma foto NOVA agora. "
                                        "Falso (ou omitido) se ele está "
                                        "se referindo a uma captura já "
                                        "feita antes."
                                    ),
                                ),
                                "tipo_captura": types.Schema(
                                    type="STRING",
                                    enum=["print", "foto"],
                                    description=(
                                        "'print' ou 'foto', conforme o "
                                        "usuário pediu. Só é usado quando "
                                        "capturar_novo é verdadeiro, ou "
                                        "quando não há nenhuma captura "
                                        "recente pra reaproveitar. Se "
                                        "capturar_novo for falso e já "
                                        "existir uma captura recente, "
                                        "pode deixar vazio."
                                    ),
                                ),
                            },
                            required=[],
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="enviar_captura_remoto",
                        description=(
                            "Captura um print da tela OU uma foto da "
                            "câmera (ou reaproveita a última captura já "
                            "feita, se recente) e envia pra outra "
                            "máquina do jarvis, usando o mesmo mecanismo "
                            "de transferência de arquivo remoto já "
                            "existente. Use quando o usuário pedir pra "
                            "tirar/enviar um print ou uma foto pra outro "
                            "computador (ex: 'tire um print e manda pro "
                            "computador da loja', 'tira uma foto e manda "
                            "pra loja'). maquina_destino é sempre "
                            "obrigatório — o nome da máquina exatamente "
                            "como o usuário se referiu a ela."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "maquina_destino": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Nome da máquina remota, "
                                        "conforme o usuário se referiu "
                                        "a ela."
                                    ),
                                ),
                                "capturar_novo": types.Schema(
                                    type="BOOLEAN",
                                    description=(
                                        "Verdadeiro se o usuário pediu "
                                        "explicitamente pra tirar um "
                                        "print ou uma foto NOVA agora. "
                                        "Falso (ou omitido) se ele está "
                                        "se referindo a uma captura já "
                                        "feita antes."
                                    ),
                                ),
                                "tipo_captura": types.Schema(
                                    type="STRING",
                                    enum=["print", "foto"],
                                    description=(
                                        "'print' ou 'foto', conforme o "
                                        "usuário pediu. Só é usado quando "
                                        "capturar_novo é verdadeiro, ou "
                                        "quando não há nenhuma captura "
                                        "recente pra reaproveitar. Se "
                                        "capturar_novo for falso e já "
                                        "existir uma captura recente, "
                                        "pode deixar vazio."
                                    ),
                                ),
                            },
                            required=[
                                "maquina_destino",
                            ],
                        ),
                    ),

                    # salvar_memoria, listar_memorias, esquecer_memoria
                    # e buscar_memorias_relacionadas NÃO são mais
                    # declaradas aqui: passaram para o pacote isolado
                    # jarvis/pacotes/memoria_obsidian/, que as expõe
                    # pelo contrato padrão obter_function_declarations()
                    # /despachar(). Ver docs/INTEGRATION.md.

                    types.FunctionDeclaration(
                        name="encerrar_chamada",
                        description=(
                            "Encerra a chamada atual do ALFRED. Use somente "
                            "quando o usuário pedir claramente para encerrar, "
                            "finalizar, desligar ou terminar a chamada, sessão "
                            "ou conexão. Exemplos: 'encerrar chamada', "
                            "'encerre a sessão', 'finalizar conversa', "
                            "'pode desligar', 'termine a chamada'."
                        ),
                    ),
        ]

        # Estende as tools nativas com as expostas por cada pacote
        # registrado (ver PACOTES_REGISTRADOS logo abaixo dos imports
        # e docs/INTEGRATION.md na raiz do projeto para o padrão completo
        # — todo pacote novo só precisa expor
        # obter_function_declarations()/despachar(), sem editar nada
        # aqui além desta lista e do branch de despacho).
        function_declarations = list(function_declarations_nativas)

        for pacote in PACOTES_REGISTRADOS:
            function_declarations.extend(
                pacote.obter_function_declarations()
            )

        tools = [
            types.Tool(
                function_declarations=function_declarations
            )
        ]

        # Contexto inicial LEVE: só as poucas notas mais recentes do
        # vault, não a memória inteira. O resto o modelo busca sob
        # demanda com buscar_memorias_relacionadas — é o que permite a
        # memória crescer sem inchar o prompt a cada sessão (o sistema
        # antigo injetava as 50 memórias de uma vez, todas as vezes).
        memorias_atuais = await asyncio.to_thread(
            memoria_obsidian.contexto_inicial
        )

        # Bloco de autenticação — só entra em instrucao_sistema quando
        # EXIGIR_AUTENTICACAO (jarvis/nucleo/config.py, .env) está ligado
        # (padrão True — o comportamento de segurança já existente
        # nunca muda sozinho). Extraído num pedaço à parte, em vez de
        # ficar direto dentro da concatenação de instrucao_sistema,
        # exatamente pra poder incluir ou não condicionalmente. O
        # texto em si mora em jarvis/nucleo/prompts/
        # gemini_live_autenticacao.md — ver prompts.bloco_autenticacao().
        bloco_autenticacao = (
            prompts.bloco_autenticacao()
            if EXIGIR_AUTENTICACAO
            else ""
        )

        # Define identidade, personalidade, autenticação,
        # limites, regras de memória, visão e encerramento. O corpo
        # (tudo menos o bloco de autenticação) mora em
        # jarvis/nucleo/prompts/gemini_live_sistema.md — ver
        # prompts.instrucao_sistema_corpo(), que já devolve o texto
        # terminado nas duas quebras de linha que separam a instrução
        # do contexto de memórias que vem concatenado logo abaixo.
        instrucao_sistema = (
            bloco_autenticacao
            + prompts.instrucao_sistema_corpo()
            + memorias_atuais
        )

        # Monta a configuração da sessão Live,
        # incluindo áudio, voz, ferramentas e instrução do sistema.
        config = types.LiveConnectConfig(
            response_modalities=[
                "AUDIO"
            ],

            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=GEMINI_VOICE
                    )
                )
            ),

            # Pede a transcrição em texto da resposta falada —
            # confirmado no SDK instalado (types.AudioTranscriptionConfig,
            # entregue em resposta.server_content.output_transcription)
            # antes de assumir que existia. Usada pra mostrar a
            # resposta do jarvis como texto na janela de chat (ver
            # receber_audio) — sem isso, response_modalities=["AUDIO"]
            # não traz nenhum texto na resposta.
            output_audio_transcription=types.AudioTranscriptionConfig(),

            tools=tools,

            system_instruction=types.Content(
                parts=[
                    types.Part(
                        text=instrucao_sistema
                    )
                ]
            ),
        )

        # Fila que recebe os blocos capturados pelo microfone.
        fila_microfone = asyncio.Queue(
            maxsize=LIMITE_FILA_MICROFONE
        )
        # Fila que recebe os blocos de áudio enviados pelo Gemini.
        fila_saida = asyncio.Queue()

        self.status_recebido.emit(
            "Conectando ao Gemini Live..."
        )

        # Abre a conexão assíncrona com o modelo Gemini Live.
        # O bloco with encerra a conexão automaticamente ao final.
        async with client.aio.live.connect(
            model=GEMINI_LIVE_MODEL,
            config=config,
        ) as sessao:
            self.sessao = sessao

            self.status_recebido.emit(
                "ALFRED conectado. Pode falar."
            )

            # Beep local (não depende do Gemini nem da rede) avisando
            # que a chamada conectou e o usuário já pode falar — ver
            # FREQUENCIA_BEEP_CHAMADA_INICIADA/DURACAO_BEEP_CHAMADA_INICIADA_MS
            # acima. winsound.Beep é bloqueante, por isso roda em
            # thread separada (asyncio.to_thread), nunca direto no
            # loop assíncrono.
            await asyncio.to_thread(
                winsound.Beep,
                FREQUENCIA_BEEP_CHAMADA_INICIADA,
                DURACAO_BEEP_CHAMADA_INICIADA_MS,
            )

            # Inicia as tarefas simultâneas da chamada: enviar
            # microfone, receber respostas, reproduzir áudio,
            # verificar inatividade e monitorar a conexão com o
            # Gemini.
            # Cada uma passa por _tarefa_supervisionada para que uma
            # exceção inesperada encerre a chamada com erro visível,
            # em vez de matar a tarefa em silêncio e deixar a chamada
            # travada (ver o comentário desse método).
            tarefas = [
                asyncio.create_task(
                    self._tarefa_supervisionada(
                        "MICROFONE",
                        self.enviar_microfone(
                            sessao,
                            fila_microfone,
                        ),
                    ),
                    name="MICROFONE",
                ),

                asyncio.create_task(
                    self._tarefa_supervisionada(
                        "RECEPÇÃO",
                        self.receber_audio(
                            sessao,
                            fila_saida,
                            fila_microfone,
                        ),
                    ),
                    name="RECEPÇÃO",
                ),

                asyncio.create_task(
                    self._tarefa_supervisionada(
                        "REPRODUÇÃO",
                        self.reproduzir_audio(
                            fila_saida,
                            fila_microfone,
                        ),
                    ),
                    name="REPRODUÇÃO",
                ),

                asyncio.create_task(
                    self._tarefa_supervisionada(
                        "INATIVIDADE",
                        self.verificar_inatividade(),
                    ),
                    name="INATIVIDADE",
                ),

                asyncio.create_task(
                    self._tarefa_supervisionada(
                        "CONEXÃO",
                        self.monitorar_conexao(),
                    ),
                    name="CONEXÃO",
                ),

                asyncio.create_task(
                    self._tarefa_supervisionada(
                        "VIGIA",
                        self.vigiar_travamento(fila_saida),
                    ),
                    name="VIGIA",
                ),
            ]

            # vigiar_travamento() consulta esta lista para detectar
            # uma tarefa que morreu enquanto a chamada seguia ativa.
            self.tarefas_chamada = tarefas

            # Mantém a sessão viva até que parar() altere self.ativo.
            while self.ativo:
                await asyncio.sleep(
                    0.1
                )

            # Cancela as tarefas quando a chamada está sendo encerrada.
            for tarefa in tarefas:
                tarefa.cancel()

            if self.tarefa_liberar_microfone:
                self.tarefa_liberar_microfone.cancel()

            if self.tarefa_encerramento:
                self.tarefa_encerramento.cancel()

            # Cancela qualquer chamada de função ainda em andamento
            # quando a chamada é encerrada — mesma lógica das tarefas
            # acima, agora também pra self.tarefas_funcao_ativas
            # (várias chamadas de função podem estar rodando em
            # paralelo, ver receber_audio).
            for tarefa_funcao in self.tarefas_funcao_ativas:
                tarefa_funcao.cancel()

            # Interrompe a visualização contínua da tela,
            # caso ainda esteja ativa quando a chamada terminar.
            if (
                self.monitor_tela_continuo
                and self.monitor_tela_continuo.esta_ativo
            ):
                await self.monitor_tela_continuo.parar()
                self.monitor_tela_continuo = None

            await asyncio.gather(
                *tarefas,
                return_exceptions=True,
            )

            self.tarefas_chamada = []

        # Guardará a sessão ativa do Gemini Live.
        self.sessao = None

        # A chamada morreu por falha, não por pedido do usuário: o
        # cérebro reserva assume a conversa a partir daqui, em
        # silêncio (sem anunciar a troca — decisão explícita do
        # usuário). Só quando ELE terminar é que a chamada acaba de
        # fato, por isso este bloco fica antes de ativacao_voz.retomar()
        # e, consequentemente, antes de run() emitir chamada_encerrada.
        #
        # assumir() é síncrona e bloqueante (grava microfone, chama
        # APIs, fala), então vai pra uma thread — nunca direto no event
        # loop, mesma regra de todo o resto deste arquivo.
        if self.encerrou_por_falha and cerebro_reserva.esta_disponivel():
            self.reserva_ativa = True

            try:
                await asyncio.to_thread(
                    cerebro_reserva.assumir,
                    PACOTES_REGISTRADOS,
                    lambda: self.reserva_ativa,
                    self.status_recebido.emit,
                )

            except Exception as erro:
                print(f"[RESERVA] O modo reserva falhou: {erro}")

            finally:
                self.reserva_ativa = False

        elif self.encerrou_por_falha:
            print(f"[RESERVA] {cerebro_reserva.motivo_indisponivel()}")

        # A chamada terminou de verdade — volta a escutar a palavra-
        # chave de ativação (ver jarvis/pacotes/ativacao_voz/detector.py). Reaproveita
        # o callback já registrado por main.py, não precisa
        # receber nada de novo aqui.
        ativacao_voz.retomar()

    # Confere periodicamente os estados que NUNCA deveriam ficar
    # presos e, se encontrar um, diz exatamente qual — no console e
    # na interface.
    #
    # Existe porque o app não tinha visibilidade nenhuma: em três
    # relatos seguidos de "travou no status X, tive que reiniciar"
    # não havia uma única linha de log dizendo o que tinha parado.
    # Cada checagem aqui é de um estado IMPOSSÍVEL em operação
    # normal, não de "está parado" (ficar parado é normal: ninguém
    # falando é o caso comum), então isto não gera alarme falso.
    #
    # Onde é seguro, também desfaz o estado preso em vez de só
    # reclamar — é sempre melhor que a chamada volte a funcionar do
    # que ficar travada esperando o usuário reiniciar o app.
    async def vigiar_travamento(self, fila_saida):
        desde_falando = None
        desde_funcao_visual = None
        fila_saida_anterior = 0

        # A reprodução travada continua travada nos ciclos seguintes;
        # sem isto o mesmo aviso sairia a cada
        # INTERVALO_VIGILANCIA_SEGUNDOS e entupiria o log de
        # atividade. Volta a False quando a reprodução se recupera,
        # então um segundo episódio é avisado de novo.
        ja_avisou_reproducao = False

        while self.ativo:
            await asyncio.sleep(INTERVALO_VIGILANCIA_SEGUNDOS)

            if not self.ativo:
                break

            agora = time.monotonic()

            # 1. alfred_falando preso: liberar_microfone_apos_fala
            # zera essa flag 0.8s depois do último bloco de áudio.
            # Ficar minutos em True significa que aquela tarefa se
            # perdeu — e, no modo padrão (sem interrupção), isso
            # deixa o microfone mudo para sempre.
            if self.alfred_falando:
                desde_falando = desde_falando or agora

                if (
                    agora - desde_falando
                    > LIMITE_FALANDO_PRESO_SEGUNDOS
                ):
                    self._reportar_travamento(
                        "o jarvis ficou marcado como 'falando' por "
                        f"{int(agora - desde_falando)}s seguidos — "
                        "o microfone foi reaberto à força."
                    )

                    self.alfred_falando = False
                    desde_falando = None
            else:
                desde_falando = None

            # 2. Mutex de função visual preso: processar_funcao_visual
            # o libera num finally, então isso só acontece se algo
            # muito atípico ocorrer — mas, preso, bloqueia TODA
            # análise de tela/câmera pelo resto da chamada.
            if self.executando_funcao_visual:
                desde_funcao_visual = desde_funcao_visual or agora

                if (
                    agora - desde_funcao_visual
                    > LIMITE_FUNCAO_VISUAL_PRESA_SEGUNDOS
                ):
                    self._reportar_travamento(
                        "uma análise visual ficou marcada como em "
                        f"andamento por {int(agora - desde_funcao_visual)}s "
                        "— foi liberada à força."
                    )

                    self.executando_funcao_visual = False
                    desde_funcao_visual = None
            else:
                desde_funcao_visual = None

            # 3. Fila de reprodução crescendo sem sair nada: o
            # dispositivo de saída parou de consumir. fila_saida é
            # ilimitada, então isso não estoura sozinho — cresce em
            # silêncio enquanto o usuário não ouve mais nada.
            fila_atual = fila_saida.qsize()

            reproducao_parada = (
                fila_atual > LIMITE_FILA_SAIDA_PARADA
                and fila_atual >= fila_saida_anterior
                and agora - self.timestamp_ultima_reproducao
                > INTERVALO_VIGILANCIA_SEGUNDOS * 2
            )

            if reproducao_parada and not ja_avisou_reproducao:
                self._reportar_travamento(
                    f"a reprodução de áudio parou com {fila_atual} "
                    "blocos acumulados na fila — o dispositivo de "
                    "saída não está mais consumindo áudio."
                )

                ja_avisou_reproducao = True

            elif not reproducao_parada:
                ja_avisou_reproducao = False

            fila_saida_anterior = fila_atual

            # [DIAGNÓSTICO DE ATRASO EM CONVERSAS LONGAS] Amostra
            # contínua, a cada tick deste mesmo laço (já roda a cada
            # INTERVALO_VIGILANCIA_SEGUNDOS) — dá a curva de
            # crescimento de fila_saida ao longo de TODA a chamada,
            # não só se cruzou LIMITE_FILA_SAIDA_PARADA como o alarme
            # acima. Também reporta e zera o atraso
            # fila->reprodução acumulado desde o tick anterior (ver
            # _laco_reproducao) — reportar tudo por bloco aqui inundaria
            # o painel de console (BLOCO/TAXA_SAIDA ≈ 43ms por bloco,
            # ~23/s), por isso só o máximo/média por janela de
            # INTERVALO_VIGILANCIA_SEGUNDOS.
            if DEBUG_TIMING_FILA_SAIDA:
                if self._debug_atraso_contagem_desde_tick:
                    atraso_medio = (
                        self._debug_atraso_soma_desde_tick
                        / self._debug_atraso_contagem_desde_tick
                    )
                else:
                    atraso_medio = 0.0

                print(
                    "[TIMING-FILA] "
                    f"t={agora - self._debug_inicio_chamada:.0f}s "
                    f"fila_saida={fila_atual} blocos "
                    f"(~{fila_atual * BLOCO / TAXA_SAIDA:.2f}s) "
                    f"atraso_max={self._debug_atraso_max_desde_tick * 1000:.0f}ms "
                    f"atraso_medio={atraso_medio * 1000:.0f}ms "
                    f"(amostras={self._debug_atraso_contagem_desde_tick})"
                )

                self._debug_atraso_max_desde_tick = 0.0
                self._debug_atraso_soma_desde_tick = 0.0
                self._debug_atraso_contagem_desde_tick = 0

            # 4. Microfone parou de entregar blocos: o stream de
            # entrada morreu sem lançar exceção. A chamada continua
            # com toda a aparência de funcionando, mas o jarvis nunca
            # mais ouve nada. Encerrar é melhor que ficar assim — a
            # próxima chamada reabre o stream já no dispositivo
            # atual, sem precisar reiniciar o app.
            if (
                self.timestamp_ultimo_bloco_microfone
                and agora - self.timestamp_ultimo_bloco_microfone
                > LIMITE_MICROFONE_MUDO_SEGUNDOS
            ):
                self._reportar_travamento(
                    "o microfone parou de entregar áudio há "
                    f"{int(agora - self.timestamp_ultimo_bloco_microfone)}s "
                    "(o dispositivo de entrada provavelmente mudou ou "
                    "foi reiniciado durante a chamada). A chamada foi "
                    "encerrada — inicie outra para reabrir o microfone."
                )

                self.encerrou_por_falha = True
                self.ativo = False
                return

            # 5. Alguma das tarefas da chamada terminou enquanto a
            # chamada ainda deveria estar rodando.
            for tarefa in self.tarefas_chamada:
                if tarefa.done() and not tarefa.cancelled():
                    self._reportar_travamento(
                        f"a tarefa '{tarefa.get_name()}' terminou "
                        "sozinha enquanto a chamada ainda estava "
                        "ativa."
                    )

                    self.encerrou_por_falha = True
                    self.ativo = False
                    return

    # Console + interface, para o usuário não precisar estar olhando
    # um terminal para descobrir o que travou.
    def _reportar_travamento(self, descricao):
        print(f"[VIGIA] Travamento detectado: {descricao}")

        self.erro_recebido.emit(
            f"Problema detectado na chamada: {descricao}"
        )

    # Envolve UMA das tarefas simultâneas da chamada (microfone,
    # recepção, reprodução, inatividade, conexão) para que ela nunca
    # morra em silêncio.
    #
    # BUG REAL relatado pelo usuário ("travou no status X, tive que
    # reiniciar"): as tarefas criadas em executar() só são aguardadas
    # (asyncio.gather) DEPOIS que self.ativo vira False. Enquanto
    # isso, executar() fica no laço "while self.ativo: await sleep".
    # Se uma dessas tarefas levantasse uma exceção, ninguém observava
    # o resultado dela — a chamada continuava "ativa" (microfone
    # ainda enviando, status parado na última mensagem emitida), mas
    # nunca mais respondia nada, e o erro era engolido no final pelo
    # return_exceptions=True. O sintoma era exatamente uma tela
    # travada exigindo reiniciar o app.
    #
    # receber_audio era o caso mais grave: sem ela, nenhuma resposta
    # do Gemini (áudio ou tool_call) volta a ser processada, embora
    # tudo continue com aparência de funcionando. É o mesmo bug já
    # corrigido antes em enviar_microfone (que mantém o próprio
    # try/except, com mensagem específica de microfone) — aqui ele é
    # resolvido de uma vez para todas as cinco tarefas.
    #
    # asyncio.CancelledError NÃO é capturada aqui de propósito: desde
    # o Python 3.8 ela não herda de Exception, então o cancelamento
    # normal feito por executar() ao encerrar a chamada continua
    # passando direto, sem ser reportado como falha.
    async def _tarefa_supervisionada(self, nome, corrotina):
        try:
            await corrotina

        except Exception as erro:
            # str(TimeoutError()) é vazio — sem isto a interface
            # mostraria "porque 'REPRODUÇÃO' falhou: " e nada mais,
            # justamente no caso do dispositivo de áudio travado.
            detalhe = str(erro) or type(erro).__name__

            print(
                f"[{nome}] A tarefa terminou com um erro inesperado: "
                f"{erro!r} — encerrando a chamada em vez de deixá-la "
                "travada."
            )

            self.erro_recebido.emit(
                f"A chamada foi encerrada porque '{nome}' falhou: "
                f"{detalhe}"
            )

            self.encerrou_por_falha = True
            self.ativo = False

    # Captura o microfone continuamente e envia os blocos
    # de áudio em tempo real para o Gemini.
    async def enviar_microfone(
        self,
        sessao,
        fila_microfone,
    ):
        # Obtém o loop desta tarefa para inserir áudio na fila
        # a partir do callback do sounddevice.
        loop = asyncio.get_running_loop()

        # Função chamada automaticamente pelo sounddevice
        # sempre que um novo bloco de áudio é capturado.
        def callback(
            indata,
            frames,
            time_info,
            status,
        ):
            # Sinal de VIDA do stream de entrada, marcado antes de
            # qualquer return antecipado de propósito: o que importa
            # aqui é que o dispositivo continua entregando blocos,
            # não se o áudio vai ser aproveitado. Sem isso não havia
            # como distinguir "ninguém está falando" (normal) de "o
            # microfone morreu" — que é justamente o travamento que
            # não levanta exceção nenhuma: se o dispositivo padrão
            # muda ou reenumera no meio da chamada (um jogo assumindo
            # o áudio, um headset USB reconectando), o sounddevice
            # simplesmente PARA de chamar este callback, o stream
            # continua "aberto", e enviar_microfone fica preso pra
            # sempre em fila_microfone.get(). Ver vigiar_travamento().
            self.timestamp_ultimo_bloco_microfone = time.monotonic()

            if not self.ativo:
                return

            # Ignora o microfone enquanto o ALFRED fala, evitando que
            # ele escute a própria voz — só quando interrupcao_habilitada
            # é False (padrão/config.json). Com True, o microfone
            # continua sendo capturado mesmo com o ALFRED falando, de
            # propósito, pra permitir interrupção (ver
            # self.interrupcao_habilitada em __init__ e
            # docs/INTEGRATION.md, seção "Interrupção de fala").
            if self.alfred_falando and not self.interrupcao_habilitada:
                return

            if status:
                print(
                    "Aviso microfone:",
                    status,
                )

            # Converte os dados capturados para bytes.
            audio_bytes = bytes(
                indata
            )

            # Envia os bytes para a fila assíncrona com segurança
            # a partir do callback de áudio.
            # Se a fila estiver cheia, o bloco mais novo é descartado
            # para impedir atraso e acúmulo de áudio antigo.
            def adicionar_audio():
                if not self.ativo:
                    return

                # Mesma exceção do check acima: com interrupcao_habilitada,
                # não bloqueia por causa de alfred_falando.
                if self.alfred_falando and not self.interrupcao_habilitada:
                    return

                try:
                    fila_microfone.put_nowait(
                        audio_bytes
                    )

                except asyncio.QueueFull:
                    pass

            loop.call_soon_threadsafe(
                adicionar_audio
            )

        # Abre o fluxo de entrada bruto do microfone. BUG REAL
        # corrigido aqui, relatado pelo usuário: sem o try/except,
        # uma falha ao abrir o microfone (ex: "Error querying device
        # -1", quando nenhum dispositivo de entrada padrão está
        # disponível no momento) matava esta tarefa em silêncio — a
        # chamada continuava "conectada" (o beep já tinha tocado, o
        # status mostrava normal), mas o áudio do usuário nunca mais
        # era capturado. A chamada ficava com aparência de
        # funcionando, mas o jarvis nunca mais ouvia nada — o mesmo
        # sintoma relatado como "não responde mais". Qualquer exceção
        # daqui em diante (abrir o stream, ou qualquer erro dentro do
        # loop) agora é reportada e encerra a chamada de forma limpa,
        # em vez de morrer silenciosamente.
        try:
            with sd.RawInputStream(
                samplerate=TAXA_ENTRADA,
                blocksize=BLOCO,
                dtype="int16",
                channels=CANAIS,
                callback=callback,
            ):
                # Marca o início: a partir daqui o stream deve
                # entregar blocos continuamente (ver o callback e
                # vigiar_travamento).
                self.timestamp_ultimo_bloco_microfone = time.monotonic()

                # Mantém a sessão viva até que parar() altere self.ativo.
                while self.ativo:
                    audio_bytes = await fila_microfone.get()

                    # O bloco pode ter entrado na fila poucos milissegundos
                    # antes de o assistente começar a falar.
                    # Fazemos uma segunda verificação para garantir que o
                    # usuário nunca interrompa o assistente durante a resposta
                    # — a menos que interrupcao_habilitada esteja ligado
                    # (mesma exceção dos dois checks acima).
                    if self.alfred_falando and not self.interrupcao_habilitada:
                        continue

                    # Envia o bloco de áudio atual para o Gemini Live.
                    await self._enviar_para_sessao(
                        sessao.send_realtime_input(
                            audio=types.Blob(
                                data=audio_bytes,
                                mime_type=(
                                    f"audio/pcm;rate={TAXA_ENTRADA}"
                                ),
                            )
                        )
                    )

                    # [DIAGNÓSTICO DE ATRASO EM CONVERSAS LONGAS] Marca
                    # o último bloco de microfone REALMENTE enviado —
                    # proxy do "fim da fala do usuário" (a Live API não
                    # expõe um evento explícito de fim de atividade pro
                    # cliente no modo de VAD automático usado aqui; o
                    # próximo bloco só deixa de ser enviado quando
                    # alfred_falando vira True, então este é o instante
                    # mais próximo disso que dá pra medir sem inventar
                    # nada). Ver DEBUG_TIMING_FILA_SAIDA/receber_audio.
                    if DEBUG_TIMING_FILA_SAIDA:
                        self._debug_timestamp_ultimo_envio_mic = (
                            time.monotonic()
                        )

        except Exception as erro:
            print(
                f"[MICROFONE] Não foi possível abrir ou usar o "
                f"microfone: {erro}"
            )

            self.erro_recebido.emit(
                f"Não foi possível abrir o microfone: {erro}"
            )

            self.encerrou_por_falha = True
            self.ativo = False

    # Recebe as respostas da sessão Gemini.
    # Pode receber áudio e também pedidos de chamadas de ferramentas.
    async def receber_audio(
        self,
        sessao,
        fila_saida,
        fila_microfone,
    ):
        while self.ativo:
            # Marca se este ciclo de receive() entregou alguma coisa.
            # Se receive() terminar SEM entregar nada, a sessão do
            # lado do servidor acabou: sem esta guarda, o while de
            # fora chamaria receive() de novo na hora, num laço
            # quente que queima CPU sem nunca mais processar resposta
            # nenhuma — travamento sem exceção nenhuma pra ninguém
            # perceber (e, num PC já ocupado com um jogo, ainda mais
            # visível).
            recebeu_algo = False

            # Percorre continuamente as respostas enviadas pela sessão.
            async for resposta in sessao.receive():
                recebeu_algo = True

                if not self.ativo:
                    break

                # Sinal do servidor de que o usuário interrompeu a
                # fala do ALFRED (campo confirmado no SDK instalado —
                # google.genai.types.LiveServerContent.interrupted —
                # e na doc oficial do Gemini Live). Só é tratado no
                # modo interrupcao_habilitada: no modo padrão o
                # microfone nem chega a ser enviado enquanto
                # alfred_falando (ver os três checks em
                # enviar_microfone), então esse sinal não deveria
                # disparar de verdade nesse modo. Ao detectar,
                # esvazia a fila_saida na hora (pra parar de tocar o
                # áudio antigo, em vez de deixar terminar sozinho) e
                # libera o microfone sem esperar ATRASO_REABRIR_MICROFONE
                # — a própria interrupção já é o sinal de que o
                # usuário está falando agora. Ver docs/INTEGRATION.md,
                # seção "Interrupção de fala (config.json)".
                if (
                    self.interrupcao_habilitada
                    and resposta.server_content
                    and resposta.server_content.interrupted
                ):
                    if self.tarefa_liberar_microfone:
                        self.tarefa_liberar_microfone.cancel()
                        self.tarefa_liberar_microfone = None

                    # Quantas vezes a fala foi cortada por interrupção
                    # nesta chamada, e quantos blocos de áudio foram
                    # jogados fora. Registrado porque uma interrupção
                    # FALSA (o microfone captando estalo de teclado,
                    # respiração, ou o vazamento do próprio fone de
                    # haste) é indistinguível de um travamento do
                    # ponto de vista de quem ouve: a frase para no
                    # meio e não volta, sem consumir CPU nenhum. Se
                    # este contador subir sozinho enquanto o jarvis
                    # fala e o usuário está calado, o culpado é a
                    # interrupção — e a correção é config.json,
                    # "interrupcao": false, não mexer em código.
                    self.interrupcoes_na_chamada += 1
                    descartados = fila_saida.qsize()

                    self.limpar_fila_saida(
                        fila_saida
                    )

                    # [DIAGNÓSTICO DE ATRASO EM CONVERSAS LONGAS]
                    # fila_saida foi descartada fora do fluxo normal
                    # (get() em _laco_reproducao) — sem isto,
                    # _debug_fila_timestamps ficaria com marcações
                    # órfãs, sem correspondência real na fila, e o
                    # atraso medido depois desta interrupção viria
                    # errado (popleft() traria um instante de um bloco
                    # que nunca vai ser tocado).
                    if DEBUG_TIMING_FILA_SAIDA:
                        self._debug_fila_timestamps.clear()

                    print(
                        "[INTERRUPÇÃO] O servidor sinalizou que o "
                        "usuário falou por cima — fala cortada "
                        f"(nº {self.interrupcoes_na_chamada} nesta "
                        f"chamada, {descartados} blocos descartados)."
                    )

                    self.alfred_falando = False

                # Quando chega o primeiro bloco de resposta, bloqueia
                # imediatamente o microfone antes mesmo da reprodução.
                # Também elimina qualquer áudio antigo que tenha sido
                # capturado pouco antes do início da resposta.
                if resposta.data:
                    # Atividade real: o ALFRED está falando. Ver
                    # verificar_inatividade() e
                    # self.timestamp_ultima_atividade.
                    self.timestamp_ultima_atividade = time.monotonic()

                    # [DIAGNÓSTICO DE MICROFONE] Marca só na transição
                    # False -> True (início real do silêncio), não a
                    # cada bloco. Ver DEBUG_TIMING_MICROFONE.
                    if DEBUG_TIMING_MICROFONE and not self.alfred_falando:
                        self._debug_inicio_mudo = time.perf_counter()
                        print(
                            "[TIMING-MIC] Microfone silenciado "
                            "(receber_audio: chegou áudio novo)."
                        )

                    # [DIAGNÓSTICO DE ATRASO EM CONVERSAS LONGAS] Só na
                    # transição False->True (início real de um NOVO
                    # turno, mesmo ponto de DEBUG_TIMING_MICROFONE
                    # acima) — mede a fila RESIDUAL de turnos
                    # anteriores (que numa chamada saudável já deveria
                    # estar zerada a esta altura) e o tempo desde o
                    # último bloco de microfone enviado. Lido ANTES do
                    # fila_saida.put() logo abaixo, de propósito: o
                    # tamanho aqui é só o que sobrou de turnos
                    # passados, sem contar o bloco que está prestes a
                    # entrar agora.
                    if DEBUG_TIMING_FILA_SAIDA and not self.alfred_falando:
                        self._debug_numero_turno += 1
                        backlog_residual = fila_saida.qsize()
                        agora_diag = time.monotonic()

                        if self._debug_timestamp_ultimo_envio_mic is not None:
                            latencia_texto = (
                                f"{agora_diag - self._debug_timestamp_ultimo_envio_mic:.3f}s"
                            )
                        else:
                            latencia_texto = (
                                "desconhecida (nenhum bloco de "
                                "microfone enviado ainda)"
                            )

                        print(
                            f"[TIMING-FILA] Turno {self._debug_numero_turno}: "
                            f"fila residual ao iniciar = "
                            f"{backlog_residual} blocos "
                            f"(~{backlog_residual * BLOCO / TAXA_SAIDA:.2f}s), "
                            "latência desde o último bloco de "
                            f"microfone enviado = {latencia_texto}"
                        )

                    self.alfred_falando = True

                    if self.tarefa_liberar_microfone:
                        self.tarefa_liberar_microfone.cancel()

                    self.limpar_fila_microfone(
                        fila_microfone
                    )

                    if DEBUG_TIMING_FILA_SAIDA:
                        self._debug_fila_timestamps.append(
                            time.monotonic()
                        )

                    await fila_saida.put(
                        resposta.data
                    )

                # Quando o Gemini solicita uma ferramenta, cria uma
                # asyncio.Task própria pra ela e continua o loop na
                # hora — NUNCA aguarda (await) o processamento direto
                # aqui. BUG REAL corrigido: antes, uma função lenta ou
                # travada (email, Discord, comando de terminal)
                # bloqueava esse "async for" inteiro (áudio incluído)
                # até terminar. Cada tool_call agora roda de forma
                # independente, o que também permite várias chamadas
                # de função em paralelo (ex: um comando de terminal
                # demorado e, ao mesmo tempo, um envio de email). O
                # check de limite é feito aqui (antes de criar a
                # tarefa) de propósito — é uma comparação de tamanho
                # de lista, instantânea, não um "esperar uma vaga" que
                # bloquearia o loop de novo.
                if resposta.tool_call:
                    # Atividade real: uma chamada de função está
                    # sendo processada. Ver verificar_inatividade().
                    self.timestamp_ultima_atividade = time.monotonic()

                    if (
                        len(self.tarefas_funcao_ativas)
                        >= LIMITE_TAREFAS_FUNCAO_SIMULTANEAS
                    ):
                        corrotina = self._responder_falha_para_lote(
                            sessao,
                            resposta.tool_call,
                            lambda nome: (
                                f"Não foi possível iniciar '{nome}' "
                                "agora — já existem "
                                f"{LIMITE_TAREFAS_FUNCAO_SIMULTANEAS} "
                                "outras ações em andamento ao mesmo "
                                "tempo (limite atingido). Informe "
                                "isso ao usuário de forma breve e "
                                "diga que ele pode pedir de novo em "
                                "instantes. NÃO tente de novo "
                                "sozinho."
                            ),
                        )
                    else:
                        corrotina = (
                            self._executar_chamada_de_funcao_com_timeout(
                                sessao,
                                resposta.tool_call,
                            )
                        )

                    tarefa = asyncio.create_task(corrotina)

                    self.tarefas_funcao_ativas.append(tarefa)

                    tarefa.add_done_callback(
                        self._ao_finalizar_tarefa_funcao
                    )

                # Acumula a transcrição da fala do ALFRED (chega em
                # pedaços, ao longo do turno) e entrega o texto
                # completo pra uma eventual janela de chat só quando
                # o turno termina — evita mandar fragmentos soltos.
                conteudo = resposta.server_content

                if conteudo and conteudo.output_transcription:
                    texto_transcrito = (
                        conteudo.output_transcription.text
                    )

                    if texto_transcrito:
                        self._buffer_transcricao_atual += (
                            texto_transcrito
                        )

                if (
                    conteudo
                    and conteudo.turn_complete
                    and self._buffer_transcricao_atual
                ):
                    obter_sinalizador().resposta_texto_recebida.emit(
                        self._buffer_transcricao_atual
                    )

                    self._buffer_transcricao_atual = ""

            # Ver o comentário de recebeu_algo no topo deste while.
            if self.ativo and not recebeu_algo:
                print(
                    "[RECEPÇÃO] A sessão do Gemini encerrou o fluxo "
                    "de respostas — encerrando a chamada em vez de "
                    "reabrir receive() num laço vazio."
                )

                self.erro_recebido.emit(
                    "A conexão com o Gemini foi encerrada pelo "
                    "servidor. A chamada foi finalizada."
                )

                self.encerrou_por_falha = True
                self.ativo = False

    # Retorna (caminho, capturou_novo, pergunta_ambiguidade) pra
    # anexar/enviar uma captura visual — print OU foto. Usada por
    # enviar_captura_email/enviar_captura_discord_dm/
    # enviar_captura_remoto — nenhuma delas reimplementa captura,
    # todas passam por aqui — e indiretamente por salvar_print_tela e
    # tirar_foto_camera (que sempre atualizam self.ultima_captura_*
    # depois de capturar).
    #
    # forcar_captura_nova=True quando o próprio pedido do usuário já
    # veio como "tire um print/uma foto e envie" (o Gemini seta isso
    # via capturar_novo na chamada) — nesse caso sempre captura de
    # novo, mesmo que exista uma captura recente. Caso contrário,
    # reaproveita self.ultima_captura_caminho (print ou foto, o que
    # tiver sido capturado por último) se ainda estiver dentro de
    # TIMEOUT_ULTIMA_CAPTURA_SEGUNDOS.
    #
    # Quando não há nenhuma captura reaproveitável (nunca capturado,
    # ou velho demais) OU forcar_captura_nova é True, tipo_captura
    # precisa dizer 'print' ou 'foto' — se vier vazio/inválido nesse
    # caso, a função NÃO adivinha: devolve caminho=None e uma
    # pergunta_ambiguidade pro Gemini repassar ao usuário antes de
    # chamar de novo.
    async def _obter_ou_capturar_ultima_captura(
        self,
        forcar_captura_nova=False,
        tipo_captura=None,
    ):
        tem_captura_recente = (
            self.ultima_captura_caminho is not None
            and self.ultima_captura_timestamp is not None
            and (
                time.monotonic() - self.ultima_captura_timestamp
            )
            <= TIMEOUT_ULTIMA_CAPTURA_SEGUNDOS
        )

        if tem_captura_recente and not forcar_captura_nova:
            return self.ultima_captura_caminho, False, None

        tipo_captura = (tipo_captura or "").strip().lower()

        if tipo_captura not in ("print", "foto"):
            return (
                None,
                False,
                "Não há uma captura recente pra reaproveitar, e não "
                "ficou claro se é pra capturar um print da tela ou "
                "uma foto da câmera — pergunte ao usuário qual dos "
                "dois ele quer e chame esta função de novo com "
                "tipo_captura preenchido.",
            )

        # MUTEX REAL FALTANDO, corrigido aqui — ver
        # _mutex_funcao_visual. Sem isso, "envie uma foto"/"envie um
        # print" disparado perto de outra tool visual (voz ou botão)
        # podia disputar o mesmo handle da webcam.
        async with self._mutex_funcao_visual() as mutex_livre:
            if not mutex_livre:
                return (
                    None,
                    False,
                    "Já existe uma captura de tela/câmera em "
                    "andamento — tente de novo em instantes.",
                )

            if tipo_captura == "foto":
                # Mesma captura já usada por analisar_camera/
                # tirar_foto_camera (reaproveitada, não duplicada). Em
                # asyncio.to_thread — ver o comentário de correção em
                # enviar_camera_para_gemini, mais abaixo neste arquivo,
                # pra o porquê.
                imagem_bytes = await asyncio.to_thread(
                    capturar_camera_bytes
                )

                caminho_salvo = await asyncio.to_thread(
                    salvar_foto_bytes,
                    imagem_bytes,
                )
            else:
                # Mesma captura já usada por analisar_tela/salvar_print_tela
                # (reaproveitada, não duplicada). Em asyncio.to_thread —
                # mesmo motivo do capturar_camera_bytes acima.
                imagem_bytes = await asyncio.to_thread(
                    capturar_monitor_do_cursor_bytes
                )

                caminho_salvo = await asyncio.to_thread(
                    salvar_print_bytes,
                    imagem_bytes,
                )

        self.ultima_captura_caminho = caminho_salvo
        self.ultima_captura_timestamp = time.monotonic()

        return caminho_salvo, True, None

    # Monta o rascunho pendente de email e o texto de leitura, a
    # partir de dados já resolvidos (destinatário/assunto/corpo/
    # anexo) — extraído do dispatch de preparar_email pra
    # enviar_captura_email poder reaproveitar EXATAMENTE o mesmo
    # fluxo de confirmação, sem duplicar essa lógica.
    def _preparar_rascunho_email(
        self,
        destinatario,
        assunto,
        corpo,
        caminho_anexo,
    ):
        self.email_pendente = {
            "destinatario": destinatario,
            "assunto": assunto,
            "corpo": corpo,
            "caminho_anexo": caminho_anexo,
            "criado_em": time.monotonic(),
        }

        return self._montar_leitura_rascunho_email()

    # Monta o texto de retorno de preparar_email — instrui o Gemini a
    # ler o rascunho de volta pro usuário e parar, esperando a
    # confirmação antes de qualquer outra chamada. Resume o corpo se
    # for longo, pra não obrigar o Jarvis a ler um texto enorme em
    # voz alta.
    def _montar_leitura_rascunho_email(self):
        rascunho = self.email_pendente

        corpo_resumido = rascunho["corpo"]

        if len(corpo_resumido) > 400:
            corpo_resumido = corpo_resumido[:400] + "... (resumido)"

        texto_anexo = (
            f" Anexo: {os.path.basename(rascunho['caminho_anexo'])}."
            if rascunho["caminho_anexo"]
            else ""
        )

        return (
            "Email preparado, mas AINDA NÃO enviado. Leia de volta "
            "pro usuário, com suas próprias palavras: destinatário "
            f"'{rascunho['destinatario']}', assunto "
            f"'{rascunho['assunto']}', conteúdo: "
            f"{corpo_resumido}.{texto_anexo} Termine perguntando "
            "claramente algo como 'posso enviar assim?' e PARE — "
            "não chame nenhuma outra função neste turno. Só depois "
            "de ouvir a resposta do usuário na fala seguinte, chame "
            "confirmar_envio_email com confirmar=true (se ele "
            "confirmar) ou confirmar=false (se ele negar ou pedir "
            "pra cancelar)."
        )

    # Chamado quando uma tarefa de self.tarefas_funcao_ativas termina
    # (sucesso, erro ou cancelamento) — via Task.add_done_callback,
    # então roda de forma síncrona, sempre na mesma thread do loop
    # assíncrono (nunca de outra thread — add_done_callback sempre
    # agenda via call_soon no próprio loop, mesmo que a tarefa tenha
    # sido cancelada/resolvida por algo externo). Remove a tarefa da
    # lista pra ela não crescer pra sempre.
    def _ao_finalizar_tarefa_funcao(self, tarefa):
        if tarefa in self.tarefas_funcao_ativas:
            self.tarefas_funcao_ativas.remove(tarefa)

        if tarefa.cancelled():
            return

        erro = tarefa.exception()

        if erro is not None:
            # Não deveria acontecer de verdade —
            # _executar_chamada_de_funcao_com_timeout já captura tudo
            # internamente e sempre manda uma function_response de
            # erro pro Gemini antes de terminar. Se uma exceção ainda
            # assim escapar até aqui, pelo menos aparece no console em
            # vez de ficar completamente silenciosa (comportamento
            # padrão do asyncio quando uma Task termina com exceção e
            # ninguém nunca dá await/checa o resultado dela).
            print(
                "[FUNÇÃO] Exceção não tratada numa tarefa de função: "
                f"{erro!r}"
            )

    # Roda processar_chamada_de_funcao em duas fases, pra permitir que
    # o jarvis continue conversando (sobre qualquer assunto) enquanto
    # uma função demorada ainda está rodando, em vez de ficar em
    # silêncio até ela terminar — limitação do protocolo de
    # function-calling da Live API, que só deixa o modelo continuar
    # depois de receber o tool_response daquela chamada específica.
    #
    # FASE 1 — corrida curta contra LIMITE_RESPOSTA_IMEDIATA_SEGUNDOS:
    # se a função termina dentro desse prazo curto, responde do jeito
    # de sempre (function_response direto, sem nenhum aviso
    # intermediário) — a grande maioria das funções do dia a dia
    # (memória, visão, etc.) cai aqui, sem mudança de comportamento
    # nenhuma. asyncio.shield garante que, se essa espera curta
    # estourar, só a ESPERA é cancelada — a execução real continua
    # rodando por trás pra FASE 2 pegar o resultado depois.
    #
    # FASE 2 — só entra aqui se a FASE 1 estourou: já respondeu um
    # function_response provisório ("comecei, aviso quando terminar"),
    # fechando o ciclo daquela chamada específica — dali em diante, o
    # resultado real (sucesso, erro, ou o timeout mais longo abaixo)
    # só pode ser entregue por fala espontânea
    # (_enviar_anuncio_espontaneo), nunca mais por tool_response: a
    # Live API não tem um jeito testado/confiável de aceitar uma
    # segunda resposta pra uma chamada de função que já foi
    # respondida. NUNCA tenta de novo sozinho em nenhuma das duas
    # fases — só informa o erro/demora; se o usuário quiser, pede de
    # novo por voz.
    #
    # Limitação aceita, não resolvida aqui: cancelar a execução
    # interrompe o AWAIT dela, mas não força a parada de uma chamada
    # bloqueante síncrona rodando numa thread separada (ex: um
    # asyncio.to_thread ainda em andamento) — isso é uma limitação
    # fundamental de threads em Python (não dá pra matar uma thread à
    # força), a mesma razão pela qual o bug de admin_terminal precisou
    # ser corrigido na origem (stdin=DEVNULL), não só com um timeout
    # por fora.
    async def _executar_chamada_de_funcao_com_timeout(
        self,
        sessao,
        tool_call,
    ):
        # Usa o maior timeout entre todas as chamadas do lote (raro
        # ter mais de uma no mesmo tool_call, mas cobre o caso) — ver
        # TIMEOUTS_TAREFA_FUNCAO_POR_NOME acima pro porquê de algumas
        # funções (admin) precisarem de um valor bem maior que o
        # genérico.
        timeout = max(
            (
                TIMEOUTS_TAREFA_FUNCAO_POR_NOME.get(
                    chamada.name,
                    TIMEOUT_TAREFA_FUNCAO_SEGUNDOS,
                )
                for chamada in tool_call.function_calls
            ),
            default=TIMEOUT_TAREFA_FUNCAO_SEGUNDOS,
        )

        tarefa_execucao = asyncio.create_task(
            self.processar_chamada_de_funcao(
                tool_call,
            )
        )

        # --- FASE 1 ---
        # O envio do resultado fica num "else", FORA do try, de
        # propósito: agora que _enviar_resposta_funcao tem timeout
        # (ver lá), uma falha no ENVIO levantaria TimeoutError e, se
        # ainda estivesse dentro do try, seria confundida com "a
        # função ainda está rodando" — mandaria a resposta provisória
        # e cairia na FASE 2, respondendo DUAS vezes a mesma
        # chamada de função (o que a Live API não suporta). No else,
        # a exceção do envio sobe direto: _enviar_para_sessao já
        # marcou self.conexao_travada e monitorar_conexao encerra a
        # chamada de forma limpa.
        try:
            function_responses, encerrar_depois = await asyncio.wait_for(
                asyncio.shield(tarefa_execucao),
                timeout=min(
                    LIMITE_RESPOSTA_IMEDIATA_SEGUNDOS,
                    timeout,
                ),
            )

        except asyncio.TimeoutError:
            # Ainda rodando — avisa e segue pra FASE 2.
            await self._responder_falha_para_lote(
                sessao,
                tool_call,
                lambda nome: (
                    f"A ação '{nome}' ainda está em andamento — é "
                    "mais demorada que o normal. Diga ao usuário, de "
                    "forma breve e natural, que você já começou e "
                    "vai avisar assim que terminar. NÃO espere em "
                    "silêncio — continue a conversa normalmente com "
                    "o usuário enquanto isso roda em segundo plano."
                ),
            )

        except Exception as erro:
            # Falhou rápido, ainda dentro da FASE 1 — mesmo
            # tratamento de sempre, sem entrar na FASE 2.
            await self._responder_falha_para_lote(
                sessao,
                tool_call,
                lambda nome, erro=erro: (
                    f"Ocorreu um erro inesperado ao executar "
                    f"'{nome}': {erro}. Informe ao usuário, de forma "
                    "breve, que essa ação falhou. NÃO tente "
                    "executá-la de novo sozinho — só se o usuário "
                    "pedir de novo por voz."
                ),
            )
            return

        else:
            # Terminou dentro do limite da FASE 1 (caso da esmagadora
            # maioria das funções) — entrega pelo caminho normal.
            await self._enviar_resposta_funcao(
                sessao,
                function_responses,
                encerrar_depois,
            )
            return

        # --- FASE 2 ---
        tempo_restante = max(
            timeout - LIMITE_RESPOSTA_IMEDIATA_SEGUNDOS,
            1,
        )

        try:
            function_responses, encerrar_depois = await asyncio.wait_for(
                tarefa_execucao,
                timeout=tempo_restante,
            )

            texto_resultado = " ".join(
                str(resposta.response.get("result", ""))
                for resposta in function_responses
            )

            await self._enviar_anuncio_espontaneo(
                "que a ação que estava rodando em segundo plano "
                f"terminou. Resultado: {texto_resultado}"
            )

            if encerrar_depois:
                if self.tarefa_encerramento:
                    self.tarefa_encerramento.cancel()

                self.tarefa_encerramento = asyncio.create_task(
                    self.encerrar_apos_resposta()
                )

        except asyncio.TimeoutError:
            tarefa_execucao.cancel()

            await self._enviar_anuncio_espontaneo(
                "que uma ação que estava rodando em segundo plano "
                "demorou demais e foi cancelada. Não tente executá-la "
                "de novo sozinho."
            )

        except Exception as erro:
            await self._enviar_anuncio_espontaneo(
                "que uma ação que estava rodando em segundo plano "
                f"falhou com um erro inesperado: {erro}. Não tente "
                "executá-la de novo sozinho."
            )

    # Envia o resultado de uma chamada de função pelo caminho normal
    # (tool_response + agenda o encerramento, se for o caso) — mesmo
    # comportamento que processar_chamada_de_funcao tinha antes de
    # passar a só retornar o resultado. Usado só na FASE 1 (resposta
    # rápida, dentro de LIMITE_RESPOSTA_IMEDIATA_SEGUNDOS); a FASE 2
    # entrega o resultado por fala espontânea, não por aqui.
    async def _enviar_resposta_funcao(
        self,
        sessao,
        function_responses,
        encerrar_depois,
    ):
        if function_responses:
            # Passa por _enviar_para_sessao como QUALQUER outro envio
            # pra sessão: sem isso, este await não tinha timeout
            # nenhum e uma conexão travada aqui congelava a chamada
            # para sempre (o modelo não pode falar de novo enquanto
            # não recebe o tool_response), com o status parado na
            # última mensagem emitida e sem nada capaz de se
            # recuperar disso. Era o único envio do arquivo fora
            # dessa proteção, junto do de _responder_falha_para_lote.
            await self._enviar_para_sessao(
                sessao.send_tool_response(
                    function_responses=function_responses
                )
            )

        if encerrar_depois:
            if self.tarefa_encerramento:
                self.tarefa_encerramento.cancel()

            self.tarefa_encerramento = asyncio.create_task(
                self.encerrar_apos_resposta()
            )

    # Envia uma function_response de erro/recusa pra CADA chamada
    # dentro de tool_call.function_calls (um resposta.tool_call pode
    # trazer mais de uma chamada de função de uma vez) — usado tanto
    # pela recusa por limite de concorrência quanto pelo timeout/erro
    # acima. gerar_mensagem(nome) monta o texto específico de cada
    # caso a partir do nome da função. Nunca lança exceção própria —
    # se o próprio envio falhar (ex: sessão já fechada), deixa a
    # exceção subir pra quem chamou tratar (mesmo padrão de qualquer
    # outro uso de sessao.send_tool_response neste arquivo).
    async def _responder_falha_para_lote(
        self,
        sessao,
        tool_call,
        gerar_mensagem,
    ):
        respostas = [
            types.FunctionResponse(
                id=chamada.id,
                name=chamada.name,
                response={
                    "result": gerar_mensagem(chamada.name)
                },
            )
            for chamada in tool_call.function_calls
        ]

        if respostas:
            # Mesma proteção de _enviar_resposta_funcao — ver o
            # comentário lá.
            await self._enviar_para_sessao(
                sessao.send_tool_response(
                    function_responses=respostas
                )
            )

    # Executa as ferramentas solicitadas pelo Gemini e RETORNA
    # (function_responses, encerrar_depois) — não envia mais o
    # tool_response nem agenda o encerramento sozinha; quem chamou
    # (_executar_chamada_de_funcao_com_timeout) decide o canal certo
    # de entrega. Ver o comentário no final do método.
    async def processar_chamada_de_funcao(
        self,
        tool_call,
    ):
        # Armazena as respostas de todas as funções solicitadas.
        function_responses = []
        # Indica se a sessão deve ser encerrada após a resposta falada.
        encerrar_depois = False

        # Uma mesma resposta pode conter uma ou mais chamadas de função.
        for chamada in tool_call.function_calls:
            nome = chamada.name
            # Converte os argumentos recebidos para um dicionário comum.
            args = dict(
                chamada.args or {}
            )

            # [DIAGNÓSTICO DE TRAVAMENTO] Marca o início do
            # processamento desta chamada específica — ver o print
            # de tempo total logo antes de function_responses.append,
            # mais abaixo. Ver DEBUG_TIMING_DISPATCH.
            if DEBUG_TIMING_DISPATCH:
                inicio_chamada = time.perf_counter()

            # Tenta despachar para cada pacote registrado antes das
            # tools nativas (ver PACOTES_REGISTRADOS). despachar()
            # retorna None quando o pacote não reconhece o nome da
            # função — nesse caso tenta o próximo, e se nenhum
            # reconhecer cai nas tools nativas abaixo. Declarado aqui
            # (antes do bloco de identificar_planta/
            # consultar_segunda_opiniao_visual logo abaixo) pra esse
            # bloco poder preenchê-lo diretamente com uma mensagem de
            # "câmera ocupada" e pular o laço de despacho por completo
            # nesse caso — ver o comentário do mutex logo abaixo.
            resultado_pacote = None

            # Exceção ao despacho genérico, compartilhada por
            # identificar_planta e consultar_segunda_opiniao_visual:
            # nenhuma das duas tem uma imagem como parâmetro vindo do
            # Gemini — a captura precisa acontecer aqui, pelo
            # cliente (mesma função já usada por analisar_camera), e
            # ser injetada em args antes de despachar() para o
            # pacote. Ver jarvis/pacotes/identificacao_planta/__init__.py,
            # jarvis/pacotes/identificacao_visual/__init__.py e docs/INTEGRATION.md.
            if nome in (
                "identificar_planta",
                "consultar_segunda_opiniao_visual",
            ):
                # MUTEX REAL FALTANDO, corrigido aqui — ver
                # _mutex_funcao_visual. Se ocupado, preenche
                # resultado_pacote diretamente (pulando o despacho pro
                # pacote, mais abaixo, que ficaria sem imagem_bytes).
                async with self._mutex_funcao_visual() as mutex_livre:
                    if not mutex_livre:
                        resultado_pacote = (
                            "Já existe uma captura de tela/câmera em "
                            "andamento — tente de novo em instantes."
                        )

                    else:
                        self.status_recebido.emit(
                            "Capturando imagem da câmera para identificar a "
                            "planta..."
                            if nome == "identificar_planta"
                            else "Capturando imagem da câmera para a segunda "
                            "opinião visual..."
                        )

                        args["imagem_bytes"] = await asyncio.to_thread(
                            capturar_camera_bytes
                        )

            # Mesma ideia acima, mas só pra dar visibilidade — não
            # captura nada. BUG/FALTA DE UX real reportada pelo
            # usuário: comandos administrativos (admin_terminal) podem
            # levar até TIMEOUT_COMANDO_LONGO_SEGUNDOS (5 min por
            # padrão) sem NENHUM feedback, porque o despacho de
            # pacotes (logo abaixo) não tem acesso a self — só o
            # cliente aqui consegue emitir status. self.status_recebido
            # só atualiza a UI local (rótulo de status + log de
            # atividade, ver jarvis/ui/janela_principal.py:atualizar_status)
            # — nunca toca a sessão Gemini, então não tem o risco
            # documentado de injetar fala espontânea com uma tool_call
            # pendente (ver a seção "Confirmation flow never blocks
            # inside a pending tool call" do admin_terminal no
            # CLAUDE.md). Isso NÃO faz o jarvis falar durante a
            # execução — o protocolo de function-calling da Live API
            # não permite isso enquanto uma chamada de função está
            # pendente — só dá visibilidade de que ele está trabalhando
            # e não travado.
            elif nome in (
                "executar_comando_admin",
                "confirmar_comando_admin",
            ):
                self.status_recebido.emit(
                    "Executando comando administrativo: "
                    f"{args.get('comando', '')}. Pode levar até "
                    "alguns minutos, dependendo do comando — aguarde."
                    if nome == "executar_comando_admin"
                    else "Processando confirmação do comando "
                    "administrativo..."
                )

            # Vira False quando o bloco de identificar_planta/
            # consultar_segunda_opiniao_visual acima já preencheu
            # resultado_pacote com "câmera ocupada" (mutex
            # indisponível) — nesse caso não há imagem_bytes em args,
            # e tentar despachar mesmo assim quebraria o pacote, então
            # todo o laço de despacho (e seu log de tempo) é pulado.
            despachar_para_pacotes = resultado_pacote is None

            # [DIAGNÓSTICO DE TRAVAMENTO] Ver DEBUG_TIMING_DISPATCH.
            if despachar_para_pacotes and DEBUG_TIMING_DISPATCH:
                inicio_despacho_pacotes = time.perf_counter()
                tempos_por_pacote = []

            if despachar_para_pacotes:
                for pacote in PACOTES_REGISTRADOS:
                    if DEBUG_TIMING_DISPATCH:
                        inicio_pacote = time.perf_counter()

                    resultado_pacote = await asyncio.to_thread(
                        pacote.despachar,
                        nome,
                        args,
                    )

                    if DEBUG_TIMING_DISPATCH:
                        tempos_por_pacote.append(
                            (
                                pacote.__name__,
                                (time.perf_counter() - inicio_pacote) * 1000,
                            )
                        )

                    if resultado_pacote is not None:
                        break

            if despachar_para_pacotes and DEBUG_TIMING_DISPATCH:
                duracao_despacho_ms = (
                    time.perf_counter() - inicio_despacho_pacotes
                ) * 1000

                detalhe = ", ".join(
                    f"{nome_pacote}={tempo_ms:.1f}ms"
                    for nome_pacote, tempo_ms in tempos_por_pacote
                )

                print(
                    f"[TIMING] '{nome}': despacho por pacotes levou "
                    f"{duracao_despacho_ms:.1f}ms no total "
                    f"({len(tempos_por_pacote)}/{len(PACOTES_REGISTRADOS)} "
                    f"pacotes tentados) -> {detalhe}"
                )

            if resultado_pacote is not None:
                resultado = resultado_pacote

                # Reenvia a MESMA imagem já usada na consulta externa
                # (Pl@ntNet ou Mistral) pro Gemini, com instrução de
                # comparar com a própria leitura visual — em vez de
                # só repassar o resultado externo sem checagem. Mesmo
                # mecanismo (send_client_content antes do
                # tool_response) já usado por
                # analisar_tela/analisar_camera via
                # processar_funcao_visual, logo abaixo.
                if nome in (
                    "identificar_planta",
                    "consultar_segunda_opiniao_visual",
                ) and args.get("imagem_bytes"):
                    await self.enviar_imagem_para_cruzamento(
                        args["imagem_bytes"],
                        resultado,
                        contexto=(
                            "identificação de planta (Pl@ntNet)"
                            if nome == "identificar_planta"
                            else "segunda opinião visual (Mistral)"
                        ),
                    )

                # Fecha o status de "executando..." emitido antes do
                # despacho, logo acima — sem isso, o log de atividade
                # fica parado na última mensagem de "aguarde" mesmo
                # depois de já ter terminado.
                if nome in (
                    "executar_comando_admin",
                    "confirmar_comando_admin",
                ):
                    self.status_recebido.emit(
                        "Execução do comando administrativo "
                        "finalizada."
                    )

            elif nome in (
                "analisar_tela",
                "analisar_camera",
            ):
                resultado = await self.processar_funcao_visual(
                    nome
                )

            elif nome == "salvar_print_tela":
                # MUTEX REAL FALTANDO, corrigido aqui — ver
                # _mutex_funcao_visual.
                async with self._mutex_funcao_visual() as mutex_livre:
                    if not mutex_livre:
                        resultado = (
                            "Já existe uma captura de tela/câmera em "
                            "andamento — tente de novo em instantes."
                        )

                    else:
                        self.status_recebido.emit(
                            "Salvando print da tela..."
                        )

                        # Mesma captura já usada por analisar_tela
                        # (reaproveitada, não duplicada). Em
                        # asyncio.to_thread — ver o comentário de
                        # correção em enviar_camera_para_gemini, mais
                        # abaixo neste arquivo.
                        imagem_bytes = await asyncio.to_thread(
                            capturar_monitor_do_cursor_bytes
                        )

                        # Gravar em disco é I/O bloqueante, por isso
                        # roda em uma thread separada para não travar
                        # o loop assíncrono.
                        caminho_salvo = await asyncio.to_thread(
                            salvar_print_bytes,
                            imagem_bytes,
                        )

                        # Atualiza a referência de "última captura" —
                        # usada por enviar_captura_email/
                        # enviar_captura_discord_dm/enviar_captura_remoto
                        # quando o pedido seguinte for só "envie este
                        # print"/"envie isso", sem precisar capturar de
                        # novo.
                        self.ultima_captura_caminho = caminho_salvo
                        self.ultima_captura_timestamp = time.monotonic()

                        resultado = f"Print da tela salvo em: {caminho_salvo}"

            elif nome == "tirar_foto_camera":
                # MUTEX REAL FALTANDO, corrigido aqui — ver
                # _mutex_funcao_visual.
                async with self._mutex_funcao_visual() as mutex_livre:
                    if not mutex_livre:
                        resultado = (
                            "Já existe uma captura de tela/câmera em "
                            "andamento — tente de novo em instantes."
                        )

                    else:
                        self.status_recebido.emit(
                            "Tirando foto da câmera..."
                        )

                        # Mesma captura já usada por analisar_camera
                        # (reaproveitada, não duplicada). Em
                        # asyncio.to_thread — ver o comentário de
                        # correção em enviar_camera_para_gemini, mais
                        # abaixo neste arquivo.
                        imagem_bytes = await asyncio.to_thread(
                            capturar_camera_bytes
                        )

                        # Gravar em disco é I/O bloqueante, por isso
                        # roda em uma thread separada para não travar
                        # o loop assíncrono.
                        caminho_salvo = await asyncio.to_thread(
                            salvar_foto_bytes,
                            imagem_bytes,
                        )

                        # Mesma referência compartilhada de "última
                        # captura" que salvar_print_tela atualiza acima.
                        self.ultima_captura_caminho = caminho_salvo
                        self.ultima_captura_timestamp = time.monotonic()

                        resultado = f"Foto salva em: {caminho_salvo}"

            elif nome == "iniciar_visualizacao_continua":
                resultado = await self.iniciar_visualizacao_continua()

            elif nome == "parar_visualizacao_continua":
                resultado = await self.parar_visualizacao_continua()

            elif nome == "preparar_email":
                destinatario = args.get(
                    "destinatario",
                    "",
                )

                assunto = args.get(
                    "assunto",
                    "",
                )

                corpo = args.get(
                    "corpo",
                    "",
                )

                usar_arquivo_selecionado = bool(
                    args.get(
                        "usar_arquivo_selecionado",
                        False,
                    )
                )

                caminho_anexo = None
                falha_anexo = None

                if usar_arquivo_selecionado:
                    self.status_recebido.emit(
                        "Procurando arquivo selecionado no Explorer "
                        "ou na Área de Trabalho..."
                    )

                    # win32com é bloqueante, por isso roda em uma
                    # thread separada para não travar o loop
                    # assíncrono — mesma razão de asyncio.to_thread
                    # já usado pra preparar_email/ler_emails.
                    sucesso_arquivo, resultado_arquivo = (
                        await asyncio.to_thread(
                            explorador_windows.obter_arquivo_selecionado
                        )
                    )

                    if not sucesso_arquivo:
                        falha_anexo = (
                            "Não foi possível encontrar um arquivo "
                            f"selecionado: {resultado_arquivo} O email "
                            "NÃO foi preparado. Avise o usuário e "
                            "pergunte se ele quer selecionar um "
                            "arquivo no Explorer ou na Área de "
                            "Trabalho e tentar de novo."
                        )

                    elif len(resultado_arquivo) > 1:
                        lista = "; ".join(resultado_arquivo)

                        falha_anexo = (
                            f"Há {len(resultado_arquivo)} arquivos "
                            f"selecionados, não apenas um ({lista}). "
                            "O email NÃO foi preparado — pergunte ao "
                            "usuário qual desses arquivos ele quer "
                            "anexar, ou peça pra selecionar só um."
                        )

                    else:
                        caminho_anexo = resultado_arquivo[0]

                if falha_anexo:
                    resultado = falha_anexo

                else:
                    self.status_recebido.emit(
                        "Email preparado, aguardando confirmação..."
                    )

                    # Substitui qualquer rascunho pendente anterior —
                    # só existe um por vez, de propósito (ver
                    # FunctionDeclaration de preparar_email). Mesmo
                    # helper reaproveitado por enviar_captura_email, pra
                    # nunca duplicar o fluxo de confirmação.
                    resultado = self._preparar_rascunho_email(
                        destinatario,
                        assunto,
                        corpo,
                        caminho_anexo,
                    )

            elif nome == "confirmar_envio_email":
                confirmar = bool(
                    args.get(
                        "confirmar",
                        False,
                    )
                )

                if not self.email_pendente:
                    resultado = (
                        "Não há nenhum email pendente de confirmação "
                        "agora."
                    )

                elif (
                    time.monotonic()
                    - self.email_pendente["criado_em"]
                    > TIMEOUT_RASCUNHO_EMAIL
                ):
                    # Rascunho velho demais — descarta em vez de
                    # confirmar por engano algo que o usuário já
                    # esqueceu, numa parte diferente da conversa.
                    self.email_pendente = None

                    resultado = (
                        "O rascunho de email preparado anteriormente "
                        "expirou, sem confirmação a tempo. Prepare o "
                        "email de novo se ainda quiser enviar."
                    )

                elif not confirmar:
                    destinatario_cancelado = self.email_pendente[
                        "destinatario"
                    ]

                    self.email_pendente = None

                    resultado = (
                        "Envio cancelado a pedido do usuário. O email "
                        f"para {destinatario_cancelado} NÃO foi enviado."
                    )

                else:
                    rascunho = self.email_pendente

                    self.status_recebido.emit(
                        "Enviando email..."
                    )

                    # smtplib é bloqueante, por isso roda em uma
                    # thread separada para não travar o loop assíncrono.
                    resultado = await asyncio.to_thread(
                        enviar_email,
                        rascunho["destinatario"],
                        rascunho["assunto"],
                        rascunho["corpo"],
                        rascunho["caminho_anexo"],
                    )

                    self.email_pendente = None

            elif nome == "ler_emails":
                quantidade = args.get(
                    "quantidade",
                    5,
                )

                apenas_nao_lidos = args.get(
                    "apenas_nao_lidos",
                    False,
                )

                pasta = args.get(
                    "pasta",
                    "INBOX",
                )

                self.status_recebido.emit(
                    "Consultando spam..."
                    if pasta == "SPAM"
                    else "Consultando caixa de entrada..."
                )

                # imaplib é bloqueante, por isso roda em uma
                # thread separada para não travar o loop assíncrono.
                resultado = await asyncio.to_thread(
                    ler_emails,
                    quantidade,
                    apenas_nao_lidos,
                    pasta,
                )

            elif nome == "baixar_anexo_email":
                criterio = args.get(
                    "criterio",
                    "",
                )

                self.status_recebido.emit(
                    "Procurando o email e baixando o anexo..."
                )

                # imaplib é bloqueante, por isso roda em uma
                # thread separada para não travar o loop assíncrono.
                resultado = await asyncio.to_thread(
                    baixar_anexo,
                    criterio,
                )

            elif nome == "enviar_captura_email":
                destinatario = args.get(
                    "destinatario",
                    "",
                )

                tipo_captura = args.get("tipo_captura")

                assunto = args.get("assunto") or (
                    "Foto da câmera"
                    if tipo_captura == "foto"
                    else "Print de tela"
                )

                corpo = args.get("corpo") or (
                    "Segue a foto solicitada."
                    if tipo_captura == "foto"
                    else "Segue o print de tela solicitado."
                )

                capturar_novo = bool(
                    args.get(
                        "capturar_novo",
                        False,
                    )
                )

                if not destinatario:
                    resultado = (
                        "É necessário informar o destinatário do email."
                    )

                else:
                    self.status_recebido.emit(
                        "Capturando para enviar por email..."
                    )

                    caminho_captura, capturou_novo, pergunta = (
                        await self._obter_ou_capturar_ultima_captura(
                            capturar_novo,
                            tipo_captura,
                        )
                    )

                    if pergunta:
                        resultado = pergunta

                    else:
                        # Mesmo fluxo de confirmação de preparar_email,
                        # reaproveitado — nunca envia direto.
                        resultado = self._preparar_rascunho_email(
                            destinatario,
                            assunto,
                            corpo,
                            caminho_captura,
                        )

                        if capturou_novo:
                            resultado = (
                                "Capturei uma nova imagem agora. "
                                + resultado
                            )

            elif nome == "enviar_captura_discord_dm":
                nome_amigo = args.get(
                    "nome_amigo",
                    "",
                )

                texto = args.get(
                    "texto"
                ) or "Olha só."

                tipo_captura = args.get("tipo_captura")

                capturar_novo = bool(
                    args.get(
                        "capturar_novo",
                        False,
                    )
                )

                if not nome_amigo:
                    resultado = "É necessário informar o nome do amigo."

                else:
                    self.status_recebido.emit(
                        "Capturando para enviar no Discord..."
                    )

                    caminho_captura, capturou_novo, pergunta = (
                        await self._obter_ou_capturar_ultima_captura(
                            capturar_novo,
                            tipo_captura,
                        )
                    )

                    if pergunta:
                        resultado = pergunta

                    else:
                        # Reaproveita a MESMA resolução de contato (busca
                        # + cache) e envio de DM já implementados em
                        # discord_jarvis — só passa o caminho da captura
                        # como anexo. Chamado direto (fora do despachar()
                        # genérico) porque caminho_anexo não é um
                        # parâmetro que o Gemini controla.
                        resultado = await asyncio.to_thread(
                            discord_jarvis.enviar_dm_discord,
                            nome_amigo,
                            texto,
                            caminho_captura,
                        )

                        if capturou_novo:
                            resultado = (
                                "Capturei uma nova imagem agora. "
                                + resultado
                            )

            elif nome == "enviar_captura_discord_canal":
                canal = args.get(
                    "canal",
                    "",
                )

                texto = args.get(
                    "texto"
                ) or "Olha só."

                tipo_captura = args.get("tipo_captura")

                capturar_novo = bool(
                    args.get(
                        "capturar_novo",
                        False,
                    )
                )

                self.status_recebido.emit(
                    "Capturando para enviar no canal do Discord..."
                )

                caminho_captura, capturou_novo, pergunta = (
                    await self._obter_ou_capturar_ultima_captura(
                        capturar_novo,
                        tipo_captura,
                    )
                )

                if pergunta:
                    resultado = pergunta

                else:
                    # Reaproveita a MESMA resolução de canal (busca +
                    # cache) e envio já implementados em discord_jarvis
                    # — só passa o caminho da captura como anexo.
                    # Chamado direto (fora do despachar() genérico)
                    # porque caminho_anexo não é um parâmetro que o
                    # Gemini controla — mesmo padrão de
                    # enviar_captura_discord_dm acima.
                    resultado = await asyncio.to_thread(
                        discord_jarvis.enviar_mensagem_discord,
                        canal,
                        texto,
                        caminho_captura,
                    )

                    if capturou_novo:
                        resultado = (
                            "Capturei uma nova imagem agora. "
                            + resultado
                        )

            elif nome == "enviar_captura_remoto":
                maquina_destino = args.get(
                    "maquina_destino",
                    "",
                )

                tipo_captura = args.get("tipo_captura")

                capturar_novo = bool(
                    args.get(
                        "capturar_novo",
                        False,
                    )
                )

                if not maquina_destino:
                    resultado = (
                        "É necessário informar qual máquina de destino."
                    )

                else:
                    self.status_recebido.emit(
                        "Capturando para enviar pra outra máquina..."
                    )

                    caminho_captura, capturou_novo, pergunta = (
                        await self._obter_ou_capturar_ultima_captura(
                            capturar_novo,
                            tipo_captura,
                        )
                    )

                    if pergunta:
                        resultado = pergunta

                    else:
                        # Reaproveita o MESMO fluxo de transferência de
                        # arquivo já implementado em rede_jarvis
                        # (enviar_arquivo, via MQTT) — mesmo comando já
                        # usado por enviar_comando_remoto.
                        resultado = await asyncio.to_thread(
                            rede_jarvis.enviar_comando_remoto,
                            maquina_destino,
                            "enviar_arquivo",
                            {
                                "caminho": caminho_captura,
                            },
                        )

                        if capturou_novo:
                            resultado = (
                                "Capturei uma nova imagem agora. "
                                + resultado
                            )

            # As funções de memória saíram daqui: agora são despachadas
            # pelo pacote memoria_obsidian, no laço genérico de
            # PACOTES_REGISTRADOS logo acima (o I/O delas já roda em
            # asyncio.to_thread por lá, como todo despachar()).

            elif nome == "encerrar_chamada":
                self.status_recebido.emit(
                    "Encerrando chamada por comando de voz..."
                )

                resultado = (
                    "Solicitação de encerramento recebida. "
                    "Diga de forma curta que a chamada será encerrada."
                )

                encerrar_depois = True

            else:
                resultado = (
                    "Função desconhecida. Nenhuma ação foi executada."
                )

            # [DIAGNÓSTICO DE TRAVAMENTO] Tempo total desta chamada
            # (despacho por pacotes + execução real, incluindo
            # chamadas de rede) — comparar com o valor de
            # receber_audio pra confirmar que é o mesmo intervalo
            # (ou não). Ver DEBUG_TIMING_DISPATCH.
            if DEBUG_TIMING_DISPATCH:
                duracao_chamada_ms = (
                    time.perf_counter() - inicio_chamada
                ) * 1000

                print(
                    f"[TIMING] '{nome}' processada em "
                    f"{duracao_chamada_ms:.1f}ms no total"
                )

            # Cria a resposta estruturada que será devolvida ao Gemini.
            function_responses.append(
                types.FunctionResponse(
                    id=chamada.id,
                    name=nome,
                    response={
                        "result": resultado
                    },
                )
            )

        # Não envia mais o tool_response nem agenda o encerramento
        # aqui dentro — devolve pra quem chamou decidir (ver
        # _executar_chamada_de_funcao_com_timeout). Motivo: uma
        # chamada de função pode demorar mais que
        # LIMITE_RESPOSTA_IMEDIATA_SEGUNDOS, caso em que quem chamou
        # já fechou o ciclo desta chamada mais cedo com uma resposta
        # provisória ("comecei, aviso quando terminar") — mandar o
        # tool_response de novo aqui, pra uma chamada de função já
        # respondida, não é um caminho testado/confiável contra a Live
        # API. Devolver o resultado, em vez de enviar direto, deixa
        # quem chamou escolher o canal certo (tool_response normal, se
        # ainda estiver dentro do prazo, ou fala espontânea, se não).
        return function_responses, encerrar_depois

    # Aguarda alguns segundos para o ALFRED concluir a despedida
    # antes de pedir que a interface finalize a chamada.
    async def encerrar_apos_resposta(self):
        """
        Aguarda a resposta de despedida do ALFRED
        e só depois solicita o encerramento à interface.
        """

        try:
            await asyncio.sleep(
                2.8
            )

            if self.ativo:
                self.solicitou_encerramento.emit()

        except asyncio.CancelledError:
            pass

    # Verifica periodicamente se a chamada está inativa há tempo
    # demais (TIMEOUT_INATIVIDADE_SEGUNDOS desde a última atividade
    # REAL — ver self.timestamp_ultima_atividade) e, se estiver,
    # encerra sozinha — avisando por voz antes, nunca desligando sem
    # aviso. Roda como uma das tarefas concorrentes de executar(),
    # cancelada junto com as outras quando a chamada termina por
    # qualquer outro motivo primeiro.
    async def verificar_inatividade(self):
        try:
            while self.ativo:
                await asyncio.sleep(
                    10
                )

                if not self.ativo:
                    break

                tempo_inativo = (
                    time.monotonic() - self.timestamp_ultima_atividade
                )

                if tempo_inativo < TIMEOUT_INATIVIDADE_SEGUNDOS:
                    continue

                self.status_recebido.emit(
                    "Encerrando por inatividade..."
                )

                # Mesmo mecanismo de fala espontânea já usado por
                # rede_jarvis e admin_terminal (_enviar_anuncio_espontaneo)
                # — chamado direto (await), não via _falar_espontaneamente,
                # porque esta tarefa já roda dentro do próprio loop
                # assíncrono do worker (self.loop), sem precisar da
                # ponte thread-safe que _falar_espontaneamente existe
                # pra prover a quem chama de FORA dele.
                await self._enviar_anuncio_espontaneo(
                    "que a chamada vai ser encerrada agora por "
                    "causa de um tempo sem atividade"
                )

                # Mesmo fluxo de encerramento já usado por
                # encerrar_chamada (a tool de voz) — reaproveitado,
                # não duplicado: espera a despedida terminar de tocar
                # e só então pede o encerramento à interface.
                if self.tarefa_encerramento:
                    self.tarefa_encerramento.cancel()

                self.tarefa_encerramento = asyncio.create_task(
                    self.encerrar_apos_resposta()
                )

                break

        except asyncio.CancelledError:
            pass

    # Verifica periodicamente se algum envio pra sessão do Gemini
    # travou ou falhou (ver _enviar_para_sessao/self.conexao_travada)
    # e, se sim, encerra a chamada sozinha — checa a cada 1s (rápido,
    # perto de instantâneo do ponto de vista do usuário) e, ao
    # contrário de verificar_inatividade/encerrar_chamada, NÃO tenta
    # avisar por voz antes de encerrar: um aviso por voz também é um
    # envio pra sessão (_enviar_anuncio_espontaneo, que também passa
    # por _enviar_para_sessao), que também poderia travar do mesmo
    # jeito — tentar avisar aqui recriaria exatamente o problema que
    # este método existe pra evitar. Só desliga a chamada e deixa o
    # usuário iniciar uma nova.
    #
    # BUG REAL relatado pelo usuário: pediu pra enviar um print num
    # canal do Discord, o jarvis executou errado (mandou só texto —
    # ver a correção de enviar_captura_discord_canal), disse que ia
    # tentar de novo, e a partir daí parou de responder por completo —
    # sem erro, sem fechar a chamada, precisou fechar pelo Gerenciador
    # de Tarefas. A hipótese mais provável é a própria conexão Live
    # travando silenciosamente, não uma função específica travando
    # (isso já tinha proteção própria, ver
    # _executar_chamada_de_funcao_com_timeout) — antes desta correção,
    # não existia NENHUM timeout em nada que manda dado pra sessão do
    # Gemini, então um travamento da conexão em si nunca seria
    # detectado nem recuperado.
    async def monitorar_conexao(self):
        while self.ativo:
            await asyncio.sleep(1)

            if self.conexao_travada:
                self.status_recebido.emit(
                    "A conexão com o Gemini parou de responder — "
                    "encerrando a chamada automaticamente."
                )

                self.encerrou_por_falha = True
                self.ativo = False
                break

    # Controla as capturas de tela e câmera,
    # impedindo repetição e chamadas simultâneas.
    #
    # origem="voz" é o padrão (todo despacho de tool_call que chega
    # aqui é por voz) — solicitar_analise_tela/solicitar_analise_camera
    # passam origem="botão" desde que passaram a chamar esta função
    # (em vez de enviar_tela_para_gemini/enviar_camera_para_gemini
    # direto) pra corrigir o mutex faltando nesses dois botões; sem
    # isso, um clique no botão mostraria "Comando de voz detectado"
    # incorretamente no status/log de atividade.
    async def processar_funcao_visual(
        self,
        nome,
        origem="voz",
    ):
        if self.executando_funcao_visual:
            return (
                "Uma análise visual já está em andamento. "
                "Use a última imagem recebida e responda ao usuário."
            )

        # time.monotonic() mede intervalos sem ser afetado
        # por alterações no relógio do computador.
        agora = time.monotonic()

        # Verifica se a mesma função visual foi chamada
        # novamente dentro do período de cooldown.
        repetido = (
            nome == self.ultima_funcao_visual
            and agora - self.tempo_ultima_funcao_visual
            < COOLDOWN_FUNCAO_VISUAL
        )

        if repetido:
            return (
                "Chamada visual duplicada ignorada. "
                "A imagem já foi capturada para este pedido. "
                "Use a última imagem recebida e responda sem "
                "chamar função novamente."
            )

        # Bloqueia novas capturas enquanto esta estiver em andamento.
        self.executando_funcao_visual = True
        self.ultima_funcao_visual = nome
        self.tempo_ultima_funcao_visual = agora

        try:
            if nome == "analisar_tela":
                self.status_recebido.emit(
                    "Comando de voz detectado: analisar tela."
                    if origem == "voz"
                    else "Botão pressionado: analisar tela."
                )

                await self.enviar_tela_para_gemini(
                    origem="voz"
                )

                return (
                    "A tela foi capturada e enviada. "
                    "Responda usando exatamente a última imagem recebida."
                )

            if nome == "analisar_camera":
                self.status_recebido.emit(
                    "Comando de voz detectado: analisar câmera."
                    if origem == "voz"
                    else "Botão pressionado: analisar câmera."
                )

                await self.enviar_camera_para_gemini(
                    origem="voz"
                )

                return (
                    "A câmera foi capturada e enviada. "
                    "Responda usando exatamente a última imagem recebida."
                )

            return "Função visual desconhecida."

        # Este bloco sempre é executado, mesmo se ocorrer erro.
        finally:
            self.executando_funcao_visual = False

    # MUTEX REAL FALTANDO, corrigido aqui: identificar_planta,
    # consultar_segunda_opiniao_visual, tirar_foto_camera e
    # _obter_ou_capturar_ultima_captura chamavam capturar_camera_bytes()
    # direto, sem passar por processar_funcao_visual — só
    # analisar_tela/analisar_camera tinham a proteção de
    # self.executando_funcao_visual. Isso só virou um risco real depois
    # que tool_calls passaram a rodar em paralelo (ver "Concurrent
    # function-call execution" no CLAUDE.md): duas dessas ferramentas
    # disparadas perto uma da outra podem disputar o mesmo handle da
    # webcam de verdade — o mesmo tipo de interferência entre duas
    # cv2.VideoCapture(0) concorrentes já medido e corrigido pro preview
    # de câmera (jarvis/pacotes/camera_preview/). Também usado por
    # salvar_print_tela por consistência com o mutex já existente (que
    # cobre "tela e câmera" pelo mesmo motivo de analisar_tela/
    # analisar_camera), mesmo essa captura sendo só de tela (mss) —
    # a screenshot em si não sofre a interferência documentada.
    #
    # Reaproveita o MESMO self.executando_funcao_visual de
    # processar_funcao_visual (não um lock novo): as duas proteções, na
    # prática, protegem o mesmo recurso físico. NUNCA chamar isto de
    # dentro de processar_funcao_visual (ou de enviar_camera_para_gemini/
    # enviar_tela_para_gemini quando chamados por ele) — o mutex já
    # está adquirido nesse caminho, e adquiri-lo de novo aqui devolveria
    # "ocupado" pra si mesmo. Só usar em pontos que capturam FORA desse
    # fluxo (ver os pontos de uso abaixo).
    #
    # Segue o mesmo padrão de recusa imediata ("tente de novo") de
    # processar_funcao_visual — nunca espera a vez, pra não segurar uma
    # tool_call em andamento indefinidamente. Uso:
    #     async with self._mutex_funcao_visual() as mutex_livre:
    #         if not mutex_livre:
    #             ... mensagem de "ocupado, tente de novo" ...
    #         else:
    #             ... captura ...
    @contextlib.asynccontextmanager
    async def _mutex_funcao_visual(self):
        if self.executando_funcao_visual:
            yield False
            return

        self.executando_funcao_visual = True

        try:
            yield True

        finally:
            self.executando_funcao_visual = False

    # Envia um frame capturado da tela para o Gemini durante a
    # visualização contínua, pelo mesmo canal de streaming em
    # tempo real usado pelo áudio (send_realtime_input).
    async def _enviar_frame_visualizacao_continua(
        self,
        frame_bytes,
    ):
        if not self.sessao:
            return

        await self._enviar_para_sessao(
            self.sessao.send_realtime_input(
                video=types.Blob(
                    data=frame_bytes,
                    mime_type="image/jpeg",
                )
            )
        )

    # Chamado pelo próprio MonitorTelaContinuo quando ele se
    # encerra sozinho por ter atingido o tempo máximo permitido,
    # sem que o usuário tenha pedido para parar.
    async def _visualizacao_continua_encerrada_por_timeout(
        self,
    ):
        self.monitor_tela_continuo = None

        self.status_recebido.emit(
            "Visualização contínua encerrada automaticamente "
            "por tempo limite."
        )

    # Inicia a captura contínua de frames da tela, enviando cada
    # frame ao Gemini em tempo real até ser interrompida.
    async def iniciar_visualizacao_continua(
        self,
    ):
        # Evita iniciar uma segunda captura contínua
        # enquanto outra já estiver em andamento.
        if (
            self.monitor_tela_continuo
            and self.monitor_tela_continuo.esta_ativo
        ):
            return (
                "A visualização contínua já está em andamento. "
                "Continue acompanhando o que o usuário está "
                "mostrando, sem chamar a função novamente."
            )

        self.status_recebido.emit(
            "Visualização contínua da tela iniciada."
        )

        self.monitor_tela_continuo = MonitorTelaContinuo(
            callback_frame=(
                self._enviar_frame_visualizacao_continua
            ),
            intervalo_segundos=(
                INTERVALO_VISUALIZACAO_CONTINUA
            ),
            timeout_segundos=(
                TIMEOUT_VISUALIZACAO_CONTINUA
            ),
            callback_encerrado=(
                self._visualizacao_continua_encerrada_por_timeout
            ),
            # Segue o monitor onde o cursor está a cada frame (não o
            # monitor principal fixo) — a visualização REMOTA
            # (jarvis/pacotes/rede_jarvis/visualizacao_remota.py) usa a mesma classe
            # sem passar isso, então continua com o padrão fixo.
            funcao_captura=capturar_monitor_do_cursor_bytes,
        )

        await self.monitor_tela_continuo.iniciar()

        return (
            "Visualização contínua da tela iniciada. Continue "
            "ouvindo o usuário normalmente enquanto ele mostra "
            "o que precisa, sem chamar esta função novamente."
        )

    # Interrompe a captura contínua de frames da tela,
    # caso esteja em andamento.
    async def parar_visualizacao_continua(
        self,
    ):
        if (
            not self.monitor_tela_continuo
            or not self.monitor_tela_continuo.esta_ativo
        ):
            return (
                "Nenhuma visualização contínua estava em andamento."
            )

        self.status_recebido.emit(
            "Visualização contínua da tela encerrada."
        )

        await self.monitor_tela_continuo.parar()
        self.monitor_tela_continuo = None

        return "Visualização contínua da tela encerrada."

    # Reproduz os blocos de áudio enviados pelo Gemini
    # e atualiza o nível visual da interface.
    async def reproduzir_audio(
        self,
        fila_saida,
        fila_microfone,
    ):
        # Thread EXCLUSIVA da reprodução, criada só pra esta chamada.
        #
        # BUG REAL relatado pelo usuário ("trava enquanto fala, mas o
        # PC está tranquilo, CPU/RAM/GPU baixos"): a escrita de cada
        # bloco de áudio ia pro pool padrão do asyncio.to_thread — o
        # MESMO pool usado pelas outras 36 chamadas bloqueantes deste
        # arquivo (tools, capturas de câmera, comandos admin, envio de
        # email...). O pool tem min(32, núcleos+4) workers; quando
        # enchia, o bloco de áudio entrava na FILA e simplesmente
        # esperava. Medido nesta máquina (24 núcleos, 28 workers): com
        # o pool ocupado, um bloco esperou 1,69s pela vez dele — o
        # equivalente a 40 blocos, ou seja, a fala parando no meio.
        # E o CPU aparece ocioso o tempo todo, porque os workers estão
        # PARADOS esperando I/O, não calculando: exatamente o que o
        # gerenciador de tarefas mostrava.
        #
        # Com um executor próprio de um worker só, a reprodução nunca
        # mais disputa vez com nada. É literalmente dar folga pro
        # áudio — o oposto de precisar de mais RAM ou GPU.
        executor_audio = concurrent.futures.ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="jarvis-audio",
        )

        laco = asyncio.get_running_loop()

        try:
            await self._laco_reproducao(
                fila_saida,
                fila_microfone,
                laco,
                executor_audio,
            )

        finally:
            # cancel_futures + wait=False: se a escrita estiver presa
            # no dispositivo, encerrar a chamada não pode ficar
            # esperando por ela.
            executor_audio.shutdown(
                wait=False,
                cancel_futures=True,
            )

    async def _laco_reproducao(
        self,
        fila_saida,
        fila_microfone,
        laco,
        executor_audio,
    ):
        # Abre o dispositivo de saída de áudio no formato PCM.
        with sd.RawOutputStream(
            samplerate=TAXA_SAIDA,
            blocksize=BLOCO,
            dtype="int16",
            channels=CANAIS,
            latency=LATENCIA_SAIDA,
        ) as saida:
            # Mantém a sessão viva até que parar() altere self.ativo.
            while self.ativo:
                audio_bytes = await fila_saida.get()

                # [DIAGNÓSTICO DE ATRASO EM CONVERSAS LONGAS] popleft()
                # porque _debug_fila_timestamps é preenchido em ordem
                # FIFO por receber_audio (append), na mesma ordem que
                # fila_saida.get() retira — mede exatamente quanto
                # tempo ESTE bloco específico esperou entre entrar na
                # fila e ser tirado dela agora, pouco antes de tocar.
                if DEBUG_TIMING_FILA_SAIDA and self._debug_fila_timestamps:
                    atraso = (
                        time.monotonic()
                        - self._debug_fila_timestamps.popleft()
                    )

                    self._debug_atraso_max_desde_tick = max(
                        self._debug_atraso_max_desde_tick,
                        atraso,
                    )
                    self._debug_atraso_soma_desde_tick += atraso
                    self._debug_atraso_contagem_desde_tick += 1

                # Mantém o microfone bloqueado durante toda a reprodução
                # e descarta qualquer bloco antigo que ainda tenha sobrado.
                # [DIAGNÓSTICO DE MICROFONE] Ver DEBUG_TIMING_MICROFONE.
                if DEBUG_TIMING_MICROFONE and not self.alfred_falando:
                    self._debug_inicio_mudo = time.perf_counter()
                    print(
                        "[TIMING-MIC] Microfone silenciado "
                        "(reproduzir_audio: tocando um bloco)."
                    )

                self.alfred_falando = True
                self.limpar_fila_microfone(
                    fila_microfone
                )

                # Calcula o volume aproximado do bloco atual.
                nivel = self.calcular_nivel_audio(
                    audio_bytes
                )

                self.nivel_audio.emit(
                    nivel
                )

                # Reproduz o bloco em uma thread auxiliar.
                # Isso evita que drivers de áudio mais lentos bloqueiem
                # o loop que recebe os próximos blocos do Gemini.
                # wait_for por fora do to_thread: se o dispositivo
                # de saída travar (jogo em tela cheia tomando a placa
                # de som, driver perdido), isso desiste em vez de
                # ficar preso pra sempre — o supervisor da tarefa
                # encerra a chamada com erro visível. Ver
                # TIMEOUT_ESCRITA_AUDIO_SEGUNDOS.
                # run_in_executor com o executor EXCLUSIVO, nunca
                # asyncio.to_thread (que usaria o pool compartilhado —
                # ver o comentário em reproduzir_audio).
                await asyncio.wait_for(
                    laco.run_in_executor(
                        executor_audio,
                        saida.write,
                        audio_bytes,
                    ),
                    timeout=TIMEOUT_ESCRITA_AUDIO_SEGUNDOS,
                )

                self.timestamp_ultima_reproducao = time.monotonic()

                # Não adicionar asyncio.sleep aqui.
                # Uma pausa por bloco deixa a voz picotando.

                if self.tarefa_liberar_microfone:
                    self.tarefa_liberar_microfone.cancel()

                self.tarefa_liberar_microfone = asyncio.create_task(
                    self.liberar_microfone_apos_fala()
                )

    @staticmethod
    def limpar_fila_microfone(
        fila_microfone,
    ):
        """
        Descarta todos os blocos de áudio que ainda aguardavam envio.
        Isso impede que um trecho capturado antes da resposta seja
        enviado ao Gemini enquanto o assistente já está falando.
        """

        while True:
            try:
                fila_microfone.get_nowait()

            except asyncio.QueueEmpty:
                break

    @staticmethod
    def limpar_fila_saida(
        fila_saida,
    ):
        """
        Descarta todos os blocos de áudio de resposta que ainda
        aguardavam reprodução. Usado só quando o servidor sinaliza
        resposta.server_content.interrupted (modo interrupcao
        habilitado, ver receber_audio) — pra parar de tocar a
        resposta antiga na hora, em vez de deixar ela terminar
        sozinha.
        """

        while True:
            try:
                fila_saida.get_nowait()

            except asyncio.QueueEmpty:
                break

    # O método abaixo não utiliza self, por isso é estático.
    @staticmethod
    # Calcula um valor entre 0 e 1 com base no pico
    # das amostras do áudio recebido.
    def calcular_nivel_audio(
        audio_bytes,
    ):
        if not audio_bytes:
            return 0.0

        try:
            # Interpreta os bytes como inteiros de 16 bits.
            amostras = array(
                "h",
                audio_bytes,
            )

            if not amostras:
                return 0.0

            # Obtém a maior amplitude presente no bloco.
            pico = max(
                abs(amostra)
                for amostra in amostras
            )

            # Normaliza a amplitude para a faixa aproximada de 0 a 1.
            nivel = pico / 32768.0
            # Ajusta a curva para deixar a animação visual mais sensível.
            nivel = nivel ** 0.55

            return max(
                0.0,
                min(
                    1.0,
                    nivel,
                ),
            )

        except (
            ValueError,
            OverflowError,
        ):
            return 0.0

    # Aguarda um pequeno intervalo depois da fala
    # antes de liberar o microfone novamente.
    async def liberar_microfone_apos_fala(
        self,
    ):
        try:
            await asyncio.sleep(
                ATRASO_REABRIR_MICROFONE
            )

            self.alfred_falando = False

            # [DIAGNÓSTICO DE MICROFONE] Ver DEBUG_TIMING_MICROFONE.
            if DEBUG_TIMING_MICROFONE and self._debug_inicio_mudo:
                duracao_mudo_ms = (
                    time.perf_counter() - self._debug_inicio_mudo
                ) * 1000

                print(
                    f"[TIMING-MIC] Microfone reaberto depois de "
                    f"{duracao_mudo_ms:.0f}ms mudo."
                )

                self._debug_inicio_mudo = None

            self.nivel_audio.emit(
                0.0
            )

        except asyncio.CancelledError:
            pass

    # Método chamado pela interface quando o botão
    # de análise de tela é pressionado.
    def solicitar_analise_tela(
        self,
    ):
        if not self.loop or not self.sessao:
            self.erro_recebido.emit(
                "Sessão Gemini ainda não está pronta."
            )

            return

        # MUTEX REAL FALTANDO, corrigido aqui: chamava
        # enviar_tela_para_gemini diretamente, sem passar pelo mutex
        # de processar_funcao_visual — um clique no botão bem perto de
        # um "analisa a tela"/"analisa a câmera" por voz não tinha
        # nenhuma proteção. processar_funcao_visual já faz exatamente
        # o mesmo (captura + envia + emite status), só que protegido —
        # a troca é direta, o retorno continua sendo descartado aqui
        # como sempre foi.
        asyncio.run_coroutine_threadsafe(
            self.processar_funcao_visual(
                "analisar_tela",
                origem="botão",
            ),
            self.loop,
        )

    # Captura a tela, envia a imagem ao Gemini
    # e adiciona instruções específicas para a análise.
    async def enviar_tela_para_gemini(
        self,
        origem="botao",
    ):
        try:
            self.status_recebido.emit(
                "Capturando tela..."
            )

            # Captura o monitor onde o cursor do mouse está agora,
            # no formato JPEG em bytes — não o monitor principal
            # fixo, já que o usuário tem vários monitores. Em
            # asyncio.to_thread — mesmo motivo do capturar_camera_bytes
            # em enviar_camera_para_gemini, logo abaixo.
            imagem_bytes = await asyncio.to_thread(
                capturar_monitor_do_cursor_bytes
            )

            # Envia uma nova mensagem contendo imagem e instrução textual.
            await self._enviar_para_sessao(
                self.sessao.send_client_content(
                    turns=[
                        types.Content(
                            role="user",
                            parts=[
                                types.Part(
                                    inline_data=types.Blob(
                                        data=imagem_bytes,
                                        mime_type="image/jpeg",
                                    )
                                ),

                                types.Part(
                                    text=prompts.ANALISE_IMAGEM_PONTUAL.format(
                                        origem="tela"
                                    )
                                ),
                            ],
                        )
                    ],
                    turn_complete=True,
                )
            )

            self.status_recebido.emit(
                "Tela enviada para análise."
            )

        except Exception as erro:
            self.erro_recebido.emit(
                f"Erro ao analisar tela: {erro}"
            )

    # Método chamado pela interface quando o botão
    # de análise da câmera é pressionado.
    def solicitar_analise_camera(
        self,
    ):
        if not self.loop or not self.sessao:
            self.erro_recebido.emit(
                "Sessão Gemini ainda não está pronta."
            )

            return

        # MUTEX REAL FALTANDO, corrigido aqui — mesmo caso de
        # solicitar_analise_tela logo acima, ver o comentário lá.
        asyncio.run_coroutine_threadsafe(
            self.processar_funcao_visual(
                "analisar_camera",
                origem="botão",
            ),
            self.loop,
        )

    # Captura uma imagem da webcam e envia
    # o conteúdo para análise do Gemini.
    async def enviar_camera_para_gemini(
        self,
        origem="botao",
    ):
        try:
            self.status_recebido.emit(
                "Capturando imagem da câmera..."
            )

            # Captura o quadro atual da webcam como JPEG em bytes.
            #
            # BUG REAL corrigido aqui (e em todo outro ponto deste
            # arquivo que chamava capturar_camera_bytes()/
            # capturar_monitor_do_cursor_bytes() direto): estava sendo
            # chamada de forma síncrona, direto dentro de uma corrotina
            # async, sem asyncio.to_thread — ao contrário do que um
            # comentário antigo (removido) afirmava ("mesmo padrão já
            # usado... por design"). capturar_camera_bytes() tem um
            # time.sleep(0.8) explícito (mais abertura/leitura/liberação
            # do dispositivo), então cada chamada direta travava o loop
            # assíncrono inteiro — inclusive enviar_microfone e
            # reproduzir_audio — pelo tempo da captura inteira. Isso é
            # muito provavelmente a causa raiz do travamento "ele
            # responde, executa uma ação, mas demora muito pra voltar a
            # me ouvir" reportado pelo usuário logo depois de rodar uma
            # tool visual (aqui e em identificar_planta/
            # consultar_segunda_opiniao_visual/salvar_print_tela/
            # tirar_foto_camera/_obter_ou_capturar_ultima_captura —
            # todos corrigidos junto). Regra do projeto (ver CLAUDE.md):
            # toda chamada síncrona bloqueante dentro do worker async
            # precisa estar em asyncio.to_thread.
            imagem_bytes = await asyncio.to_thread(
                capturar_camera_bytes
            )

            # Envia uma nova mensagem contendo imagem e instrução textual.
            await self._enviar_para_sessao(
                self.sessao.send_client_content(
                    turns=[
                        types.Content(
                            role="user",
                            parts=[
                                types.Part(
                                    inline_data=types.Blob(
                                        data=imagem_bytes,
                                        mime_type="image/jpeg",
                                    )
                                ),

                                types.Part(
                                    text=prompts.ANALISE_IMAGEM_PONTUAL.format(
                                        origem="câmera"
                                    )
                                ),
                            ],
                        )
                    ],
                    turn_complete=True,
                )
            )

            self.status_recebido.emit(
                "Imagem da câmera enviada para análise."
            )

        except Exception as erro:
            self.erro_recebido.emit(
                f"Erro ao analisar câmera: {erro}"
            )

    # Encerra o loop principal da sessão e zera o nível de áudio.
    def parar(self):
        self.ativo = False

        # Sem isto, o botão de encerrar não teria efeito nenhum
        # enquanto o cérebro reserva estivesse conduzindo a conversa
        # (ele roda depois que self.ativo já é False, ver executar()).
        self.reserva_ativa = False

        self.nivel_audio.emit(
            0.0
        )