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
    obter_nome_jarvis,
)

from jarvis.nucleo import perfis
from jarvis.nucleo import prompts
from jarvis.nucleo.preferencias import interrupcao_ativa
from jarvis.nucleo.sinalizador import obter_sinalizador

from jarvis.nucleo.registro_pacotes import (
    PACOTES_REGISTRADOS,
    TOOLS_QUE_CAPTURAM_SOZINHAS,
    TOOLS_QUE_PRECISAM_DE_IMAGEM,
    TOOLS_SILENCIOSAS,
)

from jarvis.servicos.visao.captura_tela import (
    capturar_monitor_do_cursor_bytes,
    capturar_tela_bytes,
)
from jarvis.servicos.visao.captura_camera import capturar_camera_bytes

from jarvis.pacotes import ativacao_voz

from jarvis.pacotes.ativacao_voz.config import NOME_ATIVACAO
from jarvis.pacotes import admin_terminal
from jarvis.pacotes import discord_jarvis
from jarvis.pacotes import memoria_obsidian
from jarvis.pacotes import rede_jarvis

from jarvis.cerebro.openai_realtime import esquema


TAXA_ENTRADA = 24000
TAXA_SAIDA = 24000
CANAIS = 1
BLOCO = 1024

ATRASO_REABRIR_MICROFONE = 0.8

LIMITE_FILA_MICROFONE = 50

COOLDOWN_FUNCAO_VISUAL = 8.0

TIMEOUT_FUNCAO_PADRAO = 20

TIMEOUTS_FUNCAO_POR_NOME = {
    "executar_comando_admin": (
        admin_terminal.config.TIMEOUT_COMANDO_LONGO_SEGUNDOS + 30
    ),
    "confirmar_comando_admin": (
        admin_terminal.config.TIMEOUT_COMANDO_LONGO_SEGUNDOS + 30
    ),
}


TIMEOUT_ENVIO_SESSAO_SEGUNDOS = 10

LIMITE_TAREFAS_FUNCAO_SIMULTANEAS = 4

ATRASO_ENCERRAMENTO_SEGUNDOS = 2.8

MAXIMO_MENSAGENS_TRANSCRICAO = 12

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

    types.FunctionDeclaration(
        name="pausar_chamada",
        description=(
            "Pausa a chamada atual SEM encerrá-la de vez — a "
            "conversa fica pronta para continuar de onde parou "
            "quando o usuário chamar de novo pela frase de "
            "ativação, em vez de terminar. Use somente depois de "
            "perguntar se o usuário precisa de mais alguma coisa "
            "e ele confirmar que não precisa. Nunca use no lugar "
            "de encerrar_chamada."
        ),
    ),
]


class OpenAIRealtimeWorker(QThread):

    status_recebido = Signal(str)
    erro_recebido = Signal(str)
    chamada_encerrada = Signal()
    nivel_audio = Signal(float)
    solicitou_encerramento = Signal()

    solicitou_reconexao = Signal()
    session_handle_atualizado = Signal(str)

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

        self.slug_perfil = slug_perfil or perfis.perfil_ativo()
        self.loop = None
        self.conexao = None
        self.session_handle = session_handle
        self.ativado_por_voz = ativado_por_voz
        self.hibernacao_solicitada = False

        self.lock_envio = None

        self.conexao_travada = False


        self.tarefas_funcao_ativas = []

        self.processando_ferramenta = False

        self.imagem_visual_pendente = None

        self.alfred_falando = False
        self.tarefa_liberar_microfone = None
        self.tarefa_encerramento = None

        self.interrupcao_habilitada = interrupcao_ativa()

        self.interrupcoes_na_chamada = 0

        self.item_audio_tocando = None
        self.bytes_tocados_item = 0

        self.itens_interrompidos = set()

        self.executando_funcao_visual = False
        self.ultima_funcao_visual = None
        self.tempo_ultima_funcao_visual = 0.0

        self.silenciar_audio_ate_fim_turno = False

        self.transcricao_conversa = list(transcricao_inicial or [])
        self._buffer_transcricao_usuario = ""
        self._buffer_transcricao_assistente = ""

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
    # Envolve QUALQUER envio para a sessão da Realtime API (uma
    # corrotina já construída e ainda não aguardada — ex:
    # self._enviar_para_sessao(conexao.response.create())) com um
    # timeout, e marca self.conexao_travada se estourar ou falhar.
    # Sempre repropaga a exceção original: quem chama continua
    # tratando do mesmo jeito que já tratava, este método só adiciona
    # o timeout e o registro do travamento, nunca engole o erro.
    #
    # O ponto crítico é o timeout soltar o self.lock_envio. Sem ele,
    # um único envio pendurado segura a trava para sempre e congela a
    # conversa inteira — nenhuma chamada de função consegue responder
    # seu function_call_output, e o protocolo não deixa o modelo
    # voltar a falar sem essa resposta.
    async def _enviar_para_sessao(self, corrotina):
        try:
            return await asyncio.wait_for(
                corrotina,
                timeout=TIMEOUT_ENVIO_SESSAO_SEGUNDOS,
            )

        except asyncio.TimeoutError:
            print(
                "[CONEXÃO] Envio para a sessão da OpenAI travou "
                f"(timeout de {TIMEOUT_ENVIO_SESSAO_SEGUNDOS}s) — "
                "marcando a conexão como travada."
            )

            self.conexao_travada = True
            raise

        except Exception as erro:
            print(
                f"[CONEXÃO] Envio para a sessão da OpenAI falhou: "
                f"{erro!r} — marcando a conexão como travada."
            )

            self.conexao_travada = True
            raise

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
                await self._enviar_para_sessao(
                    self.conexao.conversation.item.create(
                        item={
                            "type": "message",
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_text",
                                    "text": (
                                        prompts.ANUNCIO_ESPONTANEO.format(
                                            texto=texto
                                        )
                                    ),
                                },
                            ],
                        }
                    )
                )

                await self._enviar_para_sessao(
                    self.conexao.response.create()
                )

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
                await self._enviar_para_sessao(
                    self.conexao.conversation.item.create(
                        item={
                            "type": "message",
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_image",
                                    "image_url": self._data_url(
                                        imagem_bytes
                                    ),
                                    "detail": "auto",
                                },
                            ],
                        }
                    )
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
                await self._enviar_para_sessao(
                    self.conexao.conversation.item.create(
                        item={
                            "type": "message",
                            "role": "user",
                            "content": [
                                {"type": "input_text", "text": texto},
                            ],
                        }
                    )
                )

                await self._enviar_para_sessao(
                    self.conexao.response.create()
                )

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
                await self._enviar_para_sessao(
                    self.conexao.conversation.item.create(
                        item={
                            "type": "message",
                            "role": "user",
                            "content": conteudo,
                        }
                    )
                )

                await self._enviar_para_sessao(
                    self.conexao.response.create()
                )

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
    # prompt_bruto vem de perfis.preparar_chamada(), resolvido pelo
    # chamador: o corpo da instrução é o sistema.md do perfil ativo,
    # não mais um texto fixo. Passado como parâmetro (e não relido
    # aqui) para o arquivo ser lido UMA vez por chamada e para o
    # caminho de falha ficar só em preparar_chamada.
    def _montar_instrucao_sistema(self, memorias_atuais, prompt_bruto):
        bloco_autenticacao = (
            prompts.bloco_autenticacao()
            if EXIGIR_AUTENTICACAO
            else ""
        )

        return (
            bloco_autenticacao
            + prompts.instrucao_sistema_corpo(
                texto_bruto=prompt_bruto
            )
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

        # Resolve o perfil desta chamada de uma vez:
        # ferramentas permitidas, texto do prompt e um
        # aviso se algo deu errado. FALHA FECHADA — um
        # perfil ilegível deixa a chamada SEM ferramentas,
        # nunca com todas (ver perfis.preparar_chamada).
        perfil_da_chamada = await asyncio.to_thread(
            perfis.preparar_chamada,
            self.slug_perfil,
        )

        # Um perfil que não carrega é reportado à INTERFACE, não só ao
        # console: ninguém está olhando o terminal durante uma chamada
        # de verdade. erro_recebido cai no registro de atividade e no
        # painel de console da janela.
        if perfil_da_chamada["aviso"]:
            self.erro_recebido.emit(perfil_da_chamada["aviso"])

        # A lista que chega ao filtro já é só o que ESTE
        # provedor oferece (4 nativas, não as 16 do
        # Gemini), então uma ferramenta do perfil que só
        # existe no Gemini simplesmente não aparece — sem
        # erro e sem tabela de equivalência em lugar
        # nenhum.
        ferramentas = esquema.montar_ferramentas(
            FUNCTION_DECLARATIONS_NATIVAS,
            PACOTES_REGISTRADOS,
            filtro=lambda declaracoes: (
                perfis.filtrar_declaracoes(
                    declaracoes,
                    perfil_da_chamada["permitidas"],
                )
            ),
        )

        print(
            f"[PERFIL] {self.slug_perfil}: "
            f"{len(ferramentas)} ferramentas nesta chamada."
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
                            memorias_atuais,
                            perfil_da_chamada["prompt_bruto"],
                        ),
                        "audio": {
                            "input": {
                                "format": {
                                    "type": "audio/pcm",
                                    "rate": TAXA_ENTRADA,
                                },
                                "turn_detection": self._configuracao_vad(),
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

                self.status_recebido.emit(
                    f"{obter_nome_jarvis()} conectado. Pode falar."
                )

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

                # Mesma lógica e mesmo motivo do GeminiLiveWorker (ver
                # o comentário lá): só quando esta chamada veio da
                # ativação por voz, pede ao modelo pra cumprimentar
                # agora. Enviado só depois de RECEPÇÃO já estar na
                # lista de tarefas acima.
                if self.ativado_por_voz:
                    texto_saudacao = prompts.SAUDACAO_ATIVACAO_POR_VOZ

                    async with self.lock_envio:
                        await self._enviar_para_sessao(
                            conexao.conversation.item.create(
                                item={
                                    "type": "message",
                                    "role": "user",
                                    "content": [
                                        {
                                            "type": "input_text",
                                            "text": texto_saudacao,
                                        },
                                    ],
                                }
                            )
                        )

                        await self._enviar_para_sessao(
                            conexao.response.create()
                        )

                try:
                    while self.ativo:
                        # Conexão travada (ver _enviar_para_sessao):
                        # as três tarefas centrais continuam vivas
                        # nesse caso, então nada abaixo perceberia o
                        # problema — a chamada ficaria viva e muda.
                        # Não tenta avisar por voz: o aviso seria mais
                        # um envio, que travaria do mesmo jeito.
                        if self.conexao_travada:
                            self.erro_recebido.emit(
                                "A conexão com a OpenAI travou. "
                                "Encerrando a chamada — é só iniciar "
                                "outra."
                            )

                            self.ativo = False
                            break

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

                    # Chamadas de função ainda em andamento quando a
                    # chamada termina. Itera sobre uma CÓPIA da lista:
                    # cancel() dispara _ao_finalizar_tarefa_funcao, que
                    # remove o item da lista original.
                    tarefas_funcao = list(self.tarefas_funcao_ativas)

                    for tarefa_funcao in tarefas_funcao:
                        tarefa_funcao.cancel()

                    await asyncio.gather(
                        *tarefas,
                        *tarefas_funcao,
                        return_exceptions=True,
                    )

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

    def _configuracao_vad(self):
        """
        O turn_detection da sessão.

        Com interrupção ligada, interrupt_response vai EXPLÍCITO em
        True: é o servidor quem cancela a resposta em andamento assim
        que detecta a voz do usuário (campo confirmado no SDK
        instalado, ServerVad.interrupt_response). O cliente só precisa
        parar de tocar o que já chegou — ver _interromper_fala.

        Com interrupção desligada, o dicionário fica EXATAMENTE como
        era antes desta mudança, sem nenhum campo a mais: o padrão do
        servidor continua valendo, e o comportamento não muda nem para
        os anúncios espontâneos (rede_jarvis, admin_terminal), que
        dependem desse padrão.
        """
        configuracao = {"type": "server_vad"}

        if self.interrupcao_habilitada:
            configuracao["interrupt_response"] = True

        return configuracao

    def _microfone_bloqueado(self):
        """
        Se o áudio do microfone deve ser DESCARTADO agora.

        As três barreiras do microfone (o callback do dispositivo, o
        enfileiramento e o laço de envio) consultam esta função, e não
        uma condição copiada em cada uma. No worker do Gemini são três
        cópias da mesma condição, e a documentação dele precisa avisar
        que reverter UMA delas desliga a interrupção em silêncio — aqui
        esse erro não tem onde acontecer.

        processando_ferramenta continua bloqueando sempre, com ou sem
        interrupção: o que o usuário pediu foi interromper a FALA, e a
        execução de uma ferramenta não é fala.
        """
        if self.processando_ferramenta:
            return True

        return self.alfred_falando and not self.interrupcao_habilitada

    async def enviar_microfone(self, conexao, fila_microfone):
        loop = asyncio.get_running_loop()

        def callback(indata, frames, time_info, status):
            if not self.ativo:
                return

            if self._microfone_bloqueado():
                return

            if status:
                print("Aviso microfone:", status)

            audio_bytes = bytes(indata)

            def adicionar_audio():
                if not self.ativo or self._microfone_bloqueado():
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

                    if self._microfone_bloqueado():
                        continue

                    # Anima as barras enquanto ESCUTA, como o cérebro
                    # local já fazia. Só quando o ALFRED não está
                    # falando: nesse caso quem move as barras é a
                    # própria voz dele (reproduzir_audio), e os dois
                    # níveis brigando no mesmo sinal fariam a animação
                    # piscar. Numa interrupção, _interromper_fala zera
                    # alfred_falando e o microfone assume na hora.
                    if not self.alfred_falando:
                        self.nivel_audio.emit(
                            self.calcular_nivel_audio(audio_bytes)
                        )

                    async with self.lock_envio:
                        # É o envio mais frequente da sessão (~15x por
                        # segundo), então é também o primeiro a
                        # perceber um transporte travado — por isso
                        # passa pelo mesmo wrapper, e não direto.
                        await self._enviar_para_sessao(
                            conexao.input_audio_buffer.append(
                                audio=base64.b64encode(
                                    audio_bytes
                                ).decode("ascii")
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
                item_id = getattr(evento, "item_id", None)

                # Resto de uma fala que o usuário já interrompeu: o
                # servidor gera áudio mais rápido que o tempo real, então
                # ainda chegam deltas dela depois do corte. Tocá-los
                # seria o ALFRED voltar a falar por cima do usuário.
                if item_id is not None and item_id in self.itens_interrompidos:
                    continue

                if not self.silenciar_audio_ate_fim_turno:
                    self.alfred_falando = True

                    if self.tarefa_liberar_microfone:
                        self.tarefa_liberar_microfone.cancel()

                    # Com interrupção, o microfone NÃO pode ser limpo
                    # aqui: é justamente enquanto o ALFRED fala que o
                    # usuário precisa conseguir ser ouvido, e jogar fora
                    # os blocos dele engoliria o começo da interrupção.
                    if not self.interrupcao_habilitada:
                        self.limpar_fila_microfone(fila_microfone)

                    # (item_id, bytes): reproduzir_audio precisa saber a
                    # qual item cada bloco pertence para contar quanto de
                    # cada fala o usuário realmente ouviu.
                    await fila_saida.put(
                        (item_id, base64.b64decode(evento.delta))
                    )

            elif tipo == "input_audio_buffer.speech_started":
                # Evento do server_vad confirmado na documentação e no
                # SDK instalado (InputAudioBufferSpeechStartedEvent): o
                # servidor detectou voz no microfone. Com interrupção
                # ligada e o ALFRED no meio de uma fala, é o corte.
                #
                # Sem interrupção esse evento chega do mesmo jeito (é
                # assim que o servidor sabe que o usuário começou a
                # falar), e aí não há nada a fazer — o microfone nem
                # chega ao servidor enquanto o ALFRED fala.
                if self.interrupcao_habilitada and (
                    self.alfred_falando or not fila_saida.empty()
                ):
                    await self._interromper_fala(conexao, fila_saida)

            elif tipo == "response.function_call_arguments.done":
                argumentos = esquema.interpretar_argumentos(
                    getattr(evento, "arguments", None)
                )

                # Uma função lenta não pode bloquear este laço (áudio
                # incluído) — mesma correção já feita no worker do
                # Gemini. Cada chamada vira uma tarefa própria.
                #
                # A tarefa PRECISA ficar guardada em
                # self.tarefas_funcao_ativas: o asyncio mantém só
                # referência fraca a uma task em execução, então uma
                # task criada e esquecida pode sumir no meio do
                # caminho — e um function_call_output que nunca é
                # enviado deixa o modelo esperando aquele call_id para
                # sempre. Ver _ao_finalizar_tarefa_funcao.
                if (
                    len(self.tarefas_funcao_ativas)
                    >= LIMITE_TAREFAS_FUNCAO_SIMULTANEAS
                ):
                    corrotina = self._recusar_chamada_de_funcao(
                        conexao,
                        evento.call_id,
                        evento.name,
                    )

                else:
                    corrotina = self.processar_chamada_de_funcao(
                        conexao,
                        evento.call_id,
                        evento.name,
                        argumentos,
                        fila_microfone,
                    )

                tarefa = asyncio.create_task(
                    corrotina,
                    name=f"FUNÇÃO:{evento.name}",
                )

                self.tarefas_funcao_ativas.append(tarefa)

                tarefa.add_done_callback(
                    self._ao_finalizar_tarefa_funcao
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

    # Chamado quando uma tarefa de self.tarefas_funcao_ativas termina
    # (sucesso, erro ou cancelamento), via Task.add_done_callback —
    # então roda de forma síncrona, sempre na thread do loop
    # assíncrono. Tira a tarefa da lista para ela não crescer para
    # sempre. Mesma função e mesmo motivo do método de mesmo nome em
    # jarvis/cerebro/gemini/cliente_live.py.
    def _ao_finalizar_tarefa_funcao(self, tarefa):
        if tarefa in self.tarefas_funcao_ativas:
            self.tarefas_funcao_ativas.remove(tarefa)

        if tarefa.cancelled():
            return

        erro = tarefa.exception()

        if erro is not None:
            # Não deveria acontecer: processar_chamada_de_funcao já
            # captura tudo internamente. Se ainda assim escapar, pelo
            # menos aparece no console e na interface, em vez de ficar
            # totalmente silencioso (que é o comportamento padrão do
            # asyncio quando ninguém checa o resultado de uma Task).
            print(
                "[FUNÇÃO] Exceção não tratada numa tarefa de função: "
                f"{erro!r}"
            )

            self.erro_recebido.emit(
                f"A chamada de função '{tarefa.get_name()}' falhou de "
                f"forma inesperada: {erro}"
            )

    # Responde uma chamada de função que nem chegou a ser executada,
    # porque já há LIMITE_TAREFAS_FUNCAO_SIMULTANEAS rodando. Responder
    # é obrigatório mesmo recusando: sem o function_call_output, o
    # modelo fica preso esperando aquele call_id e a conversa para.
    async def _recusar_chamada_de_funcao(self, conexao, call_id, nome):
        texto = (
            f"Não foi possível iniciar '{nome}' agora — já existem "
            f"{LIMITE_TAREFAS_FUNCAO_SIMULTANEAS} outras ações em "
            "andamento ao mesmo tempo (limite atingido). Informe isso "
            "ao usuário de forma breve e diga que ele pode pedir de "
            "novo em instantes. NÃO tente de novo sozinho."
        )

        print(f"[FUNÇÃO] Limite simultâneo atingido, recusando '{nome}'.")

        try:
            async with self.lock_envio:
                await self._enviar_para_sessao(
                    conexao.conversation.item.create(
                        item={
                            "type": "function_call_output",
                            "call_id": call_id,
                            "output": texto,
                        }
                    )
                )

                await self._enviar_para_sessao(conexao.response.create())

        except Exception as erro:
            print(f"[FUNÇÃO] Falha ao recusar '{nome}': {erro}")

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

            elif nome == "pausar_chamada":
                self.hibernacao_solicitada = True

                resultado = (
                    "Chamada pausada. Diga ao usuário, de forma breve "
                    "e natural, que para falar com você de novo é só "
                    f"dizer '{NOME_ATIVACAO}'."
                )
                encerrar_depois = True

            else:
                resultado = await self._despachar_para_pacotes(nome, args)

            async with self.lock_envio:
                # Este é o envio que NÃO pode pendurar. Enquanto este
                # function_call_output não chega, o protocolo não
                # deixa o modelo voltar a falar — então um envio sem
                # timeout aqui congela a conversa inteira, e ainda
                # segura self.lock_envio, congelando junto toda
                # chamada de função seguinte.
                await self._enviar_para_sessao(
                    conexao.conversation.item.create(
                        item={
                            "type": "function_call_output",
                            "call_id": call_id,
                            "output": str(resultado),
                        }
                    )
                )

                # Só depois de responder à ferramenta é que a imagem
                # pendente é enviada — a mesma ordem usada pelo worker
                # do Gemini, e a que o protocolo espera.
                if self.imagem_visual_pendente is not None:
                    await self._anexar_imagem_visual_pendente(conexao)

                await self._enviar_para_sessao(conexao.response.create())

            if encerrar_depois:
                if self.tarefa_encerramento:
                    self.tarefa_encerramento.cancel()

                self.tarefa_encerramento = asyncio.create_task(
                    self.encerrar_apos_resposta()
                )

        except Exception as erro:
            # str(TimeoutError()) é VAZIO — e agora um timeout de envio
            # chega mesmo aqui (ver _enviar_para_sessao). Sem este
            # fallback a mensagem terminaria em dois-pontos e nada,
            # que é a mesma armadilha já corrigida uma vez em
            # _tarefa_supervisionada, no worker do Gemini.
            descricao = str(erro) or type(erro).__name__

            print(f"[OPENAI] Falha ao processar '{nome}': {descricao}")

            self.erro_recebido.emit(
                f"A função '{nome}' falhou: {descricao}"
            )

        finally:
            self.processando_ferramenta = False
            self.alfred_falando = False
            self.limpar_fila_microfone(fila_microfone)

    # Percorre PACOTES_REGISTRADOS na mesma ordem do worker do Gemini:
    # o primeiro pacote que reconhece o nome responde, e despachar()
    # devolve None quando não reconhece.
    async def _despachar_para_pacotes(self, nome, args):
        # Estas tools não recebem a imagem do modelo: quem captura é o
        # cliente, e a imagem entra em args antes do despacho. Mesma
        # exceção documentada em docs/INTEGRATION.md. A origem
        # ("tela" ou "camera") vem da própria lista — descrever_tela
        # precisa da TELA, e antes isto capturava sempre a câmera.
        if nome in TOOLS_QUE_PRECISAM_DE_IMAGEM:
            origem_imagem = TOOLS_QUE_PRECISAM_DE_IMAGEM[nome]

            if self.executando_funcao_visual:
                return (
                    "Já existe uma captura de tela/câmera em "
                    "andamento — tente de novo em instantes."
                )

            self.executando_funcao_visual = True

            try:
                self.status_recebido.emit(
                    "Capturando imagem da tela..."
                    if origem_imagem == "tela"
                    else "Capturando imagem da câmera..."
                )

                # capturar_monitor_do_cursor_bytes, e não
                # capturar_tela_bytes: em monitor duplo, "olha minha
                # tela" quer dizer o monitor que o usuário está olhando.
                captura = (
                    capturar_monitor_do_cursor_bytes
                    if origem_imagem == "tela"
                    else capturar_camera_bytes
                )

                args["imagem_bytes"] = await asyncio.to_thread(captura)

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
        # Mesma lógica do GeminiLiveWorker: solicitou_hibernacao em
        # vez de solicitou_encerramento quando foi pausar_chamada que
        # agendou esta espera.
        try:
            await asyncio.sleep(ATRASO_ENCERRAMENTO_SEGUNDOS)

            if self.ativo:
                if self.hibernacao_solicitada:
                    self.hibernacao_solicitada = False

                    self.solicitou_hibernacao.emit()

                else:
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

        await self._enviar_para_sessao(
            conexao.conversation.item.create(
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

                await self._enviar_para_sessao(
                    self.conexao.response.create()
                )

        except Exception as erro:
            self.erro_recebido.emit(f"Erro na análise visual: {erro}")

        finally:
            self.processando_ferramenta = False
            self.alfred_falando = False

    # ================================================================
    # INTERRUPÇÃO DE FALA
    # ================================================================

    def _milissegundos_tocados(self):
        """
        Quanto do item atual já saiu pelo alto-falante, em ms.

        Contado pelos bytes que saida.write() terminou de escrever —
        nunca pelos que chegaram do servidor, que vêm bem adiantados.
        Isso pode ficar alguns milissegundos ABAIXO do real, nunca
        acima, e é de propósito: a documentação da Realtime API diz
        que um audio_end_ms maior que a duração real do áudio faz o
        servidor responder com erro. Errar para menos só significa o
        modelo achar que falou um pedacinho a menos.

        PCM16 mono: 2 bytes por amostra.
        """
        bytes_por_segundo = TAXA_SAIDA * 2 * CANAIS

        return int(self.bytes_tocados_item * 1000 / bytes_por_segundo)

    async def _interromper_fala(self, conexao, fila_saida):
        """
        Corta a fala do ALFRED porque o usuário começou a falar.

        O servidor já cancelou a resposta sozinho (interrupt_response
        em _configuracao_vad). O que sobra para o cliente são as três
        coisas que só ele sabe fazer:

          1. parar de tocar o que já chegou e ainda está na fila — o
             servidor manda o áudio adiantado, então sem isto o ALFRED
             continuaria falando por segundos depois do corte;
          2. soltar o microfone na hora, sem esperar
             ATRASO_REABRIR_MICROFONE — o usuário está falando AGORA;
          3. contar ao servidor até onde o usuário ouviu
             (conversation.item.truncate), para o histórico do modelo
             não conter uma frase que ninguém escutou.

        Nunca levanta: é chamado de dentro de receber_eventos, e uma
        exceção aqui mataria a recepção da chamada inteira.
        """
        item_cortado = self.item_audio_tocando
        milissegundos = self._milissegundos_tocados()

        # Todo item que ainda estava na fila também foi cortado — os
        # deltas dele que ainda chegarem precisam ser descartados.
        if item_cortado is not None:
            self.itens_interrompidos.add(item_cortado)

        descartados = 0

        while True:
            try:
                item_na_fila, _bytes = fila_saida.get_nowait()

            except asyncio.QueueEmpty:
                break

            descartados += 1

            if item_na_fila is not None:
                self.itens_interrompidos.add(item_na_fila)

        if self.tarefa_liberar_microfone:
            self.tarefa_liberar_microfone.cancel()
            self.tarefa_liberar_microfone = None

        self.alfred_falando = False
        self.nivel_audio.emit(0.0)

        self.interrupcoes_na_chamada += 1

        print(
            "[INTERRUPÇÃO] O usuário começou a falar e a fala do "
            f"{obter_nome_jarvis()} foi cortada "
            f"(interrupção nº {self.interrupcoes_na_chamada} nesta "
            f"chamada; {descartados} blocos de áudio descartados; "
            f"{milissegundos} ms já tinham sido ouvidos)."
        )

        # Sem nada tocado ainda, não há o que truncar — e mandar
        # audio_end_ms=0 para um item cujo áudio nem começou é pedir
        # um erro do servidor sem ganho nenhum.
        if item_cortado is None or milissegundos <= 0:
            return

        try:
            async with self.lock_envio:
                await self._enviar_para_sessao(
                    conexao.conversation.item.truncate(
                        item_id=item_cortado,
                        content_index=0,
                        audio_end_ms=milissegundos,
                    )
                )

        except Exception as erro:
            # _enviar_para_sessao já marcou conexao_travada se foi o
            # transporte; o laço de supervisão cuida disso. Aqui só não
            # pode deixar a exceção subir e derrubar a recepção.
            print(
                "[INTERRUPÇÃO] Não consegui avisar o servidor até onde "
                f"a fala foi ouvida: {erro!r}"
            )

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
                item_id, audio_bytes = await fila_saida.get()

                # Um bloco pode ter entrado na fila no instante entre o
                # corte e o descarte da fila em _interromper_fala.
                if item_id is not None and item_id in self.itens_interrompidos:
                    continue

                # Item novo: a contagem do que foi ouvido recomeça.
                if item_id != self.item_audio_tocando:
                    self.item_audio_tocando = item_id
                    self.bytes_tocados_item = 0

                self.alfred_falando = True

                # Mesma exceção de receber_eventos: com interrupção, os
                # blocos do usuário que chegaram enquanto o ALFRED fala
                # são exatamente os que precisam chegar ao servidor.
                if not self.interrupcao_habilitada:
                    self.limpar_fila_microfone(fila_microfone)

                self.nivel_audio.emit(
                    self.calcular_nivel_audio(audio_bytes)
                )

                await asyncio.to_thread(saida.write, audio_bytes)

                # Cortado DURANTE o write: _interromper_fala já soltou o
                # microfone e zerou as barras. Agendar a liberação de
                # novo aqui só faria as barras piscarem para zero 0,8s
                # depois, no meio da fala do usuário.
                if item_id is not None and item_id in self.itens_interrompidos:
                    continue

                # Só conta DEPOIS de escrito — ver _milissegundos_tocados.
                self.bytes_tocados_item += len(audio_bytes)

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
