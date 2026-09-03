"""
Worker equivalente a jarvis/gemini/cliente_live.py, usando a Realtime
API da OpenAI como cérebro do ALFRED em vez do Gemini Live.

Veio do JARVIS COMPLETO (openai_provider/live_client.py) e foi
adaptado à arquitetura deste projeto. O que mudou em relação ao
original do curso:

- As ferramentas NÃO são declaradas à mão aqui. Elas vêm de
  PACOTES_REGISTRADOS (jarvis/nucleo/registro_pacotes.py), convertidas
  do formato do Gemini pelo esquema.py deste pacote. Um pacote novo
  funciona nos dois cérebros de voz sem tocar em nenhum cliente.
- A instrução de sistema é a MESMA do Gemini
  (jarvis/nucleo/prompts/), incluindo o bloco de autenticação por
  palavra-chave quando EXIGIR_AUTENTICACAO está ligado. O prompt do
  curso não tinha esse bloco; ter dois prompts diferentes criaria um
  segundo jeito de contornar a trava, que é justamente o que a regra
  do projeto proíbe.
- A memória vem do vault do Obsidian (memoria_obsidian), não do
  gerenciador antigo.

Mantém a mesma API pública do GeminiLiveWorker (sinais, construtor e
métodos) para jarvis/ui/janela_principal.py trocar de provedor só
mudando PROVEDOR_IA no .env, sem tocar na interface.

Diferenças de comportamento que a interface precisa conhecer:

- A Realtime API não tem equivalente a session_resumption/GoAway do
  Gemini. Os sinais solicitou_reconexao e session_handle_atualizado
  existem só para manter a mesma interface; nunca são emitidos.
- Áudio em PCM16 24 kHz na entrada E na saída (no Gemini a entrada é
  16 kHz).
"""

import asyncio
import base64
import time
from array import array

import sounddevice as sd

from PySide6.QtCore import QThread, Signal

from openai import AsyncOpenAI

from google.genai import types

from jarvis.nucleo.config import (
    EXIGIR_AUTENTICACAO,
    OPENAI_API_KEY,
    OPENAI_REALTIME_MODEL,
    OPENAI_VOICE,
)

from jarvis.nucleo import prompts
from jarvis.nucleo.sinalizador import obter_sinalizador

from jarvis.nucleo.registro_pacotes import (
    PACOTES_REGISTRADOS,
    TOOLS_QUE_CAPTURAM_SOZINHAS,
    TOOLS_SILENCIOSAS,
)

from jarvis.servicos.visao.captura_tela import capturar_tela_bytes
from jarvis.servicos.visao.captura_camera import capturar_camera_bytes

from jarvis.pacotes import ativacao_voz
from jarvis.pacotes import admin_terminal
from jarvis.pacotes import discord_jarvis
from jarvis.pacotes import memoria_obsidian
from jarvis.pacotes import rede_jarvis

from jarvis.openai_realtime import esquema


# A Realtime API trabalha em PCM16 24 kHz tanto na entrada quanto na
# saída, por isso as duas taxas são iguais aqui (no Gemini a entrada
# é 16 kHz e a saída 24 kHz).
TAXA_ENTRADA = 24000
TAXA_SAIDA = 24000
CANAIS = 1
BLOCO = 1024

# Tempo de segurança antes de reabrir o microfone depois que o
# assistente termina de falar.
ATRASO_REABRIR_MICROFONE = 0.8

LIMITE_FILA_MICROFONE = 50

# Debounce da mesma função visual, para o modelo não recapturar a
# mesma imagem várias vezes para um único pedido.
COOLDOWN_FUNCAO_VISUAL = 8.0

# Tempo máximo de uma função de pacote antes de devolver uma mensagem
# amigável em vez de travar a sessão.
TIMEOUT_FUNCAO_PADRAO = 20

# admin_terminal tem timeout interno próprio, bem mais longo — usar o
# padrão aqui cortaria um comando demorado antes de ele terminar
# sozinho. Mesma lógica de TIMEOUTS_TAREFA_FUNCAO_POR_NOME em
# jarvis/gemini/cliente_live.py.
TIMEOUTS_FUNCAO_POR_NOME = {
    "executar_comando_admin": (
        admin_terminal.config.TIMEOUT_COMANDO_LONGO_SEGUNDOS + 30
    ),
    "confirmar_comando_admin": (
        admin_terminal.config.TIMEOUT_COMANDO_LONGO_SEGUNDOS + 30
    ),
}

# Espera antes de encerrar de fato depois de encerrar_chamada, para a
# despedida terminar de tocar.
ATRASO_ENCERRAMENTO_SEGUNDOS = 2.8

# Quantas mensagens do transcript da conversa ficam guardadas — mesmo
# valor e mesmo motivo da constante de mesmo nome em
# jarvis/gemini/cliente_live.py.
MAXIMO_MENSAGENS_TRANSCRICAO = 12


# Tools nativas deste cliente — as mesmas três do JARVIS COMPLETO que
# não pertencem a pacote nenhum. Declaradas no formato do Gemini de
# propósito: é o formato que esquema.py converte, então há um único
# conversor para tudo, em vez de dois jeitos de declarar ferramenta.
FUNCTION_DECLARATIONS_NATIVAS = [
    types.FunctionDeclaration(
        name="analisar_tela",
        description=(
            "Captura a tela atual do computador e envia para análise "
            "visual. Use somente quando o usuário pedir explicitamente "
            "para ver, analisar, observar ou explicar a tela."
        ),
    ),

    types.FunctionDeclaration(
        name="analisar_camera",
        description=(
            "Captura uma imagem da webcam e envia para análise visual. "
            "Use somente quando o usuário pedir explicitamente para "
            "ver, analisar, observar ou explicar a câmera, a webcam ou "
            "algo mostrado nela."
        ),
    ),

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


class OpenAIRealtimeWorker(QThread):

    # Os mesmos sinais do GeminiLiveWorker — ver o docstring do módulo.
    status_recebido = Signal(str)
    erro_recebido = Signal(str)
    chamada_encerrada = Signal()
    nivel_audio = Signal(float)
    solicitou_encerramento = Signal()

    # Existem só por compatibilidade de interface: a Realtime API não
    # tem retomada de sessão por handle nem aviso de renovação de
    # WebSocket, então este worker NUNCA emite os dois.
    solicitou_reconexao = Signal()
    session_handle_atualizado = Signal(str)

    # Mesma assinatura do GeminiLiveWorker. session_handle e
    # transcricao_inicial são aceitos para a janela poder criar
    # qualquer um dos dois workers do mesmo jeito; o handle é ignorado
    # (ver acima), a transcrição não.
    def __init__(self, session_handle=None, transcricao_inicial=None):
        super().__init__()

        self.ativo = True
        self.loop = None
        self.conexao = None
        self.session_handle = session_handle

        # Trava de envio: vários pontos podem escrever na conexão
        # (microfone, resposta de ferramenta, imagem avulsa) e a
        # Realtime API não gosta de escritas concorrentes.
        self.lock_envio = None

        # True enquanto uma função está sendo executada — o microfone
        # fica ignorado nesse período, igual a alfred_falando.
        self.processando_ferramenta = False

        # (origem, bytes) da imagem capturada por analisar_tela/
        # analisar_camera, esperando para ser enviada DEPOIS da
        # resposta da ferramenta (a ordem importa no protocolo).
        self.imagem_visual_pendente = None

        self.alfred_falando = False
        self.tarefa_liberar_microfone = None
        self.tarefa_encerramento = None

        # Mutex e debounce das funções visuais, mesma ideia do
        # GeminiLiveWorker.
        self.executando_funcao_visual = False
        self.ultima_funcao_visual = None
        self.tempo_ultima_funcao_visual = 0.0

        # Descarta o áudio da resposta do turno atual — ligado pelas
        # tools de TOOLS_SILENCIOSAS (rolar página, escrever no campo
        # ativo, clicar num elemento).
        self.silenciar_audio_ate_fim_turno = False

        # Histórico da conversa, no mesmo formato usado pelo worker do
        # Gemini, para o resumo salvo na memória no fim da chamada.
        self.transcricao_conversa = list(transcricao_inicial or [])
        self._buffer_transcricao_usuario = ""
        self._buffer_transcricao_assistente = ""

        # Sobe (ou reconecta os callbacks de) os pacotes que precisam
        # ficar de pé fora de uma chamada — idempotentes, mesma
        # chamada que GeminiLiveWorker.__init__ faz, pelos mesmos
        # motivos. Roda aqui, na thread da UI, antes de .start().
        rede_jarvis.iniciar_rede_jarvis(
            callback_falar=self._falar_espontaneamente,
            callback_frame_remoto=self._receber_frame_remoto,
        )

        admin_terminal.iniciar_admin_terminal(
            callback_falar=self._falar_espontaneamente,
        )

        discord_jarvis.iniciar_discord_jarvis()

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

    # ================================================================
    # FALA ESPONTÂNEA (usada por rede_jarvis e admin_terminal)
    # ================================================================

    # Mesmo contrato do método de mesmo nome no GeminiLiveWorker: é
    # chamado de uma thread de fundo do pacote, então só agenda a
    # corrotina no loop desta thread.
    def _falar_espontaneamente(self, texto):
        if not self.loop or not self.conexao:
            return

        asyncio.run_coroutine_threadsafe(
            self._enviar_anuncio_espontaneo(texto),
            self.loop,
        )

    async def _enviar_anuncio_espontaneo(self, texto):
        try:
            async with self.lock_envio:
                await self.conexao.conversation.item.create(
                    item={
                        "type": "message",
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": prompts.ANUNCIO_ESPONTANEO.format(
                                    texto=texto
                                ),
                            },
                        ],
                    }
                )

                await self.conexao.response.create()

        except Exception as erro:
            print(f"[OPENAI] Falha ao anunciar espontaneamente: {erro}")

    # Frames de visualização remota (rede_jarvis). A Realtime API
    # aceita imagem como item de conversa, igual à imagem avulsa das
    # análises visuais.
    def _receber_frame_remoto(self, imagem_bytes):
        if not self.loop or not self.conexao:
            return

        asyncio.run_coroutine_threadsafe(
            self._injetar_frame_remoto(imagem_bytes),
            self.loop,
        )

    async def _injetar_frame_remoto(self, imagem_bytes):
        try:
            async with self.lock_envio:
                await self.conexao.conversation.item.create(
                    item={
                        "type": "message",
                        "role": "user",
                        "content": [
                            {
                                "type": "input_image",
                                "image_url": self._data_url(imagem_bytes),
                                "detail": "auto",
                            },
                        ],
                    }
                )

        except Exception as erro:
            print(f"[OPENAI] Falha ao injetar frame remoto: {erro}")

    # ================================================================
    # PONTES COM AS JANELAS DE CHAT / ENVIO DE ARQUIVO
    # ================================================================

    # Mesma assinatura e mesma semântica dos métodos do
    # GeminiLiveWorker: devolvem False (sem levantar exceção) quando
    # não há sessão viva, para a janela avisar o usuário em vez de
    # perder a mensagem em silêncio.
    def enviar_texto_da_ui(self, texto):
        if not self.loop or not self.conexao:
            return False

        asyncio.run_coroutine_threadsafe(
            self._enviar_texto(texto),
            self.loop,
        )

        return True

    async def _enviar_texto(self, texto):
        try:
            async with self.lock_envio:
                await self.conexao.conversation.item.create(
                    item={
                        "type": "message",
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": texto},
                        ],
                    }
                )

                await self.conexao.response.create()

        except Exception as erro:
            print(f"[OPENAI] Falha ao enviar texto da interface: {erro}")

    def enviar_imagem_da_ui(
        self,
        imagem_bytes,
        mime_type="image/jpeg",
        texto_contexto=None,
    ):
        if not self.loop or not self.conexao:
            return False

        asyncio.run_coroutine_threadsafe(
            self._enviar_imagem(imagem_bytes, mime_type, texto_contexto),
            self.loop,
        )

        return True

    async def _enviar_imagem(self, imagem_bytes, mime_type, texto_contexto):
        try:
            conteudo = []

            if texto_contexto:
                conteudo.append(
                    {"type": "input_text", "text": texto_contexto}
                )

            conteudo.append(
                {
                    "type": "input_image",
                    "image_url": self._data_url(imagem_bytes, mime_type),
                    "detail": "auto",
                }
            )

            async with self.lock_envio:
                await self.conexao.conversation.item.create(
                    item={
                        "type": "message",
                        "role": "user",
                        "content": conteudo,
                    }
                )

                await self.conexao.response.create()

        except Exception as erro:
            print(f"[OPENAI] Falha ao enviar imagem da interface: {erro}")

    # ================================================================
    # SESSÃO
    # ================================================================

    @staticmethod
    def _data_url(imagem_bytes, mime_type="image/jpeg"):
        return (
            f"data:{mime_type};base64,"
            + base64.b64encode(imagem_bytes).decode("ascii")
        )

    # A MESMA instrução usada pelo Gemini, inclusive o bloco de
    # autenticação por palavra-chave quando EXIGIR_AUTENTICACAO está
    # ligado. Ver o docstring do módulo: um prompt próprio aqui seria
    # um segundo caminho para contornar a trava.
    def _montar_instrucao_sistema(self, memorias_atuais):
        bloco_autenticacao = (
            prompts.bloco_autenticacao()
            if EXIGIR_AUTENTICACAO
            else ""
        )

        return (
            bloco_autenticacao
            + prompts.instrucao_sistema_corpo()
            + prompts.contexto_data_hora()
            + "\n\n"
            + memorias_atuais
        )

    async def executar(self):
        # O detector de palavra de ativação e esta chamada nunca podem
        # ter o microfone aberto ao mesmo tempo. Bloqueia até o
        # microfone dele estar de fato livre. Idempotente.
        ativacao_voz.pausar()

        if not OPENAI_API_KEY:
            raise ValueError(
                "OPENAI_API_KEY não encontrada no arquivo .env"
            )

        self.loop = asyncio.get_running_loop()
        self.lock_envio = asyncio.Lock()

        cliente = AsyncOpenAI(api_key=OPENAI_API_KEY)

        fila_microfone = asyncio.Queue(maxsize=LIMITE_FILA_MICROFONE)
        fila_saida = asyncio.Queue()

        # Contexto inicial leve da memória (só as notas mais recentes);
        # o resto o modelo busca sob demanda pela tool do pacote.
        memorias_atuais = await asyncio.to_thread(
            memoria_obsidian.contexto_inicial
        )

        ferramentas = esquema.montar_ferramentas(
            FUNCTION_DECLARATIONS_NATIVAS,
            PACOTES_REGISTRADOS,
        )

        self.status_recebido.emit("Conectando à OpenAI Realtime...")

        try:
            # Usa o recurso "realtime" (GA), não "beta.realtime":
            # contas migradas para a API definitiva recusam o shape
            # antigo com o erro "beta_api_shape_disabled".
            async with cliente.realtime.connect(
                model=OPENAI_REALTIME_MODEL,
            ) as conexao:
                self.conexao = conexao

                # Formato de sessão da Realtime API (GA): áudio de
                # entrada e saída ficam aninhados em "audio", e o
                # modelo só aceita uma modalidade de resposta por vez
                # (aqui, áudio).
                await conexao.session.update(
                    session={
                        "type": "realtime",
                        "output_modalities": ["audio"],
                        "instructions": self._montar_instrucao_sistema(
                            memorias_atuais
                        ),
                        "audio": {
                            "input": {
                                "format": {
                                    "type": "audio/pcm",
                                    "rate": TAXA_ENTRADA,
                                },
                                "turn_detection": {"type": "server_vad"},
                            },
                            "output": {
                                "format": {
                                    "type": "audio/pcm",
                                    "rate": TAXA_SAIDA,
                                },
                                "voice": OPENAI_VOICE,
                            },
                        },
                        "tools": ferramentas,
                    }
                )

                self.status_recebido.emit("ALFRED conectado. Pode falar.")

                tarefas = [
                    asyncio.create_task(
                        self.enviar_microfone(conexao, fila_microfone),
                        name="MICROFONE",
                    ),
                    asyncio.create_task(
                        self.receber_eventos(
                            conexao,
                            fila_saida,
                            fila_microfone,
                        ),
                        name="RECEPÇÃO",
                    ),
                    asyncio.create_task(
                        self.reproduzir_audio(fila_saida, fila_microfone),
                        name="REPRODUÇÃO",
                    ),
                ]

                try:
                    while self.ativo:
                        concluidas, _ = await asyncio.wait(
                            tarefas,
                            timeout=0.5,
                            return_when=asyncio.FIRST_COMPLETED,
                        )

                        for tarefa in concluidas:
                            if tarefa.cancelled():
                                continue

                            erro = tarefa.exception()

                            if erro is not None:
                                raise RuntimeError(
                                    f"A tarefa '{tarefa.get_name()}' "
                                    f"parou: {erro}"
                                ) from erro

                            if self.ativo:
                                raise RuntimeError(
                                    f"A tarefa '{tarefa.get_name()}' "
                                    "terminou inesperadamente."
                                )

                finally:
                    for tarefa in tarefas:
                        tarefa.cancel()

                    if self.tarefa_liberar_microfone:
                        self.tarefa_liberar_microfone.cancel()

                    if self.tarefa_encerramento:
                        self.tarefa_encerramento.cancel()

                    await asyncio.gather(*tarefas, return_exceptions=True)

        finally:
            self.conexao = None

            # Resumo pesquisável da conversa, igual ao worker do
            # Gemini. Nunca levanta exceção, mas o try existe mesmo
            # assim: uma falha aqui não pode impedir o resto do
            # encerramento.
            try:
                await asyncio.to_thread(
                    memoria_obsidian.consolidacao.salvar_resumo_conversa,
                    self.transcricao_conversa,
                )

            except Exception as erro:
                print(
                    f"[MEMORIA] Falha ao salvar o resumo da conversa: {erro}"
                )

            # A chamada acabou: volta a escutar a palavra de ativação.
            ativacao_voz.retomar()

    # ================================================================
    # MICROFONE
    # ================================================================

    async def enviar_microfone(self, conexao, fila_microfone):
        loop = asyncio.get_running_loop()

        def callback(indata, frames, time_info, status):
            if not self.ativo:
                return

            if self.alfred_falando or self.processando_ferramenta:
                return

            if status:
                print("Aviso microfone:", status)

            audio_bytes = bytes(indata)

            def adicionar_audio():
                if (
                    self.alfred_falando
                    or self.processando_ferramenta
                    or not self.ativo
                ):
                    return

                try:
                    fila_microfone.put_nowait(audio_bytes)

                except asyncio.QueueFull:
                    pass

            loop.call_soon_threadsafe(adicionar_audio)

        # Sem este try, uma falha ao abrir o microfone mataria a tarefa
        # em silêncio e a chamada ficaria "conectada" e surda — o
        # mesmo bug real já corrigido no worker do Gemini.
        try:
            with sd.RawInputStream(
                samplerate=TAXA_ENTRADA,
                blocksize=BLOCO,
                dtype="int16",
                channels=CANAIS,
                callback=callback,
            ):
                while self.ativo:
                    audio_bytes = await fila_microfone.get()

                    if self.alfred_falando or self.processando_ferramenta:
                        continue

                    async with self.lock_envio:
                        await conexao.input_audio_buffer.append(
                            audio=base64.b64encode(audio_bytes).decode(
                                "ascii"
                            )
                        )

        except Exception as erro:
            print(
                f"[MICROFONE] Não foi possível abrir ou usar o "
                f"microfone: {erro}"
            )

            self.erro_recebido.emit(
                f"Não foi possível abrir o microfone: {erro}"
            )

            self.ativo = False

    # ================================================================
    # RECEPÇÃO DE EVENTOS
    # ================================================================

    async def receber_eventos(self, conexao, fila_saida, fila_microfone):
        async for evento in conexao:
            if not self.ativo:
                break

            tipo = evento.type

            if tipo == "response.output_audio.delta":
                # silenciar_audio_ate_fim_turno descarta o turno
                # inteiro (rolagem, escrita, clique) — e descarta de
                # forma completa: sem marcar alfred_falando e sem
                # enfileirar nada, senão o microfone ficaria bloqueado
                # esperando uma reprodução que nunca acontece.
                if not self.silenciar_audio_ate_fim_turno:
                    self.alfred_falando = True

                    if self.tarefa_liberar_microfone:
                        self.tarefa_liberar_microfone.cancel()

                    self.limpar_fila_microfone(fila_microfone)

                    await fila_saida.put(base64.b64decode(evento.delta))

            elif tipo == "response.function_call_arguments.done":
                argumentos = esquema.interpretar_argumentos(
                    getattr(evento, "arguments", None)
                )

                # Uma função lenta não pode bloquear este laço (áudio
                # incluído) — mesma correção já feita no worker do
                # Gemini. Cada chamada vira uma tarefa própria.
                asyncio.create_task(
                    self.processar_chamada_de_funcao(
                        conexao,
                        evento.call_id,
                        evento.name,
                        argumentos,
                        fila_microfone,
                    )
                )

            elif tipo == "response.done":
                self.silenciar_audio_ate_fim_turno = False

                self._fechar_turno_da_transcricao()

            elif tipo == "error":
                mensagem = getattr(
                    getattr(evento, "error", None),
                    "message",
                    "Erro desconhecido da Realtime API.",
                )

                self.erro_recebido.emit(mensagem)

            else:
                # Transcrições: alimentam self.transcricao_conversa
                # (resumo salvo na memória no fim da chamada) e a
                # janela de chat. getattr defensivo de propósito — se
                # o nome do evento mudar, o pior que acontece é a
                # transcrição ficar vazia, nunca uma exceção no meio
                # da sessão.
                self._acumular_transcricao(tipo, evento)

    def _acumular_transcricao(self, tipo, evento):
        texto = getattr(evento, "transcript", None) or getattr(
            evento,
            "delta",
            None,
        )

        if not isinstance(texto, str) or not texto:
            return

        if tipo.startswith("conversation.item.input_audio_transcription"):
            if tipo.endswith(".completed"):
                self._buffer_transcricao_usuario += texto

        elif tipo.startswith("response.output_audio_transcript"):
            if tipo.endswith(".done"):
                self._buffer_transcricao_assistente += texto

                # A resposta em texto do turno também alimenta a
                # janela de chat, quando ela estiver aberta.
                obter_sinalizador().resposta_texto_recebida.emit(texto)

    def _fechar_turno_da_transcricao(self):
        # Usuário primeiro (perguntou), ALFRED depois (respondeu) —
        # mesma ordem lógica usada pelo worker do Gemini.
        if self._buffer_transcricao_usuario:
            self.transcricao_conversa.append(
                {
                    "role": "user",
                    "content": self._buffer_transcricao_usuario,
                }
            )

            self._buffer_transcricao_usuario = ""

        if self._buffer_transcricao_assistente:
            self.transcricao_conversa.append(
                {
                    "role": "assistant",
                    "content": self._buffer_transcricao_assistente,
                }
            )

            self._buffer_transcricao_assistente = ""

        # Mesmo teto usado pelo worker do Gemini, pelo mesmo
        # motivo: este transcript vira o resumo salvo na memória no
        # fim da chamada e não pode crescer sem limite.
        excesso = (
            len(self.transcricao_conversa)
            - MAXIMO_MENSAGENS_TRANSCRICAO
        )

        if excesso > 0:
            self.transcricao_conversa = self.transcricao_conversa[excesso:]

    # ================================================================
    # CHAMADAS DE FUNÇÃO
    # ================================================================

    async def processar_chamada_de_funcao(
        self,
        conexao,
        call_id,
        nome,
        args,
        fila_microfone,
    ):
        self.processando_ferramenta = True
        self.alfred_falando = True
        self.limpar_fila_microfone(fila_microfone)

        try:
            encerrar_depois = False

            if nome in TOOLS_SILENCIOSAS:
                self.silenciar_audio_ate_fim_turno = True

            if nome in ("analisar_tela", "analisar_camera"):
                resultado = await self.processar_funcao_visual(nome)

            elif nome == "encerrar_chamada":
                resultado = (
                    "Diga de forma curta que a chamada será encerrada."
                )
                encerrar_depois = True

            else:
                resultado = await self._despachar_para_pacotes(nome, args)

            async with self.lock_envio:
                await conexao.conversation.item.create(
                    item={
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": str(resultado),
                    }
                )

                # Só depois de responder à ferramenta é que a imagem
                # pendente é enviada — a mesma ordem usada pelo worker
                # do Gemini, e a que o protocolo espera.
                if self.imagem_visual_pendente is not None:
                    await self._anexar_imagem_visual_pendente(conexao)

                await conexao.response.create()

            if encerrar_depois:
                if self.tarefa_encerramento:
                    self.tarefa_encerramento.cancel()

                self.tarefa_encerramento = asyncio.create_task(
                    self.encerrar_apos_resposta()
                )

        except Exception as erro:
            print(f"[OPENAI] Falha ao processar '{nome}': {erro}")

            self.erro_recebido.emit(
                f"A função '{nome}' falhou: {erro}"
            )

        finally:
            self.processando_ferramenta = False
            self.alfred_falando = False
            self.limpar_fila_microfone(fila_microfone)

    # Percorre PACOTES_REGISTRADOS na mesma ordem do worker do Gemini:
    # o primeiro pacote que reconhece o nome responde, e despachar()
    # devolve None quando não reconhece.
    async def _despachar_para_pacotes(self, nome, args):
        # identificar_planta e consultar_segunda_opiniao_visual não
        # recebem a imagem do modelo: quem captura é o cliente, e a
        # imagem entra em args antes do despacho. Mesma exceção
        # documentada em docs/INTEGRATION.md.
        if nome in ("identificar_planta", "consultar_segunda_opiniao_visual"):
            if self.executando_funcao_visual:
                return (
                    "Já existe uma captura de tela/câmera em "
                    "andamento — tente de novo em instantes."
                )

            self.executando_funcao_visual = True

            try:
                self.status_recebido.emit(
                    "Capturando imagem da câmera..."
                )

                args["imagem_bytes"] = await asyncio.to_thread(
                    capturar_camera_bytes
                )

            finally:
                self.executando_funcao_visual = False

        # Tools que capturam a tela por dentro do próprio despachar()
        # (hoje só clicar_elemento_visual): o mutex fica segurado
        # durante o despacho inteiro, não em volta de uma captura.
        segurar_mutex = nome in TOOLS_QUE_CAPTURAM_SOZINHAS

        if segurar_mutex:
            if self.executando_funcao_visual:
                return (
                    "Já existe uma captura de tela/câmera em "
                    "andamento — tente de novo em instantes."
                )

            self.executando_funcao_visual = True

        if nome in ("executar_comando_admin", "confirmar_comando_admin"):
            self.status_recebido.emit(
                "Executando comando administrativo. Pode levar até "
                "alguns minutos, dependendo do comando — aguarde."
            )

        timeout = TIMEOUTS_FUNCAO_POR_NOME.get(nome, TIMEOUT_FUNCAO_PADRAO)

        try:
            for pacote in PACOTES_REGISTRADOS:
                resultado = await self._executar_com_timeout(
                    pacote.despachar,
                    nome,
                    args,
                    timeout=timeout,
                )

                if resultado is not None:
                    return resultado

        finally:
            if segurar_mutex:
                self.executando_funcao_visual = False

        return "Função desconhecida. Nenhuma ação foi executada."

    # Roda uma função síncrona (que pode bloquear) fora do event loop,
    # com timeout, devolvendo uma mensagem amigável em vez de derrubar
    # a sessão.
    async def _executar_com_timeout(self, funcao, *args, timeout=15):
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(funcao, *args),
                timeout=timeout,
            )

        except asyncio.TimeoutError:
            return (
                "A operação demorou mais que o esperado e foi "
                "interrompida com segurança. Avise o usuário e não "
                "tente de novo sozinho."
            )

        except Exception as erro:
            return (
                f"A operação não pôde ser concluída: {erro}. Avise o "
                "usuário e não tente de novo sozinho."
            )

    async def encerrar_apos_resposta(self):
        try:
            await asyncio.sleep(ATRASO_ENCERRAMENTO_SEGUNDOS)

            if self.ativo:
                self.solicitou_encerramento.emit()

        except asyncio.CancelledError:
            pass

    # ================================================================
    # VISÃO
    # ================================================================

    async def processar_funcao_visual(self, nome):
        if self.executando_funcao_visual:
            return (
                "Uma análise visual já está em andamento. "
                "Aguarde a imagem atual."
            )

        agora = time.monotonic()

        repetido = (
            nome == self.ultima_funcao_visual
            and agora - self.tempo_ultima_funcao_visual
            < COOLDOWN_FUNCAO_VISUAL
        )

        if repetido:
            return (
                "Chamada visual duplicada ignorada. "
                "Use a última imagem recebida."
            )

        self.executando_funcao_visual = True
        self.ultima_funcao_visual = nome
        self.tempo_ultima_funcao_visual = agora

        try:
            if nome == "analisar_tela":
                self.status_recebido.emit("Capturando tela...")

                imagem = await asyncio.wait_for(
                    asyncio.to_thread(capturar_tela_bytes),
                    timeout=12,
                )

                self.imagem_visual_pendente = ("tela", imagem)

                return (
                    "A tela foi capturada e será enviada agora para "
                    "análise."
                )

            if nome == "analisar_camera":
                self.status_recebido.emit("Capturando imagem da câmera...")

                imagem = await asyncio.wait_for(
                    asyncio.to_thread(capturar_camera_bytes),
                    timeout=15,
                )

                self.imagem_visual_pendente = ("camera", imagem)

                return (
                    "A câmera foi capturada e será enviada agora para "
                    "análise."
                )

            return "Função visual desconhecida."

        except asyncio.TimeoutError:
            return (
                "A captura visual demorou demais e foi cancelada com "
                "segurança."
            )

        except Exception as erro:
            return f"Não foi possível capturar a imagem: {erro}"

        finally:
            self.executando_funcao_visual = False

    async def _anexar_imagem_visual_pendente(self, conexao):
        pendente = self.imagem_visual_pendente
        self.imagem_visual_pendente = None

        if pendente is None:
            return

        tipo, imagem_bytes = pendente
        origem = "tela" if tipo == "tela" else "câmera"

        await conexao.conversation.item.create(
            item={
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": prompts.ANALISE_IMAGEM_PONTUAL.format(
                            origem=origem
                        ),
                    },
                    {
                        "type": "input_image",
                        "image_url": self._data_url(imagem_bytes),
                        "detail": "auto",
                    },
                ],
            }
        )

        self.status_recebido.emit(
            f"Imagem da {origem} enviada para análise."
        )

    # Botões "ANALISAR TELA" / "ANALISAR CÂMERA" da janela. Passam pelo
    # MESMO processar_funcao_visual das tools, para reaproveitar mutex
    # e cooldown em vez de duplicá-los.
    def solicitar_analise_tela(self):
        self._solicitar_analise("analisar_tela")

    def solicitar_analise_camera(self):
        self._solicitar_analise("analisar_camera")

    def _solicitar_analise(self, nome):
        if not self.loop or not self.conexao:
            self.erro_recebido.emit("Sessão OpenAI ainda não está pronta.")
            return

        asyncio.run_coroutine_threadsafe(
            self._enviar_analise_avulsa(nome),
            self.loop,
        )

    async def _enviar_analise_avulsa(self, nome):
        if self.processando_ferramenta:
            self.erro_recebido.emit(
                "Aguarde a conclusão da ação atual antes da análise "
                "visual."
            )
            return

        self.processando_ferramenta = True
        self.alfred_falando = True

        try:
            resultado = await self.processar_funcao_visual(nome)

            if self.imagem_visual_pendente is None:
                self.erro_recebido.emit(resultado)
                return

            async with self.lock_envio:
                await self._anexar_imagem_visual_pendente(self.conexao)
                await self.conexao.response.create()

        except Exception as erro:
            self.erro_recebido.emit(f"Erro na análise visual: {erro}")

        finally:
            self.processando_ferramenta = False
            self.alfred_falando = False

    # ================================================================
    # REPRODUÇÃO
    # ================================================================

    async def reproduzir_audio(self, fila_saida, fila_microfone):
        with sd.RawOutputStream(
            samplerate=TAXA_SAIDA,
            blocksize=BLOCO,
            dtype="int16",
            channels=CANAIS,
        ) as saida:
            while self.ativo:
                audio_bytes = await fila_saida.get()

                self.alfred_falando = True
                self.limpar_fila_microfone(fila_microfone)

                self.nivel_audio.emit(
                    self.calcular_nivel_audio(audio_bytes)
                )

                await asyncio.to_thread(saida.write, audio_bytes)

                if self.tarefa_liberar_microfone:
                    self.tarefa_liberar_microfone.cancel()

                self.tarefa_liberar_microfone = asyncio.create_task(
                    self.liberar_microfone_apos_fala()
                )

    async def liberar_microfone_apos_fala(self):
        try:
            await asyncio.sleep(ATRASO_REABRIR_MICROFONE)

            self.alfred_falando = False
            self.nivel_audio.emit(0.0)

        except asyncio.CancelledError:
            pass

    @staticmethod
    def limpar_fila_microfone(fila_microfone):
        while True:
            try:
                fila_microfone.get_nowait()

            except asyncio.QueueEmpty:
                break

    @staticmethod
    def calcular_nivel_audio(audio_bytes):
        if not audio_bytes:
            return 0.0

        try:
            amostras = array("h", audio_bytes)

            if not amostras:
                return 0.0

            pico = max(abs(amostra) for amostra in amostras)
            nivel = (pico / 32768.0) ** 0.55

            return max(0.0, min(1.0, nivel))

        except (ValueError, OverflowError):
            return 0.0
