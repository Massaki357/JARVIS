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


TAXA_ENTRADA = 16000
CANAIS = 1
BLOCO = 1024


LIMITE_FILA_MICROFONE = 50

ATRASO_REABRIR_MICROFONE = 0.8

BLOCOS_FALA_PARA_INTERROMPER = 5

CARENCIA_INTERRUPCAO_SEGUNDOS = 0.5

LATENCIA_SAIDA = "high"

TIMEOUT_ESCRITA_AUDIO_SEGUNDOS = 10

FERRAMENTAS_QUE_PRECISAM_DE_IMAGEM = TOOLS_QUE_PRECISAM_DE_IMAGEM

_CAPTURAS = {
    "tela": lambda: captura_tela.capturar_monitor_do_cursor_bytes(),
    "camera": lambda: captura_camera.capturar_camera_bytes(),
}

class RespostaFalada(NamedTuple):
    audio: bytes
    texto: str | None


MAXIMO_MENSAGENS_TRANSCRICAO = 12

FREQUENCIA_BEEP_CHAMADA_INICIADA = 880
DURACAO_BEEP_CHAMADA_INICIADA_MS = 150

MENSAGEM_SEM_SUPORTE = (
    "O cérebro de voz local (alfred-server) só recebe áudio: não dá "
    "para mandar imagem nem texto digitado. Troque PROVEDOR_IA para "
    "gemini ou openai se precisar disso."
)


class VozLocalWorker(QThread):
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

        self.session_handle = session_handle
        self.ativado_por_voz = ativado_por_voz
        self.hibernacao_solicitada = False

        self.transcricao_conversa = list(transcricao_inicial or [])

        self.detector_fala = None

        self.interrupcao_habilitada = interrupcao_ativa()

        self.interrupcoes_na_chamada = 0

        self._blocos_apos_interrupcao = []

        self.loop = None

        self.cliente_mqtt = None

        self._futuro_resposta = None

        self._tipo_esperado = None

        self.alfred_falando = False

        self.encerrou_por_falha = False

        self.timestamp_ultimo_bloco_microfone = 0.0

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
        ativacao_voz.pausar()

        self.loop = asyncio.get_running_loop()

        fila_microfone = asyncio.Queue(
            maxsize=LIMITE_FILA_MICROFONE
        )

        executor_audio = concurrent.futures.ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="jarvis-audio-local",
        )

        tarefas = []

        try:
            self.status_recebido.emit(
                "Conectando ao servidor de voz local..."
            )

            await asyncio.to_thread(self._preparar_detector_de_fala)

            if self.interrupcao_habilitada:
                self.status_recebido.emit(
                    "Interrupção ligada — use fone de ouvido: em caixas "
                    "de som o assistente se interrompe sozinho."
                )

            cliente = ClienteVozLocal(
                ao_receber_texto=self._ao_receber_texto_mqtt,
                ao_receber_saida=self._ao_receber_saida_mqtt,
                ao_receber_erro=self._ao_receber_erro_mqtt,
            )

            sucesso, mensagem = await asyncio.to_thread(
                cliente.conectar
            )

            if not sucesso:
                self.erro_recebido.emit(mensagem)
                self.encerrou_por_falha = True

                return

            self.cliente_mqtt = cliente

            await asyncio.to_thread(
                winsound.Beep,
                FREQUENCIA_BEEP_CHAMADA_INICIADA,
                DURACAO_BEEP_CHAMADA_INICIADA_MS,
            )

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

            ativacao_voz.retomar()

            self.nivel_audio.emit(0.0)

    async def _tarefa_supervisionada(self, nome, corrotina):
        try:
            await corrotina

        except Exception as erro:
            descricao = str(erro) or type(erro).__name__

            print(
                f"[VOZ LOCAL] A tarefa {nome} falhou: {descricao}"
            )

            self.erro_recebido.emit(
                f"Falha em {nome}: {descricao}"
            )

            self.encerrou_por_falha = True
            self.ativo = False

    async def _vigiar_microfone(self):
        while self.ativo:
            await asyncio.sleep(5)

            if not self.ativo:
                break

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

    async def capturar_microfone(self, fila_microfone):
        loop = asyncio.get_running_loop()

        def callback(
            indata,
            frames,
            time_info,
            status,
        ):
            self.timestamp_ultimo_bloco_microfone = time.monotonic()

            if not self.ativo:
                return

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

                if self.alfred_falando and not self.interrupcao_habilitada:
                    return

                try:
                    fila_microfone.put_nowait(audio_bytes)

                except asyncio.QueueFull:
                    pass

            loop.call_soon_threadsafe(adicionar_audio)

        try:
            with sd.RawInputStream(
                samplerate=TAXA_ENTRADA,
                blocksize=BLOCO,
                dtype="int16",
                channels=CANAIS,
                callback=callback,
            ):
                self.timestamp_ultimo_bloco_microfone = time.monotonic()

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

    async def ciclo_de_conversa(
        self,
        fila_microfone,
        executor_audio,
    ):
        while self.ativo:
            pcm_frase = await self._capturar_frase(fila_microfone)

            if not pcm_frase:
                continue

            duracao = audio_wav.duracao_segundos(
                pcm_frase,
                TAXA_ENTRADA,
                CANAIS,
            )

            self.status_recebido.emit(
                f"Transcrevendo {duracao:.1f}s de áudio..."
            )

            resultado = await self._transcrever(pcm_frase)

            if resultado is None:
                continue

            tipo, conteudo = resultado

            if tipo == "erro":
                self._reportar_falha_do_servidor(conteudo)

                continue

            texto = (conteudo.get("texto") or "").strip()

            if not texto:
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

            decisao = await self._rotear(texto)

            # Checar falhou antes do ramo ferramenta/conversa: falha nunca vira conversa.
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
                self._registrar_resultado_local(decisao)

                self._aparar_transcricao()

                if self.ativo:
                    self.status_recebido.emit("Pode falar.")

                continue

            self.status_recebido.emit(
                "Pedindo a resposta falada ao servidor local..."
            )

            resultado = await self._pedir_resposta(conteudo)

            if resultado is None:
                continue

            tipo, conteudo_resposta = resultado

            if tipo == "erro":
                self._reportar_falha_do_servidor(conteudo_resposta)

            else:
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

    def _reportar_falha_do_servidor(self, descricao):
        self.erro_recebido.emit(
            f"O servidor de voz local falhou: {descricao}"
        )

    async def _rotear(self, texto):
        try:
            return await asyncio.to_thread(
                roteamento_hierarquico.processar_turno,
                texto,
                list(self.transcricao_conversa[:-1]),
                self._preparar_argumentos_da_ferramenta,
            )

        except Exception as erro:
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

    def _preparar_argumentos_da_ferramenta(self, nome_funcao, argumentos):
        origem = FERRAMENTAS_QUE_PRECISAM_DE_IMAGEM.get(nome_funcao)

        if origem is None:
            return argumentos

        self.status_recebido.emit(
            f"Capturando imagem d{'a tela' if origem == 'tela' else 'a câmera'}..."
        )

        argumentos = dict(argumentos or {})
        argumentos["imagem_bytes"] = _CAPTURAS[origem]()

        return argumentos

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

    def _registrar_fala_do_assistente(self, texto):
        limpo = (texto or "").strip()

        if not limpo:
            return

        print(f"[VOZ LOCAL] Resposta falada: {limpo}")

        obter_sinalizador().resposta_texto_recebida.emit(limpo)

        self.transcricao_conversa.append(
            {
                "role": "assistant",
                "content": limpo,
            }
        )

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

    def _bloco_tem_fala(self, bloco, nivel):
        if self.detector_fala is None:
            return nivel >= config.LIMIAR_VOZ

        try:
            return self.detector_fala.tem_fala(bloco)

        except Exception as erro:
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

    async def _capturar_frase(self, fila_microfone):
        if self.detector_fala is not None:
            self.detector_fala.zerar()

        pre_fala = collections.deque(
            self._blocos_apos_interrupcao,
            maxlen=config.BLOCOS_PRE_FALA,
        )

        self._blocos_apos_interrupcao = []

        blocos = []
        falando = False
        silencio_acumulado = 0.0
        duracao_total = 0.0

        duracao_com_voz = 0.0

        indice_ultima_voz = -1

        while self.ativo:
            try:
                bloco = await asyncio.wait_for(
                    fila_microfone.get(),
                    timeout=0.2,
                )

            except asyncio.TimeoutError:
                continue

            nivel = self.calcular_nivel_audio(bloco)

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

            if duracao_total >= config.DURACAO_MAXIMA_SEGUNDOS:
                print(
                    "[VOZ LOCAL] Frase atingiu o tempo máximo "
                    f"({config.DURACAO_MAXIMA_SEGUNDOS}s); enviando como está."
                )

                break

        self.nivel_audio.emit(0.0)

        if not falando or not self.ativo:
            return None

        # Mede só os blocos com voz, nunca a duração total do trecho.
        if duracao_com_voz < config.DURACAO_MINIMA_SEGUNDOS:
            return None

        if indice_ultima_voz >= 0:
            blocos = blocos[
                : indice_ultima_voz + 1 + config.BLOCOS_POS_FALA
            ]

        return b"".join(blocos)

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

    async def _pedir_resposta(self, dados):
        dados = dict(dados or {})

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

    async def _publicar_e_aguardar(
        self,
        publicar,
        tipo_esperado,
        timeout,
        topico_resposta,
    ):
        if self.cliente_mqtt is None:
            return None

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
                return (
                    "erro",
                    f"nenhuma resposta em {timeout}s "
                    f"no tópico {topico_resposta}",
                )

        finally:
            self._futuro_resposta = None
            self._tipo_esperado = None

    def _aparar_transcricao(self):
        excedente = len(self.transcricao_conversa) - MAXIMO_MENSAGENS_TRANSCRICAO

        if excedente > 0:
            del self.transcricao_conversa[:excedente]

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

            if time.monotonic() - inicio < CARENCIA_INTERRUPCAO_SEGUNDOS:
                continue

            nivel = self.calcular_nivel_audio(bloco)

            if self._bloco_tem_fala(bloco, nivel):
                consecutivos += 1

            else:
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

        self.alfred_falando = True
        self.limpar_fila_microfone(fila_microfone)

        interrompido = False

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

        tamanho_pedaco = BLOCO * audio_wav.LARGURA_16_BITS * canais

        try:
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

                    if interrompido:
                        break

                    pedaco = pcm[inicio:inicio + tamanho_pedaco]

                    self.nivel_audio.emit(
                        self.calcular_nivel_audio(pedaco)
                    )

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
                self.interrupcoes_na_chamada += 1

                restante = max(len(pcm) - bytes_tocados, 0)

                print(
                    "[INTERRUPÇÃO] O usuário falou por cima — fala "
                    f"cortada (nº {self.interrupcoes_na_chamada} nesta "
                    f"chamada, {restante} bytes de áudio descartados)."
                )

                self.alfred_falando = False

            else:
                await asyncio.sleep(ATRASO_REABRIR_MICROFONE)

                self.limpar_fila_microfone(fila_microfone)
                self.alfred_falando = False

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
            pass

    # Casa a resposta contra self._tipo_esperado antes de resolver.
    def _resolver_futuro(self, resultado):
        futuro = self._futuro_resposta
        tipo, conteudo = resultado

        fora_de_hora = futuro is None or futuro.done()

        etapa_errada = (
            not fora_de_hora
            and tipo != "erro"
            and tipo != self._tipo_esperado
        )

        if fora_de_hora or etapa_errada:
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
