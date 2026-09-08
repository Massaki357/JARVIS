# Terceiro cérebro de voz do ALFRED: o servidor local (alfred-server),
# rodando em Docker nesta mesma máquina e conversando por MQTT.
#
# COMO ELE DIFERE DOS OUTROS DOIS, e por que o código não pôde ser
# copiado dos outros workers:
#
# O Gemini Live e a Realtime API da OpenAI são sessões de STREAMING
# bidirecional — o áudio do microfone é empurrado bloco a bloco em
# tempo real e o SERVIDOR decide onde o turno do usuário terminou
# (VAD do lado de lá). O alfred-server é requisição/resposta com
# ARQUIVOS INTEIROS. Isso obriga este worker a fazer duas coisas que
# nenhum dos outros dois faz:
#
#   1. Decidir sozinho onde a frase termina (o VAD por silêncio em
#      _capturar_frase), porque não há ninguém do outro lado para
#      fazer isso.
#   2. Conversar por turnos estritamente sequenciais — captura,
#      envia, espera, toca, volta a capturar — em vez de manter
#      tarefas de envio e recepção rodando em paralelo.
#
# O TURNO TEM TRÊS PARTES, e a do meio é toda daqui:
#
#   ETAPA 1  áudio  -> jarvis/audio/entrada  -> jarvis/texto/saida
#            (JSON {"texto","tom","sexo"})
#   ROTEAMENTO  o texto passa por jarvis/roteamento_hierarquico —
#            o MESMO motor que decide ferramenta-vs-conversa. Se for
#            ferramenta, ele já a executa, e o servidor NÃO é chamado
#            neste turno.
#   ETAPA 2  texto  -> jarvis/texto/entrada  -> jarvis/audio/saida
#            (o WAV falado), só quando era conversa.
#
# O servidor não sabe como essa decisão do meio é tomada, e é de
# propósito: lá não existe ferramenta, perfil nem catálogo. Foi
# exatamente para abrir espaço para ela que o pipeline dele foi
# partido em duas metades.
#
# LIMITAÇÕES INERENTES AO PROTOCOLO DO SERVIDOR (não são pendências
# a implementar depois — o canal simplesmente não existe):
#
#   - O servidor não faz function-calling: quem decide e executa
#     ferramenta aqui é o roteamento hierárquico, sobre o TEXTO
#     transcrito. Os perfis (jarvis/nucleo/perfis/), o prompt de
#     sistema e o gate da palavra-chave continuam sem valer neste
#     modo — eles pertencem à sessão do Gemini/OpenAI, que aqui não
#     existe. Um turno resolvido por ferramenta não tem voz: o
#     resultado aparece na interface (ver _registrar_resultado_local).
#
#   - AS 16 FERRAMENTAS NATIVAS DO GEMINI NÃO EXISTEM AQUI. Elas são
#     branches do elif de processar_chamada_de_funcao em
#     jarvis/cerebro/gemini/cliente_live.py, não pacotes — não estão no
#     catálogo do roteamento e não há código de pacote por trás delas,
#     então _despachar jamais as encontraria. São:
#
#       visão ao vivo:      analisar_tela, analisar_camera,
#                           iniciar_visualizacao_continua,
#                           parar_visualizacao_continua
#       captura em disco:   salvar_print_tela, tirar_foto_camera
#       envio de captura:   enviar_captura_email,
#                           enviar_captura_discord_dm,
#                           enviar_captura_discord_canal,
#                           enviar_captura_remoto
#       email:              preparar_email, confirmar_envio_email,
#                           ler_emails, baixar_anexo_email
#       controle de chamada: encerrar_chamada, pausar_chamada
#
#     DUAS JÁ FORAM PORTADAS. analisar_tela e analisar_camera existem
#     aqui como descrever_tela e descrever_camera, no pacote
#     jarvis/pacotes/descricao_visual/: o cliente captura e um modelo
#     de visão devolve a descrição em TEXTO, que entra no turno como
#     resultado de ferramenta. Nomes diferentes de propósito — o
#     despacho do worker do Gemini percorre PACOTES_REGISTRADOS antes
#     da cadeia nativa, então reusar o nome sequestraria o
#     comportamento dele.
#
#     iniciar_visualizacao_continua e parar_visualizacao_continua
#     continuam INDISPONÍVEIS POR DESIGN, e não é a mesma coisa:
#     dependem de streaming de vídeo em tempo real, com frames
#     injetados continuamente na sessão. Replicar isso por chamadas
#     repetidas de "captura avulsa + descreve" seria outra feature, com
#     custo e latência muito maiores — uma chamada de visão leva
#     segundos, e a visualização contínua manda vários frames por
#     segundo. Não foi implementado, de propósito.
#
#     As de email e captura são só Python e seriam portáveis para um
#     pacote pelo mesmo caminho — só não foram ainda.
#
#     Consequência prática que vale saber: encerrar_chamada não existe
#     aqui, então neste modo a chamada só termina pelo botão. E o que
#     o usuário pede como "olha minha tela" / "vê a câmera" é recusado
#     por design, não por bug.
#
#     O que EXISTE de visão neste modo vem do catálogo:
#     descrever_tela e descrever_camera (as portadas),
#     identificar_planta e consultar_segunda_opiniao_visual — as
#     quatro dependem de FERRAMENTAS_QUE_PRECISAM_DE_IMAGEM abaixo —,
#     mais abrir_camera/fechar_camera e clicar_elemento_visual, que
#     captura a tela sozinha internamente.
#   - Não há retomada de sessão: solicitou_reconexao e
#     session_handle_atualizado existem só por paridade de interface
#     (mesma situação do worker da OpenAI) e nunca são emitidos.
#   - A interrupção de fala (config.json -> "interrupcao") FUNCIONA,
#     mas por um caminho diferente do Gemini. Lá o SERVIDOR detecta
#     que o usuário falou por cima e devolve
#     server_content.interrupted, porque o microfone segue sendo
#     transmitido durante a fala. Aqui o alfred-server já entregou o
#     WAV inteiro e não sabe mais nada do turno, então quem detecta é
#     este cliente: _vigiar_interrupcao roda junto da reprodução e
#     usa o mesmo Silero que fecha as frases. Ao detectar, a
#     reprodução para na hora, o resto do WAV é descartado e a captura
#     da nova frase começa imediatamente.
#
#     ⚠ EXIGE FONE DE OUVIDO, e isto é medido, não precaução: o Silero
#     decide por CONTEÚDO, e a voz do assistente é voz humana.
#     Alimentando o detector com respostas reais deste servidor, ele
#     viu fala em 68% a 82% dos blocos — e a -24 dB (eco distante de
#     caixa) ainda 67% a 81%, porque atenuar não muda o conteúdo. Em
#     caixas de som, portanto, ele se interrompe sozinho em quase toda
#     resposta. Não há cancelamento de eco em lugar nenhum do projeto.
#     Por isso é opt-in e vem desligado.
#
#     Interromper durante a GERAÇÃO (antes de tocar) não é tratado: o
#     protocolo do servidor não tem canal de cancelamento, e uma
#     resposta que chegue tarde já é descartada por _resolver_futuro.
#
# O que é IGUAL aos outros dois, de propósito: os sete Signals, a
# assinatura do construtor e os métodos públicos. É essa paridade que
# deixa jarvis/ui/janela_principal.py trocar de cérebro mexendo em uma
# função só (_classe_do_worker).
import asyncio
import concurrent.futures
import collections
import json
import time
import winsound

from array import array
from typing import NamedTuple

import sounddevice as sd

from PySide6.QtCore import QThread, Signal

from jarvis import roteamento_hierarquico
from jarvis.nucleo import perfis
from jarvis.nucleo.config import obter_nome_jarvis
from jarvis.nucleo.preferencias import interrupcao_ativa
from jarvis.nucleo.registro_pacotes import TOOLS_QUE_PRECISAM_DE_IMAGEM
from jarvis.nucleo.sinalizador import obter_sinalizador
from jarvis.pacotes import ativacao_voz
from jarvis.roteamento_hierarquico import config as config_roteamento
from jarvis.servicos.visao import captura_camera, captura_tela

from . import audio_wav
from . import config
from . import contexto
from . import vad_silero
from .mqtt_voz import ClienteVozLocal


# Mesmos parâmetros de captura do worker do Gemini — 16 kHz mono
# 16 bits é também o formato que o servidor prefere, então o WAV
# publicado é literalmente o áudio capturado com um cabeçalho na
# frente, sem reamostragem nenhuma no caminho.
TAXA_ENTRADA = 16000
CANAIS = 1
BLOCO = 1024

# Não existe TAXA_SAIDA fixa aqui, ao contrário dos outros dois
# workers: a taxa do áudio de resposta vem do cabeçalho do WAV que o
# servidor devolveu (ver audio_wav.wav_para_pcm) e o dispositivo é
# aberto nela. Fixar um valor deixaria a voz acelerada ou arrastada
# se o servidor mudasse de taxa.

# Limite de blocos aguardando processamento, igual ao do worker do
# Gemini: evita acúmulo de áudio velho se a máquina engasgar.
LIMITE_FILA_MICROFONE = 50

# Tempo de segurança antes de reabrir o microfone depois que o
# assistente termina de falar (retorno de áudio, drivers lentos).
ATRASO_REABRIR_MICROFONE = 0.8

# ---- Interrupção da fala (barge-in), só com "interrupcao": true -----
#
# EXIGE FONE DE OUVIDO. O Silero decide por CONTEÚDO, e a voz do
# assistente é voz humana: alimentando o detector com WAVs de resposta
# reais deste servidor, ele classificou 68% a 82% dos blocos como fala.
# E ATENUAR NÃO RESOLVE — a -24 dB (eco distante de caixa) ainda deu
# 67% a 81%, porque fala baixa continua sendo fala. Ou seja, em caixas
# de som o assistente se interrompe sozinho em quase toda resposta.
# Não existe cancelamento de eco acústico em lugar nenhum do projeto.
#
# Blocos CONSECUTIVOS de fala para cortar a reprodução. Um bloco só
# seria gatilho fácil demais (um estalo de teclado, uma respiração);
# cinco blocos são ~320 ms, que é fala de verdade e ainda assim rápido
# o bastante para não parecer que o assistente ignorou a interrupção.
BLOCOS_FALA_PARA_INTERROMPER = 5

# Carência no começo da reprodução: neste intervalo a interrupção nem
# é avaliada. Serve para a cauda da própria frase do usuário, que ainda
# está no ar quando o áudio começa a tocar — sem isso, ele se
# interromperia com o fim da própria pergunta.
CARENCIA_INTERRUPCAO_SEGUNDOS = 0.5

# Mesma folga de buffer do worker do Gemini.
LATENCIA_SAIDA = "high"

# Teto para a escrita de um pedaço de áudio no dispositivo. Um
# dispositivo de saída que para de consumir (jogo em tela cheia
# tomando a placa de som) trava sem levantar exceção nenhuma — sem
# este wait_for a chamada ficaria muda e presa para sempre. Mesma
# proteção e mesmo valor de jarvis/cerebro/gemini/cliente_live.py.
TIMEOUT_ESCRITA_AUDIO_SEGUNDOS = 10

# Ferramentas do catálogo que só funcionam se alguém capturar a
# imagem e entregar para elas — no cliente do Gemini isso é feito pelo
# próprio cliente, que injeta imagem_bytes em args antes do despacho
# (ver processar_chamada_de_funcao em jarvis/cerebro/gemini/cliente_live.py).
#
# Sem o equivalente aqui, as primeiras duas eram alcançáveis pelo
# roteamento e falhavam SEMPRE ("nenhuma imagem foi capturada"): o
# catálogo as oferece e o pacote as reconhece, mas ninguém entregava
# a imagem.
#
# O valor diz QUAL captura usar. Guardado como texto, e não como a
# função em si, de propósito: a função é resolvida na hora da chamada
# (ver _CAPTURAS), o que mantém o módulo substituível em teste sem
# precisar reconstruir este mapa.
# A lista mora em jarvis/nucleo/registro_pacotes.py, e não aqui, desde
# que um BUG REAL mostrou o custo de cada cliente ter a sua: este
# worker tinha as quatro entradas, mas os workers do Gemini e da
# OpenAI só tinham duas, então descrever_tela/descrever_camera
# falhavam SEMPRE nos dois com "nenhuma imagem foi capturada" — e o
# pacote está em PACOTES_REGISTRADOS, que é global, então os três
# declaravam as tools. O alias local continua por clareza de leitura
# neste arquivo; a fonte da verdade é uma só.
FERRAMENTAS_QUE_PRECISAM_DE_IMAGEM = TOOLS_QUE_PRECISAM_DE_IMAGEM

# capturar_monitor_do_cursor_bytes, e não capturar_tela_bytes: em
# monitor duplo, "olha minha tela" quer dizer o monitor que o usuário
# está olhando, não o primário fixo. É a mesma função que o
# analisar_tela do Gemini usa.
_CAPTURAS = {
    "tela": lambda: captura_tela.capturar_monitor_do_cursor_bytes(),
    "camera": lambda: captura_camera.capturar_camera_bytes(),
}

class RespostaFalada(NamedTuple):
    """
    O que a ETAPA 2 devolve: o WAV e o TEXTO que ele fala.

    Os dois andam juntos porque o texto só serve se chegar ao MESMO
    ponto do turno em que o áudio chega — é ali que ele entra em
    transcricao_conversa, para que o turno seguinte saiba o que o
    assistente respondeu, e não só o que o usuário perguntou.

    texto é None quando o servidor não mandou a user property
    (imagem antiga do alfred-server, ou uma conexão v3.1.1). Nesse
    caso o áudio toca normalmente e o histórico segue só com o lado
    do usuário, exatamente como era antes.
    """

    audio: bytes
    texto: str | None


# Teto do histórico da conversa, igual ao dos outros dois workers.
# Aqui ele tem um segundo peso: esta lista é também o histórico
# enviado ao roteamento hierárquico a cada turno.
MAXIMO_MENSAGENS_TRANSCRICAO = 12

# Beep local de "chamada iniciada", igual ao dos outros workers.
FREQUENCIA_BEEP_CHAMADA_INICIADA = 880
DURACAO_BEEP_CHAMADA_INICIADA_MS = 150

# Mensagem única para tudo que este modo não tem como fazer. Note que
# FERRAMENTAS funcionam (pelo roteamento hierárquico, sobre o texto
# transcrito) — o que não existe aqui é canal para IMAGEM e para
# TEXTO digitado, porque o servidor só recebe áudio.
MENSAGEM_SEM_SUPORTE = (
    "O cérebro de voz local (alfred-server) só recebe áudio: não dá "
    "para mandar imagem nem texto digitado. Troque PROVEDOR_IA para "
    "gemini ou openai se precisar disso."
)


class VozLocalWorker(QThread):
    # ================================================================
    # SINAIS — os mesmos sete dos outros dois workers, na mesma ordem.
    # ================================================================
    status_recebido = Signal(str)
    erro_recebido = Signal(str)
    chamada_encerrada = Signal()
    nivel_audio = Signal(float)
    solicitou_encerramento = Signal()

    # Existem só por paridade de interface: o protocolo do servidor
    # local não tem retomada de sessão, então nenhum dos dois é
    # emitido em momento algum (mesma situação do worker da OpenAI).
    solicitou_reconexao = Signal()
    session_handle_atualizado = Signal(str)

    # Também nunca emitido aqui: pausar a chamada por voz depende da
    # tool pausar_chamada, e não há ferramentas neste modo.
    solicitou_hibernacao = Signal()

    def __init__(
        self,
        session_handle=None,
        transcricao_inicial=None,
        ativado_por_voz=False,
        slug_perfil=None,
    ):
        super().__init__()

        self.ativo = True

        # O perfil não muda nada neste modo (não há ferramentas para
        # filtrar nem prompt para enviar), mas o atributo precisa
        # existir e ser resolvido do mesmo jeito: a janela lê
        # self.live_worker.slug_perfil ao encerrar a chamada.
        self.slug_perfil = slug_perfil or perfis.perfil_ativo()

        self.session_handle = session_handle
        self.ativado_por_voz = ativado_por_voz
        self.hibernacao_solicitada = False

        # Histórico da conversa, no mesmo formato dos outros dois
        # workers ({"role", "content"}) — o que a etapa 1 transcreve
        # entra aqui. Tem um segundo uso que lá não tem: é este mesmo
        # histórico que vai ao roteamento hierárquico a cada turno,
        # que espera exatamente esse formato.
        #
        # list(...) e não a lista recebida direto: a janela guarda a
        # referência dela, e continuar acrescentando no MESMO objeto
        # faria dois workers escreverem na mesma lista.
        self.transcricao_conversa = list(transcricao_inicial or [])

        # Detector de fala do VAD. Preenchido no início da chamada
        # (_preparar_detector_de_fala); None significa modo de
        # emergência por amplitude.
        self.detector_fala = None

        # Barge-in: cortar a fala do assistente quando o usuário fala
        # por cima. Lido UMA vez, como nos outros workers — trocar
        # config.json no meio da chamada não tem efeito até a próxima.
        self.interrupcao_habilitada = interrupcao_ativa()

        # Quantas vezes a fala foi cortada nesta chamada. Existe pelo
        # mesmo motivo do contador equivalente no worker do Gemini: uma
        # interrupção FALSA (eco da caixa de som, estalo de teclado) é
        # indistinguível de um travamento para quem ouve — a frase para
        # no meio e não volta. Se este número subir enquanto o usuário
        # está calado, o culpado é o barge-in, e a correção é
        # config.json -> "interrupcao": false, não mexer em código.
        self.interrupcoes_na_chamada = 0

        # Blocos de microfone que o vigia da reprodução já tinha
        # consumido quando detectou a interrupção. Viram a pré-fala da
        # próxima captura, senão as primeiras sílabas de quem
        # interrompeu se perdem. Ver _capturar_frase.
        self._blocos_apos_interrupcao = []

        self.loop = None

        # Conexão MQTT desta chamada (uma por chamada, sem singleton).
        self.cliente_mqtt = None

        # Future aguardando a resposta do turno atual. Escrito pelo
        # ciclo de conversa e resolvido pelos callbacks do MQTT.
        # None quando não há nenhum turno esperando resposta — é o que
        # faz uma mensagem fora de hora (retida no broker, ou chegando
        # depois de um timeout) ser descartada em vez de tocada.
        self._futuro_resposta = None

        # "texto" (etapa 1) ou "audio" (etapa 2) — qual metade do
        # pipeline o turno atual está esperando. É o que faz uma
        # resposta atrasada da outra metade ser descartada em vez de
        # aceita no lugar da certa (ver _resolver_futuro).
        self._tipo_esperado = None

        # Bloqueia o microfone enquanto o assistente fala, evitando
        # que ele escute a própria voz.
        self.alfred_falando = False

        # Marca que a chamada terminou por falha, e não porque o
        # usuário pediu — mesmo significado do atributo homônimo no
        # worker do Gemini.
        self.encerrou_por_falha = False

        # Sinal de vida do stream de entrada, marcado pelo callback do
        # sounddevice. Ver _vigiar_microfone().
        self.timestamp_ultimo_bloco_microfone = 0.0

    # ================================================================
    # CICLO DE VIDA DA THREAD
    # ================================================================

    def run(self):
        try:
            asyncio.run(self.executar())

        except Exception as erro:
            self.erro_recebido.emit(str(erro))

        finally:
            self.nivel_audio.emit(0.0)
            self.chamada_encerrada.emit()

    def parar(self):
        self.ativo = False
        self.nivel_audio.emit(0.0)

    async def executar(self):
        # O detector de palavra de ativação e esta chamada nunca podem
        # ter o microfone aberto ao mesmo tempo. Bloqueia até o
        # microfone dele estar de fato livre. Idempotente. Mesma
        # primeira linha dos outros dois workers.
        ativacao_voz.pausar()

        self.loop = asyncio.get_running_loop()

        fila_microfone = asyncio.Queue(
            maxsize=LIMITE_FILA_MICROFONE
        )

        # Thread EXCLUSIVA da reprodução, criada só para esta chamada.
        # Nunca asyncio.to_thread: o pool padrão é compartilhado com
        # todas as outras chamadas bloqueantes do processo e, quando
        # enche, a escrita do áudio entra na fila e a fala trava no
        # meio com a CPU ociosa. Mesmo motivo (e mesmo bug real já
        # diagnosticado) de jarvis/cerebro/gemini/cliente_live.py.
        executor_audio = concurrent.futures.ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="jarvis-audio-local",
        )

        tarefas = []

        try:
            self.status_recebido.emit(
                "Conectando ao servidor de voz local..."
            )

            # Carrega o modelo do VAD (e o baixa, na primeira vez).
            # Em thread: são dezenas de ms de I/O e inicialização do
            # onnxruntime, e na primeira execução pode incluir um
            # download — nada disso pode segurar o loop.
            await asyncio.to_thread(self._preparar_detector_de_fala)

            if self.interrupcao_habilitada:
                # O aviso vai para a INTERFACE, e no início de cada
                # chamada: a preferência mora em config.json, que não
                # aparece em tela nenhuma, e o sintoma de usá-la em
                # caixas de som (a fala parando sozinha no meio) é
                # idêntico ao de um travamento. Melhor dizer antes.
                self.status_recebido.emit(
                    "Interrupção ligada — use fone de ouvido: em caixas "
                    "de som o assistente se interrompe sozinho."
                )

            cliente = ClienteVozLocal(
                ao_receber_texto=self._ao_receber_texto_mqtt,
                ao_receber_saida=self._ao_receber_saida_mqtt,
                ao_receber_erro=self._ao_receber_erro_mqtt,
            )

            # conectar() bloqueia esperando o CONNACK — nunca no loop.
            sucesso, mensagem = await asyncio.to_thread(
                cliente.conectar
            )

            if not sucesso:
                self.erro_recebido.emit(mensagem)
                self.encerrou_por_falha = True

                return

            self.cliente_mqtt = cliente

            # winsound.Beep é bloqueante, então vai para uma thread —
            # mesma convenção dos outros workers.
            await asyncio.to_thread(
                winsound.Beep,
                FREQUENCIA_BEEP_CHAMADA_INICIADA,
                DURACAO_BEEP_CHAMADA_INICIADA_MS,
            )

            # Sem chave da Groq o roteamento não roda, e TODO turno
            # vira conversa — as ferramentas simplesmente não
            # acontecem. Degrada em vez de derrubar a chamada, mas
            # avisa: silenciosamente sem ferramentas é pior do que
            # sem ferramentas.
            if not config_roteamento.GROQ_API_KEY:
                self.erro_recebido.emit(
                    "GROQ_API_KEY não configurada: neste modo as "
                    "ferramentas dependem dela, então tudo será "
                    "tratado como conversa."
                )

            self.status_recebido.emit(
                f"{obter_nome_jarvis()} local conectado. Pode falar."
            )

            tarefas = [
                asyncio.create_task(
                    self._tarefa_supervisionada(
                        "MICROFONE",
                        self.capturar_microfone(fila_microfone),
                    ),
                    name="MICROFONE",
                ),
                asyncio.create_task(
                    self._tarefa_supervisionada(
                        "CONVERSA",
                        self.ciclo_de_conversa(
                            fila_microfone,
                            executor_audio,
                        ),
                    ),
                    name="CONVERSA",
                ),
                asyncio.create_task(
                    self._tarefa_supervisionada(
                        "VIGIA",
                        self._vigiar_microfone(),
                    ),
                    name="VIGIA",
                ),
            ]

            # Mantém a chamada viva até parar() (botão/janela) ou até
            # uma das tarefas supervisionadas zerar self.ativo.
            while self.ativo:
                await asyncio.sleep(0.1)

        finally:
            self.ativo = False

            for tarefa in tarefas:
                tarefa.cancel()

            if tarefas:
                await asyncio.gather(
                    *tarefas,
                    return_exceptions=True,
                )

            # cancel_futures + wait=False: se a escrita estiver presa
            # no dispositivo, encerrar a chamada não pode esperar por
            # ela.
            executor_audio.shutdown(
                wait=False,
                cancel_futures=True,
            )

            if self.cliente_mqtt is not None:
                await asyncio.to_thread(
                    self.cliente_mqtt.desconectar
                )

                self.cliente_mqtt = None

            self.loop = None

            # Devolve o microfone ao detector de palavra de ativação.
            ativacao_voz.retomar()

            self.nivel_audio.emit(0.0)

    # ================================================================
    # SUPERVISÃO DAS TAREFAS
    # ================================================================

    # As tarefas só são aguardadas quando a chamada JÁ está
    # terminando, então uma exceção dentro delas morreria sem ninguém
    # ver: a tarefa morre, self.ativo continua True e a chamada fica
    # com cara de conectada para sempre. Mesmo supervisor (e mesmo bug
    # real já diagnosticado) de jarvis/cerebro/gemini/cliente_live.py.
    #
    # CancelledError não é capturado de propósito: desde o Python 3.8
    # ela não herda de Exception, e o cancelamento normal do
    # encerramento precisa passar reto sem virar "falha".
    async def _tarefa_supervisionada(self, nome, corrotina):
        try:
            await corrotina

        except Exception as erro:
            # str(TimeoutError()) é vazio — sem este fallback a
            # mensagem terminaria num dois-pontos solto.
            descricao = str(erro) or type(erro).__name__

            print(
                f"[VOZ LOCAL] A tarefa {nome} falhou: {descricao}"
            )

            self.erro_recebido.emit(
                f"Falha em {nome}: {descricao}"
            )

            self.encerrou_por_falha = True
            self.ativo = False

    # Detecta o microfone que para de entregar blocos SEM levantar
    # exceção nenhuma (dispositivo padrão trocando no meio da chamada,
    # headset USB reconectando): o sounddevice simplesmente para de
    # chamar o callback, o stream continua "aberto" e a chamada fica
    # surda com cara de viva. Mesmo raciocínio do vigiar_travamento do
    # worker do Gemini, reduzido à única condição que se aplica aqui.
    async def _vigiar_microfone(self):
        while self.ativo:
            await asyncio.sleep(5)

            if not self.ativo:
                break

            # 0.0 = o stream ainda não abriu; nunca alarma na partida.
            if not self.timestamp_ultimo_bloco_microfone:
                continue

            silencio = (
                time.monotonic()
                - self.timestamp_ultimo_bloco_microfone
            )

            if silencio > 10:
                print(
                    "[VOZ LOCAL] O microfone parou de entregar áudio "
                    f"há {silencio:.0f}s."
                )

                self.erro_recebido.emit(
                    "O microfone parou de entregar áudio. Encerrando "
                    "a chamada — a próxima abre o dispositivo atual."
                )

                self.encerrou_por_falha = True
                self.ativo = False

                break

    # ================================================================
    # CAPTURA DO MICROFONE
    # ================================================================

    # Idêntica em parâmetros e em proteções à do worker do Gemini: o
    # pedido era não mudar a lógica de captura, só o destino do áudio.
    async def capturar_microfone(self, fila_microfone):
        loop = asyncio.get_running_loop()

        def callback(
            indata,
            frames,
            time_info,
            status,
        ):
            # Sinal de VIDA do stream, marcado ANTES de qualquer
            # return antecipado de propósito: o que se mede aqui é se
            # o dispositivo continua entregando blocos, não se o áudio
            # vai ser aproveitado. Abaixo do check de alfred_falando,
            # uma resposta longa ficaria indistinguível de um
            # microfone morto. Ver _vigiar_microfone().
            self.timestamp_ultimo_bloco_microfone = time.monotonic()

            if not self.ativo:
                return

            # Mesma convenção das três guardas do worker do Gemini: o
            # microfone é ignorado enquanto o assistente fala, EXCETO
            # com a interrupção ligada — aí ele continua sendo
            # capturado de propósito, para o vigia da reprodução poder
            # detectar que o usuário falou por cima. Se um dia esta
            # linha voltar a ser um "if self.alfred_falando:" simples,
            # o barge-in morre em silêncio.
            if self.alfred_falando and not self.interrupcao_habilitada:
                return

            if status:
                print(
                    "Aviso microfone:",
                    status,
                )

            audio_bytes = bytes(indata)

            def adicionar_audio():
                if not self.ativo:
                    return

                # Mesma exceção da guarda acima.
                if self.alfred_falando and not self.interrupcao_habilitada:
                    return

                try:
                    fila_microfone.put_nowait(audio_bytes)

                except asyncio.QueueFull:
                    pass

            loop.call_soon_threadsafe(adicionar_audio)

        # try/except obrigatório: sem ele, uma falha ao abrir o
        # microfone ("Error querying device -1") mataria esta tarefa
        # em silêncio e a chamada continuaria "conectada", só que
        # surda para sempre. Bug real já corrigido no worker do
        # Gemini, replicado aqui pelo mesmo motivo.
        try:
            with sd.RawInputStream(
                samplerate=TAXA_ENTRADA,
                blocksize=BLOCO,
                dtype="int16",
                channels=CANAIS,
                callback=callback,
            ):
                self.timestamp_ultimo_bloco_microfone = time.monotonic()

                # O stream vive enquanto a chamada viver; quem consome
                # a fila é o ciclo de conversa.
                while self.ativo:
                    await asyncio.sleep(0.1)

        except Exception as erro:
            print(
                f"[VOZ LOCAL] Não foi possível abrir ou usar o "
                f"microfone: {erro}"
            )

            self.erro_recebido.emit(
                f"Não foi possível abrir o microfone: {erro}"
            )

            self.encerrou_por_falha = True
            self.ativo = False

    # ================================================================
    # CICLO DE CONVERSA (turnos sequenciais)
    # ================================================================

    # Um turno completo, em três decisões:
    #
    #   ETAPA 1  áudio  -> jarvis/audio/entrada  -> jarvis/texto/saida
    #   ROTEAMENTO  o texto passa por roteamento_hierarquico
    #   ETAPA 2  texto  -> jarvis/texto/entrada  -> jarvis/audio/saida
    #
    # A etapa 2 só acontece quando o roteamento decidiu que aquilo era
    # CONVERSA. Se era ferramenta, ela já foi executada localmente e o
    # servidor não é chamado neste turno — é justamente para permitir
    # essa decisão no meio que o pipeline foi partido em dois.
    async def ciclo_de_conversa(
        self,
        fila_microfone,
        executor_audio,
    ):
        while self.ativo:
            pcm_frase = await self._capturar_frase(fila_microfone)

            if not pcm_frase:
                # Silêncio, ruído curto demais, ou a chamada
                # encerrando — nada a enviar.
                continue

            duracao = audio_wav.duracao_segundos(
                pcm_frase,
                TAXA_ENTRADA,
                CANAIS,
            )

            self.status_recebido.emit(
                f"Transcrevendo {duracao:.1f}s de áudio..."
            )

            # --- ETAPA 1: áudio -> texto ---------------------------
            resultado = await self._transcrever(pcm_frase)

            if resultado is None:
                continue

            tipo, conteudo = resultado

            if tipo == "erro":
                self._reportar_falha_do_servidor(conteudo)

                continue

            texto = (conteudo.get("texto") or "").strip()

            if not texto:
                # O servidor transcreveu, mas não saiu nada (ruído que
                # passou pelo VAD). Não é erro do servidor nem vale um
                # turno de resposta.
                self.status_recebido.emit(
                    "Não entendi o que foi dito. Pode falar."
                )

                continue

            print(f"[VOZ LOCAL] Transcrição: {texto}")

            self.transcricao_conversa.append(
                {
                    "role": "user",
                    "content": texto,
                }
            )

            # --- ROTEAMENTO: era ferramenta ou conversa? -----------
            decisao = await self._rotear(texto)

            # BUG REAL, corrigido aqui: uma falha DO ROTEAMENTO não é
            # uma conversa. Antes, qualquer resultado com
            # usou_ferramenta=False caía na etapa 2, e o servidor de
            # voz — que não sabe que ferramentas existem — respondia
            # algo plausível ("claro, abrindo o navegador") sem nada
            # ter sido executado. Foi assim que um rate limit da Groq
            # virou "ele disse que abriu e não abriu".
            #
            # A falha vai para a interface e o turno acaba aqui. Não
            # dá para falá-la: a única saída de voz é a etapa 2, que
            # RESPONDE ao texto enviado em vez de lê-lo, então mandar
            # a mensagem de erro para lá faria o servidor conversar
            # sobre o erro. Com o retry de rate limit no roteamento,
            # este caminho ficou raro.
            if decisao is not None and decisao.falhou:
                self.erro_recebido.emit(
                    f"Não consegui decidir o que fazer: {decisao.resposta}"
                )

                self._aparar_transcricao()

                if self.ativo:
                    self.status_recebido.emit("Pode falar.")

                continue

            if decisao is not None and (
                decisao.usou_ferramenta
                or decisao.pedido_esclarecimento
            ):
                # Ferramenta: JÁ foi executada por processar_turno.
                # O servidor NÃO é chamado neste turno, exatamente
                # como especificado — o resultado aparece na
                # interface, sem voz.
                #
                # pedido_esclarecimento entra aqui pelo mesmo motivo
                # prático: o roteamento entendeu que era uma ação, só
                # não soube qual. Mandar o texto original para a etapa
                # de resposta faria o servidor conversar sobre um
                # pedido de ação que ele nem sabe que existe.
                self._registrar_resultado_local(decisao)

                self._aparar_transcricao()

                if self.ativo:
                    self.status_recebido.emit("Pode falar.")

                continue

            # --- ETAPA 2: texto -> áudio ---------------------------
            self.status_recebido.emit(
                "Pedindo a resposta falada ao servidor local..."
            )

            # Republica o JSON INTEIRO que veio da etapa 1, sem
            # remontar campo a campo: é literalmente o que o servidor
            # espera receber de volta, e assim tom/sexo chegam lá
            # exatamente como ele os produziu.
            resultado = await self._pedir_resposta(conteudo)

            if resultado is None:
                continue

            tipo, conteudo_resposta = resultado

            if tipo == "erro":
                self._reportar_falha_do_servidor(conteudo_resposta)

            else:
                # O texto entra no histórico ANTES de tocar, e de
                # propósito: _reproduzir_resposta bloqueia pelo tempo
                # inteiro da fala, e uma falha no dispositivo de saída
                # não deve apagar da conversa uma resposta que o
                # servidor de fato deu. A ordem também deixa o
                # histórico na sequência real do diálogo.
                self._registrar_fala_do_assistente(
                    conteudo_resposta.texto
                )

                await self._reproduzir_resposta(
                    conteudo_resposta.audio,
                    fila_microfone,
                    executor_audio,
                )

            self._aparar_transcricao()

            if self.ativo:
                self.status_recebido.emit("Pode falar.")

    # Erro vindo de jarvis/audio/erro (ou de um timeout/falha de
    # publicação nossa). Mesma porta de saída de qualquer outro erro
    # do projeto: registro de atividade + painel de console. A chamada
    # NÃO cai por causa disso — o microfone volta a escutar.
    #
    # O servidor já prefixa a linha com a metade que falhou
    # ("transcrição: ..." / "resposta: ..."), então repassar o texto
    # como veio é mais informativo do que reescrevê-lo aqui.
    def _reportar_falha_do_servidor(self, descricao):
        self.erro_recebido.emit(
            f"O servidor de voz local falhou: {descricao}"
        )

    # Passa o texto transcrito pelo roteamento hierárquico — o MESMO
    # motor que decide ferramenta-vs-conversa para os outros cérebros.
    # Ele já executa a ferramenta quando é o caso, então aqui não há
    # despacho nenhum a fazer: só ler o que ele decidiu.
    #
    # É síncrono e faz HTTP (Groq) mais o despacho da ferramenta, por
    # isso vai para uma thread — nunca direto no loop.
    async def _rotear(self, texto):
        try:
            return await asyncio.to_thread(
                roteamento_hierarquico.processar_turno,
                texto,
                # O histórico já está no formato que ele espera
                # ({"role", "content"}), então é a mesma lista.
                list(self.transcricao_conversa[:-1]),
                self._preparar_argumentos_da_ferramenta,
            )

        except Exception as erro:
            # Uma falha no roteamento não pode custar o turno: sem
            # decisão, o caminho seguro é tratar como conversa, que é
            # o comportamento de antes desta etapa existir.
            descricao = str(erro) or type(erro).__name__

            print(
                f"[VOZ LOCAL] Roteamento falhou ({descricao}); "
                "tratando como conversa."
            )

            self.erro_recebido.emit(
                f"O roteamento de ferramentas falhou ({descricao}). "
                "Tratando como conversa."
            )

            return None

    # Chamado por processar_turno logo antes do despacho, já dentro
    # da thread do roteamento — capturar_camera_bytes é bloqueante
    # (~2,8s nesta máquina: warm-up do dispositivo mais 10 frames),
    # então não pode rodar no loop.
    #
    # Não existe mutex aqui como no cliente do Gemini porque não há
    # concorrência a proteger: este worker é estritamente sequencial,
    # um turno por vez. A disputa pelo dispositivo com a janela de
    # pré-visualização continua tratada, porque capturar_camera_bytes
    # já usa o handle compartilhado quando ele está aberto.
    def _preparar_argumentos_da_ferramenta(self, nome_funcao, argumentos):
        origem = FERRAMENTAS_QUE_PRECISAM_DE_IMAGEM.get(nome_funcao)

        if origem is None:
            return argumentos

        self.status_recebido.emit(
            f"Capturando imagem d{'a tela' if origem == 'tela' else 'a câmera'}..."
        )

        # Cópia: nunca escreve no dicionário que o roteamento montou.
        argumentos = dict(argumentos or {})
        argumentos["imagem_bytes"] = _CAPTURAS[origem]()

        return argumentos

    # Resultado de um turno que terminou localmente (ferramenta
    # executada ou pedido de esclarecimento): não há áudio, então o
    # texto precisa aparecer em algum lugar.
    def _registrar_resultado_local(self, decisao):
        texto = (decisao.resposta or "").strip()

        if decisao.ferramenta_executada:
            print(
                f"[VOZ LOCAL] Ferramenta executada: "
                f"{decisao.ferramenta_executada}"
            )

        if texto:
            self.status_recebido.emit(texto)

            self.transcricao_conversa.append(
                {
                    "role": "assistant",
                    "content": texto,
                }
            )

    # A fala do ASSISTENTE entrando no histórico, do mesmo jeito que a
    # do usuário já entra logo depois da transcrição.
    #
    # ISTO É O QUE FALTAVA PARA A CONVERSA TER DOIS LADOS. O histórico
    # daqui é o único que existe neste modo — o servidor é
    # request/response e não guarda nada entre chamadas —, e ele
    # alimenta duas coisas a cada turno: o campo "historico" mandado à
    # ETAPA 2 (contexto.historico_para_envio) e o histórico passado ao
    # roteamento hierárquico. Enquanto só a fala do usuário entrava,
    # os dois enxergavam metade do diálogo: o assistente conseguia
    # lembrar do que tinha PERGUNTADO, nunca do que tinha RESPONDIDO.
    #
    # texto vazio ou None é ignorado em silêncio: significa que o
    # servidor não mandou a user property, e uma entrada em branco no
    # histórico só gastaria espaço do teto e confundiria o modelo.
    def _registrar_fala_do_assistente(self, texto):
        limpo = (texto or "").strip()

        if not limpo:
            return

        print(f"[VOZ LOCAL] Resposta falada: {limpo}")

        # Mesmo sinal que os workers do Gemini e da OpenAI emitem no
        # fim de cada turno falado — é por ele que a janela de chat e o
        # chat sobreposto à esfera recebem o texto. Aqui só foi
        # possível depois que o servidor passou a devolver o texto ao
        # lado do áudio (user property "texto"); antes disso este lado
        # não tinha o que emitir.
        #
        # Vai pelo sinalizador compartilhado, e não por um Signal deste
        # worker, porque o worker é recriado a cada chamada: um sinal
        # por instância obrigaria a reconectar a cada chamada nova.
        obter_sinalizador().resposta_texto_recebida.emit(limpo)

        self.transcricao_conversa.append(
            {
                "role": "assistant",
                "content": limpo,
            }
        )

    # Prepara o detector de fala para esta chamada. Carregar o modelo
    # custa algumas dezenas de ms e é feito UMA vez, aqui, e não a cada
    # frase — no meio de uma conversa isso apareceria como atraso.
    #
    # FALHA AQUI NÃO DERRUBA A CHAMADA. Sem o modelo (primeira execução
    # sem rede, onnxruntime ausente, arquivo corrompido) o worker cai
    # no modo por amplitude, que é o comportamento antigo. É pior — é
    # justamente o que trava a frase com ruído de fundo —, mas é
    # melhor do que não conseguir falar com o jarvis. O aviso vai para
    # a interface, não só para o console: ninguém fica olhando terminal
    # durante uma chamada.
    def _preparar_detector_de_fala(self):
        self.detector_fala = None

        try:
            self.detector_fala = vad_silero.DetectorDeFala()

            print(
                "[VOZ LOCAL] Detecção de fala pelo Silero VAD "
                f"(limiar {config.LIMIAR_PROB_FALA})."
            )

        except vad_silero.VadIndisponivel as erro:
            self.erro_recebido.emit(
                f"Detector de fala indisponível ({erro}). Usando detecção "
                "por volume — com ruído de fundo alto, a frase pode "
                "demorar a fechar."
            )

        except Exception as erro:
            self.erro_recebido.emit(
                f"Falha inesperada ao preparar o detector de fala "
                f"({erro}). Usando detecção por volume."
            )

    # Um bloco contém fala?
    #
    # Com o Silero, a resposta vem do CONTEÚDO do áudio. Sem ele
    # (modo de emergência), cai no critério antigo de amplitude, que é
    # o que este trabalho veio substituir — ver vad_silero.py.
    #
    # `nivel` é sempre o volume, e é passado de fora porque quem chama
    # já o calculou para animar a esfera: recalcular seria desperdício,
    # e a esfera continua sendo uma medida de volume mesmo.
    def _bloco_tem_fala(self, bloco, nivel):
        if self.detector_fala is None:
            return nivel >= config.LIMIAR_VOZ

        try:
            return self.detector_fala.tem_fala(bloco)

        except Exception as erro:
            # Uma falha na inferência no meio da frase não pode custar
            # a captura: desliga o detector pelo resto da chamada e
            # segue por amplitude, avisando uma única vez.
            print(
                f"[VOZ LOCAL] Erro na detecção de fala ({erro}); "
                "seguindo por volume até o fim da chamada."
            )
            self.detector_fala = None
            self.erro_recebido.emit(
                "O detector de fala falhou durante a chamada; voltei a "
                "usar detecção por volume."
            )

            return nivel >= config.LIMIAR_VOZ

    # Detecção de fim de fala. Devolve o PCM da frase, ou None quando
    # não houve fala aproveitável.
    #
    # Este é o pedaço que os outros dois workers não têm: lá o
    # servidor decide onde o turno acaba; aqui o servidor só recebe
    # arquivos prontos, então a decisão é toda deste lado.
    #
    # O QUE MUDOU, e o que NÃO mudou: quem classifica cada bloco em
    # fala/não-fala é o Silero (_bloco_tem_fala), por conteúdo. A
    # lógica de QUANTO tempo de não-fala fecha a frase é a mesma de
    # sempre — SILENCIO_SEGUNDOS acumulados, pré-fala na frente, cauda
    # aparada atrás, duração mínima medida só sobre os blocos com voz.
    async def _capturar_frase(self, fila_microfone):
        # O modelo é recorrente e guarda estado entre janelas: zerar no
        # começo de cada frase impede que a cauda da frase anterior
        # influencie a classificação do começo desta.
        if self.detector_fala is not None:
            self.detector_fala.zerar()

        # Guarda os últimos blocos ANTES de a fala ser detectada, para
        # não cortar a primeira sílaba (quando o modelo reconhece a
        # voz, o começo da palavra já passou).
        #
        # Quando o turno anterior acabou em INTERRUPÇÃO, esta fila já
        # começa preenchida: são os blocos que o vigia da reprodução
        # consumiu do microfone para decidir que o usuário estava
        # falando. Sem isso, as primeiras sílabas de quem interrompeu
        # seriam justamente as que se perdem — o vigia as tirou da fila
        # e ninguém mais as veria. Consumido de uma vez: valem só para
        # esta captura.
        pre_fala = collections.deque(
            self._blocos_apos_interrupcao,
            maxlen=config.BLOCOS_PRE_FALA,
        )

        self._blocos_apos_interrupcao = []

        blocos = []
        falando = False
        silencio_acumulado = 0.0
        duracao_total = 0.0

        # Tempo somado APENAS dos blocos acima do limiar. É este valor,
        # e não a duração do buffer, que decide se houve fala de
        # verdade: o buffer carrega os blocos de pré-fala na frente e o
        # silêncio que fechou a frase atrás, então medi-lo inteiro faria
        # um estalo de 0,1s parecer uma frase de 1,4s.
        duracao_com_voz = 0.0

        # Posição do último bloco com voz dentro de "blocos", para
        # aparar o silêncio final antes de publicar.
        indice_ultima_voz = -1

        while self.ativo:
            try:
                # wait_for em vez de get() puro: sem ele, encerrar a
                # chamada no silêncio deixaria esta tarefa presa na
                # fila até o próximo bloco chegar.
                bloco = await asyncio.wait_for(
                    fila_microfone.get(),
                    timeout=0.2,
                )

            except asyncio.TimeoutError:
                continue

            nivel = self.calcular_nivel_audio(bloco)

            # Anima a esfera enquanto escuta, do mesmo jeito que os
            # outros workers animam enquanto o assistente fala.
            self.nivel_audio.emit(nivel)

            duracao_bloco = audio_wav.duracao_segundos(
                bloco,
                TAXA_ENTRADA,
                CANAIS,
            )

            tem_fala = self._bloco_tem_fala(bloco, nivel)

            if not falando:
                pre_fala.append(bloco)

                if tem_fala:
                    falando = True

                    blocos = list(pre_fala)
                    pre_fala.clear()

                    duracao_total = audio_wav.duracao_segundos(
                        b"".join(blocos),
                        TAXA_ENTRADA,
                        CANAIS,
                    )

                    silencio_acumulado = 0.0

                    # O bloco que cruzou o limiar é o último da
                    # pré-fala (ele entra em pre_fala antes do teste).
                    duracao_com_voz = duracao_bloco
                    indice_ultima_voz = len(blocos) - 1

                    self.status_recebido.emit("Ouvindo...")

                continue

            blocos.append(bloco)
            duracao_total += duracao_bloco

            if tem_fala:
                silencio_acumulado = 0.0
                duracao_com_voz += duracao_bloco
                indice_ultima_voz = len(blocos) - 1

            else:
                silencio_acumulado += duracao_bloco

                if silencio_acumulado >= config.SILENCIO_SEGUNDOS:
                    break

            # Teto de segurança: mesmo com o Silero, alguém falando sem
            # parar (ou uma TV com voz humana ligada perto) gravaria
            # indefinidamente sem isto.
            if duracao_total >= config.DURACAO_MAXIMA_SEGUNDOS:
                print(
                    "[VOZ LOCAL] Frase atingiu o tempo máximo "
                    f"({config.DURACAO_MAXIMA_SEGUNDOS}s); enviando como está."
                )

                break

        self.nivel_audio.emit(0.0)

        if not falando or not self.ativo:
            return None

        # Fala curta demais é ruído (uma tosse, uma tecla) — descarta
        # em vez de gastar um round-trip com o servidor. Compara a
        # duração COM VOZ, nunca a do buffer (ver duracao_com_voz).
        if duracao_com_voz < config.DURACAO_MINIMA_SEGUNDOS:
            return None

        # Apara o silêncio que fechou a frase, mantendo só uma cauda
        # curta: sem isso, todo arquivo publicado levaria
        # SILENCIO_SEGUNDOS de nada no fim.
        if indice_ultima_voz >= 0:
            blocos = blocos[
                : indice_ultima_voz + 1 + config.BLOCOS_POS_FALA
            ]

        return b"".join(blocos)

    # ETAPA 1. Publica o áudio e espera o JSON da transcrição.
    # Devolve ("texto", dict), ("erro", texto) ou None.
    async def _transcrever(self, pcm_frase):
        try:
            wav = audio_wav.pcm_para_wav(
                pcm_frase,
                TAXA_ENTRADA,
                CANAIS,
            )

        except Exception as erro:
            return (
                "erro",
                f"não foi possível montar o WAV da fala ({erro})",
            )

        return await self._publicar_e_aguardar(
            publicar=lambda: self.cliente_mqtt.publicar_entrada(wav),
            tipo_esperado="texto",
            timeout=config.TIMEOUT_TRANSCRICAO_SEGUNDOS,
            topico_resposta=config.TOPICO_TEXTO_SAIDA,
        )

    # ETAPA 2. Republica o JSON da transcrição e espera o WAV final.
    # Devolve ("audio", RespostaFalada), ("erro", texto) ou None —
    # a RespostaFalada traz o WAV e o texto que ele fala.
    #
    # É AQUI que o modo local ganha memória. O alfred-server não tem
    # sessão: cada /responder é isolado, sem estado entre chamadas —
    # por isso perguntar o nome depois de tê-lo dito não funcionava.
    # Como a decisão é manter o servidor sem conhecimento nenhum sobre
    # o jarvis, quem monta o contexto é este lado, e manda pronto a
    # cada chamada.
    #
    # Os dois campos são OPCIONAIS no contrato: um servidor que ainda
    # não os conhece simplesmente os ignora (ele lê o payload por
    # chave, com .get), e o comportamento é o de antes. Por isso dá
    # para mandá-los já.
    async def _pedir_resposta(self, dados):
        # Cópia: o dicionário veio da etapa 1 e é republicado como
        # está; acrescentar campos nele mexeria no que já foi guardado.
        dados = dict(dados or {})

        # A fala atual já vai em "texto" — mandá-la também no
        # histórico a duplicaria. Por isso [:-1]: ela é a última coisa
        # que entrou na transcrição, logo antes do roteamento.
        historico = contexto.historico_para_envio(
            self.transcricao_conversa[:-1]
        )

        if historico:
            dados["historico"] = historico

        contexto_sistema = await asyncio.to_thread(
            contexto.montar_contexto_sistema,
            dados.get("texto", ""),
        )

        if contexto_sistema:
            dados["contexto_sistema"] = contexto_sistema

        return await self._publicar_e_aguardar(
            publicar=lambda: self.cliente_mqtt.publicar_texto(dados),
            tipo_esperado="audio",
            timeout=config.TIMEOUT_RESPOSTA_SEGUNDOS,
            topico_resposta=config.TOPICO_SAIDA,
        )

    # O ida-e-volta em si, idêntico para as duas etapas: cria o
    # future, publica, espera com timeout e sempre libera o future no
    # fim. Só mudam o que se publica, o que se espera e por quanto
    # tempo — por isso é um método só, e não dois quase iguais.
    async def _publicar_e_aguardar(
        self,
        publicar,
        tipo_esperado,
        timeout,
        topico_resposta,
    ):
        if self.cliente_mqtt is None:
            return None

        # O future precisa existir ANTES da publicação: o servidor
        # pode responder rápido o bastante para a mensagem chegar
        # enquanto a publicação ainda está retornando.
        #
        # tipo_esperado é o que impede a etapa 1 de aceitar um áudio
        # atrasado da etapa anterior como se fosse a transcrição dela:
        # os dois pares de tópicos são independentes e uma resposta
        # antiga pode chegar a qualquer momento.
        futuro = self.loop.create_future()
        self._futuro_resposta = futuro
        self._tipo_esperado = tipo_esperado

        try:
            sucesso, mensagem = await asyncio.to_thread(publicar)

            if not sucesso:
                return ("erro", mensagem)

            try:
                return await asyncio.wait_for(
                    futuro,
                    timeout=timeout,
                )

            except asyncio.TimeoutError:
                # A chamada NÃO trava nem cai: reporta e volta a
                # escutar. Uma resposta que chegue atrasada depois
                # disso é descartada em _resolver_futuro, porque
                # _futuro_resposta já terá voltado a None.
                return (
                    "erro",
                    f"nenhuma resposta em {timeout}s "
                    f"no tópico {topico_resposta}",
                )

        finally:
            self._futuro_resposta = None
            self._tipo_esperado = None

    # Mantém o histórico da conversa (que é também o histórico levado
    # ao roteamento) dentro de um teto. Mesma ideia, e mesmo motivo,
    # do MAXIMO_MENSAGENS_TRANSCRICAO dos outros dois workers: um
    # histórico sem limite cresce a cada turno e vai inteiro em toda
    # chamada ao roteamento.
    def _aparar_transcricao(self):
        excedente = len(self.transcricao_conversa) - MAXIMO_MENSAGENS_TRANSCRICAO

        if excedente > 0:
            del self.transcricao_conversa[:excedente]

    # ================================================================
    # REPRODUÇÃO
    # ================================================================

    # Vigia da reprodução: lê o microfone ENQUANTO o assistente fala e
    # avisa quando o usuário falou por cima.
    #
    # É a diferença estrutural em relação aos outros dois cérebros. No
    # Gemini Live quem detecta a interrupção é o SERVIDOR, que devolve
    # server_content.interrupted porque o microfone continua sendo
    # transmitido durante a fala. Aqui o alfred-server já entregou o
    # WAV inteiro e não sabe mais nada do turno — então a detecção é
    # toda deste lado, com o mesmo Silero que já fecha as frases.
    #
    # Reusa self.detector_fala SEM segunda sessão ONNX: este vigia e o
    # _capturar_frase nunca rodam ao mesmo tempo (o laço do turno é
    # estritamente sequencial) e os dois chamam zerar() ao começar, que
    # é o que o estado recorrente do modelo exige.
    #
    # Guarda os últimos blocos que consumiu: eles são o começo da fala
    # de quem interrompeu, e viram a pré-fala da próxima captura.
    async def _vigiar_interrupcao(self, fila_microfone, ao_interromper):
        if self.detector_fala is not None:
            self.detector_fala.zerar()

        recentes = collections.deque(maxlen=config.BLOCOS_PRE_FALA)
        consecutivos = 0
        inicio = time.monotonic()

        while self.ativo:
            try:
                bloco = await asyncio.wait_for(
                    fila_microfone.get(),
                    timeout=0.2,
                )

            except asyncio.TimeoutError:
                continue

            recentes.append(bloco)

            # Carência: no começo da reprodução a cauda da própria
            # frase do usuário ainda está no ar. Os blocos continuam
            # sendo guardados (podem virar pré-fala), só não contam
            # como interrupção.
            if time.monotonic() - inicio < CARENCIA_INTERRUPCAO_SEGUNDOS:
                continue

            nivel = self.calcular_nivel_audio(bloco)

            if self._bloco_tem_fala(bloco, nivel):
                consecutivos += 1

            else:
                # Exige fala CONSECUTIVA: um bloco solto no meio do
                # silêncio é estalo, não intenção de falar.
                consecutivos = 0

            if consecutivos >= BLOCOS_FALA_PARA_INTERROMPER:
                self._blocos_apos_interrupcao = list(recentes)
                ao_interromper()

                return

    async def _reproduzir_resposta(
        self,
        dados_wav,
        fila_microfone,
        executor_audio,
    ):
        try:
            pcm, taxa, canais = audio_wav.wav_para_pcm(dados_wav)

        except ValueError as erro:
            self.erro_recebido.emit(str(erro))

            return

        laco = asyncio.get_running_loop()

        # Bloqueia o microfone durante toda a reprodução e descarta o
        # que já estava na fila, para o assistente não escutar a
        # própria voz. Com a interrupção ligada, as guardas do
        # microfone deixam passar de propósito (ver o callback em
        # executar) e quem escuta é o vigia abaixo — a limpeza da fila
        # continua valendo, para o vigia não começar julgando áudio
        # velho de antes da resposta.
        self.alfred_falando = True
        self.limpar_fila_microfone(fila_microfone)

        interrompido = False

        # Quantos bytes do WAV já foram escritos no dispositivo. Uma
        # variável própria, e não o índice do for: se a abertura do
        # stream falhar, o for nunca roda e o `finally` explodiria com
        # NameError ao montar a mensagem de descarte.
        bytes_tocados = 0

        def marcar_interrupcao():
            nonlocal interrompido
            interrompido = True

        vigia = None

        if self.interrupcao_habilitada:
            vigia = asyncio.create_task(
                self._vigiar_interrupcao(
                    fila_microfone,
                    marcar_interrupcao,
                ),
                name="VIGIA_INTERRUPCAO",
            )

        self.status_recebido.emit("Reproduzindo a resposta...")

        # Um "bloco" em bytes, no formato que o servidor devolveu.
        tamanho_pedaco = BLOCO * audio_wav.LARGURA_16_BITS * canais

        try:
            # O dispositivo é aberto na taxa e no número de canais do
            # ARQUIVO, não em constantes fixas — ver o comentário
            # sobre TAXA_SAIDA no topo do módulo.
            with sd.RawOutputStream(
                samplerate=taxa,
                blocksize=BLOCO,
                dtype="int16",
                channels=canais,
                latency=LATENCIA_SAIDA,
            ) as saida:
                for inicio in range(0, len(pcm), tamanho_pedaco):
                    if not self.ativo:
                        break

                    # O usuário falou por cima: para de escrever AGORA
                    # e joga fora o resto do WAV, em vez de deixar a
                    # frase terminar sozinha. Mesmo efeito do
                    # limpar_fila_saida que o worker do Gemini faz ao
                    # receber server_content.interrupted.
                    if interrompido:
                        break

                    pedaco = pcm[inicio:inicio + tamanho_pedaco]

                    self.nivel_audio.emit(
                        self.calcular_nivel_audio(pedaco)
                    )

                    # wait_for por fora: um dispositivo de saída que
                    # trava (jogo em tela cheia tomando a placa de
                    # som) não levanta exceção, só nunca retorna.
                    # run_in_executor com o executor EXCLUSIVO, nunca
                    # asyncio.to_thread — ver o comentário em
                    # executar().
                    await asyncio.wait_for(
                        laco.run_in_executor(
                            executor_audio,
                            saida.write,
                            pedaco,
                        ),
                        timeout=TIMEOUT_ESCRITA_AUDIO_SEGUNDOS,
                    )

                    bytes_tocados = inicio + len(pedaco)

        except Exception as erro:
            descricao = str(erro) or type(erro).__name__

            self.erro_recebido.emit(
                f"Falha ao reproduzir a resposta do servidor local: {descricao}"
            )

        finally:
            self.nivel_audio.emit(0.0)

            if vigia is not None and not vigia.done():
                vigia.cancel()

            if interrompido:
                # NADA de dormir nem de limpar a fila aqui. O usuário
                # está falando NESTE instante: o atraso viraria latência
                # pura, e a limpeza comeria justamente os blocos da
                # frase que ele acabou de começar. Os blocos que o vigia
                # já tinha consumido vão como pré-fala da próxima
                # captura (self._blocos_apos_interrupcao).
                self.interrupcoes_na_chamada += 1

                restante = max(len(pcm) - bytes_tocados, 0)

                print(
                    "[INTERRUPÇÃO] O usuário falou por cima — fala "
                    f"cortada (nº {self.interrupcoes_na_chamada} nesta "
                    f"chamada, {restante} bytes de áudio descartados)."
                )

                self.alfred_falando = False

            else:
                # Espera o retorno de áudio da sala morrer antes de
                # voltar a escutar, e só então limpa o que entrou na
                # fila.
                await asyncio.sleep(ATRASO_REABRIR_MICROFONE)

                self.limpar_fila_microfone(fila_microfone)
                self.alfred_falando = False

    # ================================================================
    # CALLBACKS DO MQTT (chegam da thread de rede do paho)
    # ================================================================

    # ETAPA 1: JSON UTF-8 {"texto", "tom", "sexo"}. Um JSON quebrado
    # vira erro do turno, nunca exceção nesta thread.
    def _ao_receber_texto_mqtt(self, payload):
        try:
            dados = json.loads(
                payload.decode("utf-8", errors="replace")
            )

        except (ValueError, AttributeError) as erro:
            self._entregar_resposta(
                (
                    "erro",
                    f"a transcrição veio num JSON ilegível ({erro})",
                )
            )

            return

        if not isinstance(dados, dict):
            self._entregar_resposta(
                (
                    "erro",
                    "a transcrição veio num formato inesperado "
                    f"({type(dados).__name__} em vez de objeto JSON)",
                )
            )

            return

        self._entregar_resposta(("texto", dados))

    def _ao_receber_saida_mqtt(self, audio_bytes, texto_resposta=None):
        # O texto vem junto do áudio (user property "texto") e viaja
        # até o laço do turno dentro do MESMO resultado, em vez de
        # ficar guardado num atributo: assim uma resposta descartada
        # por chegar fora de hora (ver _resolver_futuro) leva o texto
        # dela embora junto, e não contamina o histórico do turno
        # seguinte com uma fala que o usuário nunca ouviu.
        self._entregar_resposta(
            ("audio", RespostaFalada(audio_bytes, texto_resposta))
        )

    def _ao_receber_erro_mqtt(self, texto):
        self._entregar_resposta(
            (
                "erro",
                texto or "o servidor não disse qual etapa falhou",
            )
        )

    # Atravessa da thread do paho para o loop desta thread. Mesma
    # técnica (call_soon_threadsafe) que os outros pacotes usam para
    # entregar algo de uma thread de fundo ao loop do worker.
    def _entregar_resposta(self, resultado):
        laco = self.loop

        if laco is None:
            return

        try:
            laco.call_soon_threadsafe(
                self._resolver_futuro,
                resultado,
            )

        except RuntimeError:
            # O loop já fechou (chamada encerrando) — a mensagem
            # simplesmente não interessa mais.
            pass

    def _resolver_futuro(self, resultado):
        futuro = self._futuro_resposta
        tipo, conteudo = resultado

        # Um erro vale para qualquer etapa que esteja esperando: o
        # servidor publica os dois no mesmo tópico, prefixados pela
        # metade que falhou.
        fora_de_hora = futuro is None or futuro.done()

        # Resposta da etapa ERRADA: a etapa 1 nunca aceita um áudio, a
        # etapa 2 nunca aceita um JSON. Os dois pares de tópicos são
        # independentes, então uma resposta atrasada do turno anterior
        # pode chegar bem no meio da espera do turno atual — sem esta
        # checagem, ela seria entregue como se fosse a resposta certa.
        etapa_errada = (
            not fora_de_hora
            and tipo != "erro"
            and tipo != self._tipo_esperado
        )

        if fora_de_hora or etapa_errada:
            # Mensagem retida no broker, resposta que chegou depois do
            # timeout, ou resposta da outra metade do pipeline.
            # Conteúdo nesse estado é descartado (tocá-lo seria a
            # resposta de uma pergunta que o usuário já considera
            # perdida), mas um erro continua valendo a pena mostrar.
            if tipo == "erro":
                self.erro_recebido.emit(
                    f"O servidor de voz local reportou: {conteudo}"
                )

            else:
                medivel = (
                    conteudo.audio
                    if isinstance(conteudo, RespostaFalada)
                    else conteudo
                )
                tamanho = (
                    len(medivel)
                    if isinstance(medivel, (bytes, bytearray))
                    else len(str(medivel))
                )

                print(
                    f"[VOZ LOCAL] Resposta do tipo '{tipo}' recebida "
                    f"fora de hora ({tamanho} bytes) — descartada "
                    f"(esperando: {self._tipo_esperado or 'nada'})."
                )

            return

        futuro.set_result(resultado)

    # ================================================================
    # API PÚBLICA EXIGIDA PELA JANELA
    # ================================================================
    # Os quatro métodos abaixo existem porque jarvis/ui/janela_principal.py
    # e as janelas de chat/envio de arquivo os chamam sem saber qual
    # cérebro está ativo. Neste modo eles não têm para onde ir: o
    # servidor troca áudio e nada mais. Recusam explicando, em vez de
    # não fazer nada em silêncio.

    def solicitar_analise_tela(self):
        self.erro_recebido.emit(MENSAGEM_SEM_SUPORTE)

    def solicitar_analise_camera(self):
        self.erro_recebido.emit(MENSAGEM_SEM_SUPORTE)

    def enviar_texto_da_ui(self, texto):
        self.erro_recebido.emit(MENSAGEM_SEM_SUPORTE)

        return False

    def enviar_imagem_da_ui(
        self,
        imagem_bytes,
        mime_type,
        texto_contexto=None,
    ):
        self.erro_recebido.emit(MENSAGEM_SEM_SUPORTE)

        return False

    # ================================================================
    # AUXILIARES
    # ================================================================

    @staticmethod
    def limpar_fila_microfone(fila_microfone):
        while True:
            try:
                fila_microfone.get_nowait()

            except asyncio.QueueEmpty:
                break

    # Mesmo cálculo dos outros dois workers (pico normalizado, com a
    # curva 0.55 que deixa a animação mais sensível). Aqui ele tem um
    # segundo uso que lá não tem: é também o sinal comparado com
    # config.LIMIAR_VOZ pelo VAD.
    @staticmethod
    def calcular_nivel_audio(audio_bytes):
        if not audio_bytes:
            return 0.0

        try:
            amostras = array("h", audio_bytes)

            if not amostras:
                return 0.0

            pico = max(
                abs(amostra)
                for amostra in amostras
            )

            nivel = (pico / 32768.0) ** 0.55

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
