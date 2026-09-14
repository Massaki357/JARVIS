import asyncio
import base64
import contextlib
import concurrent.futures
import time
import os
import warnings
import winsound
import collections
import queue

from jarvis.nucleo.preferencias import interrupcao_ativa

from jarvis.nucleo import prompts

from array import array

import sounddevice as sd

from PySide6.QtCore import QThread, Signal
from google import genai
from google.genai import types

from jarvis.nucleo.config import (
    EXIGIR_AUTENTICACAO,
    GEMINI_API_KEY,
    GEMINI_LIVE_MODEL,
    GEMINI_LIVE_MODEL_FALLBACK,
    GEMINI_VOICE,
    TIMEOUT_INATIVIDADE_SEGUNDOS,
    obter_nome_jarvis,
)

from jarvis.servicos.visao.captura_tela import (
    capturar_monitor_do_cursor_bytes,
    salvar_print_bytes,
)
from jarvis.servicos.visao.captura_camera import capturar_camera_bytes, salvar_foto_bytes
from jarvis.servicos.visao.monitor_continuo import MonitorTelaContinuo

from jarvis.servicos.email.remetente import enviar_email
from jarvis.servicos.email.leitor import ler_emails, baixar_anexo
from jarvis.servicos import aviso_ferramenta

from jarvis.pacotes import explorador_windows

from jarvis.pacotes import rede_jarvis

from jarvis.pacotes import admin_terminal

from jarvis.pacotes import discord_jarvis

from jarvis.pacotes import ativacao_voz

from jarvis.pacotes.ativacao_voz.config import NOME_ATIVACAO

from jarvis.nucleo.sinalizador import obter_sinalizador

from jarvis.pacotes import memoria_obsidian

from jarvis.nucleo import perfis

from jarvis.nucleo.registro_pacotes import (
    PACOTES_REGISTRADOS,
    TOOLS_QUE_CAPTURAM_SOZINHAS,
    TOOLS_QUE_PRECISAM_DE_IMAGEM,
    TOOLS_SILENCIOSAS,
)


TAXA_ENTRADA = 16000
TAXA_SAIDA = 24000
CANAIS = 1
BLOCO = 1024

ATRASO_REABRIR_MICROFONE = 0.8

LIMITE_FILA_MICROFONE = 50

DEBUG_TIMING_DISPATCH = False

DEBUG_TIMING_MICROFONE = False

DEBUG_TIMING_FILA_SAIDA = False

DEBUG_TIMING_CONGELAMENTO = False

COOLDOWN_FUNCAO_VISUAL = 8.0

INTERVALO_VISUALIZACAO_CONTINUA = 1.5

TIMEOUT_VISUALIZACAO_CONTINUA = 90

TIMEOUT_RASCUNHO_EMAIL = 120

TIMEOUT_ULTIMA_CAPTURA_SEGUNDOS = 300

FREQUENCIA_BEEP_CHAMADA_INICIADA = 880
DURACAO_BEEP_CHAMADA_INICIADA_MS = 150

LIMITE_TAREFAS_FUNCAO_SIMULTANEAS = 4

TIMEOUT_TAREFA_FUNCAO_SEGUNDOS = 20

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

LIMITE_RESPOSTA_IMEDIATA_SEGUNDOS = 5

TIMEOUT_ENVIO_SESSAO_SEGUNDOS = 10

TIMEOUT_CONEXAO_GEMINI_SEGUNDOS = 15

LATENCIA_SAIDA = "high"

TIMEOUT_ESCRITA_AUDIO_SEGUNDOS = 10

# Pausa só hiberna com a despedida registrada no servidor; senão a retomada refaz o turno e pausa de novo.
LIMITE_ESPERA_PAUSA_SEGUNDOS = 15

LIMITE_DESPEDIDA_TOCANDO_SEGUNDOS = 10

INTERVALO_VIGILANCIA_SEGUNDOS = 5.0
LIMITE_FALANDO_PRESO_SEGUNDOS = 60.0
LIMITE_FUNCAO_VISUAL_PRESA_SEGUNDOS = 120.0
LIMITE_FILA_SAIDA_PARADA = 200

LIMITE_MICROFONE_MUDO_SEGUNDOS = 10.0


MAXIMO_MENSAGENS_TRANSCRICAO = 12

TAMANHO_BLOCO_AVISO = 4800

MAXIMO_RESPOSTAS_LEMBRADAS = 20


# Imagem fora da resposta da função deixa o modelo mudo ou chutando; o base64 pronto contorna o json.dumps de bytes do SDK.
warnings.filterwarnings(
    "ignore",
    message=(
        r"Pydantic serializer warnings:\s+PydanticSerializationUnexpectedValue"
        r"\(Expected `bytes`.*field_name='data'.*input_type=str\]\)\s*$"
    ),
)


def _partes_imagem_resposta(imagem_bytes):
    if not imagem_bytes:
        return None

    return [
        types.FunctionResponsePart(
            inline_data=types.FunctionResponseBlob.model_construct(
                data=base64.b64encode(imagem_bytes).decode("ascii"),
                mime_type="image/jpeg",
            )
        )
    ]


class GeminiLiveWorker(QThread):
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

        self.ativado_por_voz = ativado_por_voz

        self.hibernacao_solicitada = False

        self.fase_pausa = None
        self.pausa_registrada = None

        self.session_handle = session_handle

        self.renovacao_em_andamento = False

        self.silenciar_audio_ate_fim_turno = False
        self.loop = None
        self.sessao = None

        self.alfred_falando = False

        self.timestamp_mic_reaberto = time.monotonic()

        self.timestamp_ultima_geracao_gemini = time.monotonic()

        self.interrupcao_habilitada = interrupcao_ativa()

        self.conexao_travada = False

        self._debug_inicio_mudo = None

        self._debug_fila_timestamps = collections.deque()
        self._debug_atraso_max_desde_tick = 0.0
        self._debug_atraso_soma_desde_tick = 0.0
        self._debug_atraso_contagem_desde_tick = 0
        self._debug_numero_turno = 0
        self._debug_timestamp_ultimo_envio_mic = None
        self._debug_inicio_chamada = time.monotonic()

        self._debug_timestamp_ultima_resposta_qualquer = time.monotonic()

        self._debug_nivel_mic_maximo_desde_tick = 0.0

        self._debug_envio_max_desde_tick = 0.0
        self._debug_envio_soma_desde_tick = 0.0
        self._debug_envio_contagem_desde_tick = 0

        self.tarefa_liberar_microfone = None
        self.tarefa_encerramento = None

        # Referência obrigatória: o asyncio só guarda referência fraca à task (CLAUDE.md).
        self.tarefas_funcao_ativas = []

        self.tarefas_aviso = set()
        self.fila_saida_atual = None
        self.chamadas_canceladas = set()
        self.respostas_recentes = collections.deque(
            maxlen=MAXIMO_RESPOSTAS_LEMBRADAS
        )
        self.voltar_status_ouvindo = False

        self.timestamp_ultima_atividade = time.monotonic()

        self.executando_funcao_visual = False

        self.timestamp_ultima_reproducao = 0.0

        self.timestamp_ultimo_bloco_microfone = 0.0

        self.encerrou_por_falha = False

        self.interrupcoes_na_chamada = 0

        self.transcricao_conversa = list(transcricao_inicial or [])
        self._buffer_transcricao_usuario = ""

        self.timestamp_ultima_resposta_gemini = time.monotonic()

        self.tarefas_chamada = []
        self.ultima_funcao_visual = None
        self.tempo_ultima_funcao_visual = 0.0

        self.monitor_tela_continuo = None

        self._buffer_transcricao_atual = ""

        self.email_pendente = None

        self.ultima_captura_caminho = None
        self.ultima_captura_timestamp = None

        rede_jarvis.iniciar_rede_jarvis(
            callback_falar=self._falar_espontaneamente,
            callback_frame_remoto=self._receber_frame_remoto,
        )

        admin_terminal.iniciar_admin_terminal(
            callback_falar=self._falar_espontaneamente,
        )

        discord_jarvis.iniciar_discord_jarvis()

    def _falar_espontaneamente(self, texto):
        if not self.loop or not self.sessao:
            return

        asyncio.run_coroutine_threadsafe(
            self._enviar_anuncio_espontaneo(texto),
            self.loop,
        )

    # Todo envio à sessão passa por aqui, nunca um await direto (CLAUDE.md).
    async def _enviar_para_sessao(self, corrotina):
        if DEBUG_TIMING_CONGELAMENTO:
            inicio_envio = time.monotonic()

        try:
            resultado = await asyncio.wait_for(
                corrotina,
                timeout=TIMEOUT_ENVIO_SESSAO_SEGUNDOS,
            )

            if DEBUG_TIMING_CONGELAMENTO:
                duracao_envio = time.monotonic() - inicio_envio

                self._debug_envio_max_desde_tick = max(
                    self._debug_envio_max_desde_tick,
                    duracao_envio,
                )
                self._debug_envio_soma_desde_tick += duracao_envio
                self._debug_envio_contagem_desde_tick += 1

            return resultado

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

    def run(self):
        try:
            asyncio.run(
                self.executar()
            )

        except Exception as erro:
            self.erro_recebido.emit(
                str(erro)
            )

        finally:
            self.nivel_audio.emit(
                0.0
            )

            self.chamada_encerrada.emit()

    async def _conectar_sessao_gemini(self, client, config, pilha):
        modelos = (
            GEMINI_LIVE_MODEL,
            GEMINI_LIVE_MODEL_FALLBACK,
        )

        ultimo_erro = None

        for indice, modelo in enumerate(modelos):
            try:
                # wait_for obrigatório; o modelo fallback só entra se a CONEXÃO falhar (docs/gemini-live-worker.md).
                sessao = await asyncio.wait_for(
                    pilha.enter_async_context(
                        client.aio.live.connect(
                            model=modelo,
                            config=config,
                        )
                    ),
                    timeout=TIMEOUT_CONEXAO_GEMINI_SEGUNDOS,
                )

            except Exception as erro:
                ultimo_erro = erro

                print(
                    f"[GEMINI] Falha ao conectar com o modelo "
                    f"'{modelo}': {str(erro) or type(erro).__name__}"
                )

                continue

            if indice > 0:
                print(
                    "[GEMINI] Modelo principal indisponível — "
                    f"conectado com o modelo alternativo '{modelo}'."
                )

            return sessao

        self.encerrou_por_falha = True

        raise ultimo_erro

    async def executar(self):
        ativacao_voz.pausar()

        if not GEMINI_API_KEY:
            raise ValueError(
                "GEMINI_API_KEY não encontrada no arquivo .env"
            )

        self.loop = asyncio.get_running_loop()

        client = genai.Client(
            api_key=GEMINI_API_KEY
        )

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
                            "conversa fica pronta para continuar de onde "
                            "parou quando o usuário chamar de novo pela "
                            "frase de ativação, em vez de terminar. Use "
                            "somente depois de perguntar se o usuário "
                            "precisa de mais alguma coisa e ele confirmar "
                            "que não precisa. Nunca use no lugar de "
                            "encerrar_chamada."
                        ),
                    ),
        ]

        function_declarations = list(function_declarations_nativas)

        for pacote in PACOTES_REGISTRADOS:
            function_declarations.extend(
                pacote.obter_function_declarations()
            )

        perfil_da_chamada = await asyncio.to_thread(
            perfis.preparar_chamada,
            self.slug_perfil,
        )

        if perfil_da_chamada["aviso"]:
            self.erro_recebido.emit(perfil_da_chamada["aviso"])

        function_declarations = perfis.filtrar_declaracoes(
            function_declarations,
            perfil_da_chamada["permitidas"],
        )

        print(
            f"[PERFIL] {self.slug_perfil}: "
            f"{len(function_declarations)} ferramentas nesta "
            "chamada."
        )

        tools = [
            types.Tool(
                function_declarations=function_declarations
            )
        ]

        memorias_atuais = await asyncio.to_thread(
            memoria_obsidian.contexto_inicial
        )

        bloco_autenticacao = (
            prompts.bloco_autenticacao()
            if EXIGIR_AUTENTICACAO
            else ""
        )

        instrucao_sistema = (
            bloco_autenticacao
            + prompts.instrucao_sistema_corpo(
                texto_bruto=perfil_da_chamada["prompt_bruto"]
            )
            + prompts.contexto_data_hora()
            + "\n\n"
            + memorias_atuais
        )

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

            output_audio_transcription=types.AudioTranscriptionConfig(),

            input_audio_transcription=types.AudioTranscriptionConfig(),

            session_resumption=types.SessionResumptionConfig(
                handle=self.session_handle
            ),

            context_window_compression=(
                types.ContextWindowCompressionConfig(
                    sliding_window=types.SlidingWindow()
                )
            ),

            tools=tools,

            system_instruction=types.Content(
                parts=[
                    types.Part(
                        text=instrucao_sistema
                    )
                ]
            ),
        )

        fila_microfone = asyncio.Queue(
            maxsize=LIMITE_FILA_MICROFONE
        )
        fila_saida = asyncio.Queue()
        self.fila_saida_atual = fila_saida

        self.status_recebido.emit(
            "Conectando ao Gemini Live..."
        )

        pilha_sessao_gemini = contextlib.AsyncExitStack()

        sessao = await self._conectar_sessao_gemini(
            client,
            config,
            pilha_sessao_gemini,
        )

        async with pilha_sessao_gemini:
            self.sessao = sessao

            self.status_recebido.emit(
                f"{obter_nome_jarvis()} conectado. Pode falar."
            )

            await asyncio.to_thread(
                winsound.Beep,
                FREQUENCIA_BEEP_CHAMADA_INICIADA,
                DURACAO_BEEP_CHAMADA_INICIADA_MS,
            )

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

            self.tarefas_chamada = tarefas

            if self.ativado_por_voz:
                texto_saudacao = prompts.SAUDACAO_ATIVACAO_POR_VOZ

                await self._enviar_para_sessao(
                    self.sessao.send_client_content(
                        turns=[
                            types.Content(
                                role="user",
                                parts=[
                                    types.Part(
                                        text=texto_saudacao
                                    )
                                ],
                            )
                        ],
                        turn_complete=True,
                    )
                )

            while self.ativo:
                await asyncio.sleep(
                    0.1
                )

            if DEBUG_TIMING_CONGELAMENTO:
                print(
                    "[TIMING-CONGELAMENTO] Encerrando: cancelando "
                    f"{len(tarefas)} tarefas e aguardando o gather..."
                )
                inicio_encerramento = time.monotonic()

            for tarefa in tarefas:
                tarefa.cancel()

            if self.tarefa_liberar_microfone:
                self.tarefa_liberar_microfone.cancel()

            if self.tarefa_encerramento:
                self.tarefa_encerramento.cancel()

            for tarefa_funcao in self.tarefas_funcao_ativas:
                tarefa_funcao.cancel()

            if (
                self.monitor_tela_continuo
                and self.monitor_tela_continuo.esta_ativo
            ):
                await self.monitor_tela_continuo.parar()
                self.monitor_tela_continuo = None

            resultados_encerramento = await asyncio.gather(
                *tarefas,
                return_exceptions=True,
            )

            if DEBUG_TIMING_CONGELAMENTO:
                duracao_encerramento = (
                    time.monotonic() - inicio_encerramento
                )

                detalhe = ", ".join(
                    f"{tarefa.get_name()}={type(resultado).__name__}"
                    for tarefa, resultado in zip(
                        tarefas, resultados_encerramento
                    )
                )

                print(
                    "[TIMING-CONGELAMENTO] Encerramento concluído em "
                    f"{duracao_encerramento:.2f}s -> {detalhe}"
                )

            self.tarefas_chamada = []

        if not self.renovacao_em_andamento:
            try:
                await asyncio.to_thread(
                    memoria_obsidian.consolidacao.salvar_resumo_conversa,
                    self.transcricao_conversa,
                )

            except Exception as erro:
                print(
                    f"[MEMORIA] Falha ao salvar o resumo da conversa: {erro}"
                )

        self.sessao = None

        if self.encerrou_por_falha:
            print(
                "[CHAMADA] A chamada terminou por falha, não por "
                "pedido do usuário. Inicie outra chamada para "
                "continuar."
            )

            self.erro_recebido.emit(
                "A chamada terminou por falha, não por pedido seu."
            )

        ativacao_voz.retomar()

    # Só checa estados impossíveis no uso normal, nunca ociosidade.
    async def vigiar_travamento(self, fila_saida):
        desde_falando = None
        desde_funcao_visual = None
        fila_saida_anterior = 0

        ja_avisou_reproducao = False

        while self.ativo:
            await asyncio.sleep(INTERVALO_VIGILANCIA_SEGUNDOS)

            if not self.ativo:
                break

            agora = time.monotonic()

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
                    self.timestamp_mic_reaberto = time.monotonic()
                    desde_falando = None
            else:
                desde_falando = None

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

            if DEBUG_TIMING_CONGELAMENTO:
                if self._debug_envio_contagem_desde_tick:
                    envio_medio = (
                        self._debug_envio_soma_desde_tick
                        / self._debug_envio_contagem_desde_tick
                    )
                else:
                    envio_medio = 0.0

                print(
                    "[TIMING-CONGELAMENTO] "
                    f"t={agora - self._debug_inicio_chamada:.0f}s "
                    "tempo desde a última resposta recebida do "
                    "Gemini (qualquer tipo) = "
                    f"{agora - self._debug_timestamp_ultima_resposta_qualquer:.1f}s "
                    "| nível máximo de microfone captado neste "
                    "intervalo = "
                    f"{self._debug_nivel_mic_maximo_desde_tick:.2f} "
                    "(0.00-1.00 — acima de ~0.15 costuma ser fala de "
                    "verdade, não só ruído de fundo) | envio pra "
                    "sessão neste intervalo: máximo="
                    f"{self._debug_envio_max_desde_tick * 1000:.0f}ms, "
                    f"médio={envio_medio * 1000:.0f}ms "
                    f"(amostras={self._debug_envio_contagem_desde_tick})"
                )

                self._debug_nivel_mic_maximo_desde_tick = 0.0
                self._debug_envio_max_desde_tick = 0.0
                self._debug_envio_soma_desde_tick = 0.0
                self._debug_envio_contagem_desde_tick = 0

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

    def _reportar_travamento(self, descricao):
        print(f"[VIGIA] Travamento detectado: {descricao}")

        self.erro_recebido.emit(
            f"Problema detectado na chamada: {descricao}"
        )

    async def _tarefa_supervisionada(self, nome, corrotina):
        try:
            await corrotina

        except Exception as erro:
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

    async def enviar_microfone(
        self,
        sessao,
        fila_microfone,
    ):
        loop = asyncio.get_running_loop()

        def callback(
            indata,
            frames,
            time_info,
            status,
        ):
            # Primeira linha do callback, antes de qualquer return: é o que vigiar_travamento mede.
            self.timestamp_ultimo_bloco_microfone = time.monotonic()

            if DEBUG_TIMING_CONGELAMENTO:
                nivel_mic = self.calcular_nivel_audio(
                    bytes(indata)
                )

                self._debug_nivel_mic_maximo_desde_tick = max(
                    self._debug_nivel_mic_maximo_desde_tick,
                    nivel_mic,
                )

            if not self.ativo:
                return

            # Manter 'and not self.interrupcao_habilitada' nas 3 checagens (docs/gemini-live-worker.md).
            if (
                self.alfred_falando
                and not self.interrupcao_habilitada
            ):
                return

            if status:
                print(
                    "Aviso microfone:",
                    status,
                )

            audio_bytes = bytes(
                indata
            )

            def adicionar_audio():
                if not self.ativo:
                    return

                # Manter 'and not self.interrupcao_habilitada' nas 3 checagens (docs/gemini-live-worker.md).
                if (
                    self.alfred_falando
                    and not self.interrupcao_habilitada
                ):
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

        # O try em volta é obrigatório: falha no microfone não pode morrer em silêncio.
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
                    audio_bytes = await fila_microfone.get()

                    # Manter 'and not self.interrupcao_habilitada' nas 3 checagens (docs/gemini-live-worker.md).
                    if (
                        self.alfred_falando
                        and not self.interrupcao_habilitada
                    ):
                        continue

                    # Barras de escuta: só com o ALFRED calado, senão os dois níveis brigam no sinal.
                    if not self.alfred_falando:
                        self.nivel_audio.emit(
                            self.calcular_nivel_audio(audio_bytes)
                        )

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

    async def receber_audio(
        self,
        sessao,
        fila_saida,
        fila_microfone,
    ):
        while self.ativo:
            recebeu_algo = False

            async for resposta in sessao.receive():
                recebeu_algo = True

                if DEBUG_TIMING_CONGELAMENTO:
                    self._debug_timestamp_ultima_resposta_qualquer = (
                        time.monotonic()
                    )

                self.timestamp_ultima_resposta_gemini = time.monotonic()

                if not self.ativo:
                    break

                if (
                    self.interrupcao_habilitada
                    and resposta.server_content
                    and resposta.server_content.interrupted
                ):
                    if self.tarefa_liberar_microfone:
                        self.tarefa_liberar_microfone.cancel()
                        self.tarefa_liberar_microfone = None

                    self.interrupcoes_na_chamada += 1
                    descartados = fila_saida.qsize()

                    self.limpar_fila_saida(
                        fila_saida
                    )

                    if DEBUG_TIMING_FILA_SAIDA:
                        self._debug_fila_timestamps.clear()

                    print(
                        "[INTERRUPÇÃO] O servidor sinalizou que o "
                        "usuário falou por cima — fala cortada "
                        f"(nº {self.interrupcoes_na_chamada} nesta "
                        f"chamada, {descartados} blocos descartados)."
                    )

                    self.alfred_falando = False
                    self.timestamp_mic_reaberto = time.monotonic()

                if resposta.data:
                    self.timestamp_ultima_geracao_gemini = time.monotonic()

                    # Descarta o turno inteiro: alfred_falando, fila_saida e limpeza do microfone juntos.
                    if not self.silenciar_audio_ate_fim_turno:
                        self.timestamp_ultima_atividade = time.monotonic()

                        if DEBUG_TIMING_MICROFONE and not self.alfred_falando:
                            self._debug_inicio_mudo = time.perf_counter()
                            print(
                                "[TIMING-MIC] Microfone silenciado "
                                "(receber_audio: chegou áudio novo)."
                            )

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

                # Vira task supervisionada: nunca await direto de processar_chamada_de_funcao.
                if resposta.tool_call:
                    self.timestamp_ultima_geracao_gemini = time.monotonic()

                    self.timestamp_ultima_atividade = time.monotonic()

                    # Checagem síncrona antes de criar a task; acima do limite, recusa RESPONDENDO o call_id.
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

                # Cancelada = o servidor descarta a resposta; sem isto o modelo inventa o resultado.
                cancelamento = getattr(resposta, "tool_call_cancellation", None)

                if cancelamento and cancelamento.ids:
                    self._registrar_cancelamento(cancelamento.ids)

                atualizacao_sessao = getattr(
                    resposta,
                    "session_resumption_update",
                    None,
                )

                if atualizacao_sessao and getattr(
                    atualizacao_sessao,
                    "resumable",
                    False,
                ):
                    novo_handle = getattr(
                        atualizacao_sessao,
                        "new_handle",
                        None,
                    )

                    if novo_handle:
                        self.session_handle = novo_handle
                        self.session_handle_atualizado.emit(
                            novo_handle
                        )

                        if (
                            self.fase_pausa == "aguardando_handle"
                            and self.pausa_registrada is not None
                        ):
                            self.pausa_registrada.set()

                # go_away é renovação de rotina: nunca marcar encerrou_por_falha.
                aviso_encerramento = getattr(resposta, "go_away", None)

                if (
                    aviso_encerramento is not None
                    and not self.renovacao_em_andamento
                ):
                    self.renovacao_em_andamento = True

                    self.limpar_fila_microfone(
                        fila_microfone
                    )

                    print(
                        "[CONEXÃO] O servidor pediu renovação da "
                        "conexão (go_away). Reabrindo sem perder a "
                        "conversa."
                    )

                    self.status_recebido.emit(
                        "Servidor solicitou a renovação da conexão. "
                        "Preservando a conversa..."
                    )

                    self.solicitou_reconexao.emit()

                    self.ativo = False
                    return

                conteudo = resposta.server_content

                if (
                    conteudo
                    and conteudo.output_transcription
                ):
                    texto_transcrito = (
                        conteudo.output_transcription.text
                    )

                    if texto_transcrito:
                        self._buffer_transcricao_atual += (
                            texto_transcrito
                        )

                if conteudo and conteudo.input_transcription:
                    texto_usuario_transcrito = (
                        conteudo.input_transcription.text
                    )

                    if texto_usuario_transcrito:
                        self._buffer_transcricao_usuario += (
                            texto_usuario_transcrito
                        )

                if conteudo and conteudo.turn_complete:
                    self.silenciar_audio_ate_fim_turno = False

                    if (
                        self.voltar_status_ouvindo
                        and not self.tarefas_funcao_ativas
                        and not self.hibernacao_solicitada
                        and self.tarefa_encerramento is None
                    ):
                        self.voltar_status_ouvindo = False

                        self.status_recebido.emit(
                            f"{obter_nome_jarvis()} está ouvindo."
                        )

                    if self.fase_pausa == "aguardando_turno":
                        self.fase_pausa = "aguardando_handle"

                    if self._buffer_transcricao_atual:
                        obter_sinalizador().resposta_texto_recebida.emit(
                            self._buffer_transcricao_atual
                        )

                    if self._buffer_transcricao_usuario:
                        self.transcricao_conversa.append(
                            {
                                "role": "user",
                                "content": self._buffer_transcricao_usuario,
                            }
                        )

                        self._buffer_transcricao_usuario = ""

                    if self._buffer_transcricao_atual:
                        self.transcricao_conversa.append(
                            {
                                "role": "assistant",
                                "content": self._buffer_transcricao_atual,
                            }
                        )

                        self._buffer_transcricao_atual = ""

                    excesso = (
                        len(self.transcricao_conversa)
                        - MAXIMO_MENSAGENS_TRANSCRICAO
                    )

                    if excesso > 0:
                        self.transcricao_conversa = (
                            self.transcricao_conversa[excesso:]
                        )

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

        async with self._mutex_funcao_visual() as mutex_livre:
            if not mutex_livre:
                return (
                    None,
                    False,
                    "Já existe uma captura de tela/câmera em "
                    "andamento — tente de novo em instantes.",
                )

            if tipo_captura == "foto":
                imagem_bytes = await asyncio.to_thread(
                    capturar_camera_bytes
                )

                caminho_salvo = await asyncio.to_thread(
                    salvar_foto_bytes,
                    imagem_bytes,
                )
            else:
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

    def _ao_finalizar_tarefa_funcao(self, tarefa):
        if tarefa in self.tarefas_funcao_ativas:
            self.tarefas_funcao_ativas.remove(tarefa)

        if tarefa.cancelled():
            return

        erro = tarefa.exception()

        if erro is not None:
            print(
                "[FUNÇÃO] Exceção não tratada numa tarefa de função: "
                f"{erro!r}"
            )

    async def _executar_chamada_de_funcao_com_timeout(
        self,
        sessao,
        tool_call,
    ):
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

        self._agendar_aviso_de_demora(
            tarefa_execucao,
            tool_call,
        )

        try:
            function_responses, encerrar_depois = await asyncio.wait_for(
                asyncio.shield(tarefa_execucao),
                timeout=min(
                    LIMITE_RESPOSTA_IMEDIATA_SEGUNDOS,
                    timeout,
                ),
            )

        except asyncio.TimeoutError:
            await self._responder_falha_para_lote(
                sessao,
                tool_call,
                lambda nome: (
                    f"A ação '{nome}' ainda está em andamento — é "
                    "mais demorada que o normal. Diga ao usuário, de "
                    "forma breve e natural, que você já começou e "
                    "vai avisar assim que terminar. NÃO espere em "
                    "silêncio — continue a conversa normalmente com "
                    "o usuário enquanto isso roda em segundo plano. "
                    "Não descreva nem adiante o resultado antes de "
                    "ele chegar."
                ),
            )

        except Exception as erro:
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
            # Fica no else do try: dentro dele, timeout do envio pareceria timeout da função.
            await self._enviar_resposta_funcao(
                sessao,
                function_responses,
                encerrar_depois,
            )
            return

        tempo_restante = max(
            timeout - LIMITE_RESPOSTA_IMEDIATA_SEGUNDOS,
            1,
        )

        try:
            function_responses, encerrar_depois = await asyncio.wait_for(
                tarefa_execucao,
                timeout=tempo_restante,
            )

            for resposta in function_responses:
                self.chamadas_canceladas.discard(resposta.id)

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

    def _agendar_aviso_de_demora(
        self,
        tarefa_execucao,
        tool_call,
    ):
        nome = aviso_ferramenta.ferramenta_do_aviso(
            (
                (chamada.name, chamada.args)
                for chamada in tool_call.function_calls
            ),
            TOOLS_SILENCIOSAS,
        )

        if not nome or self.fila_saida_atual is None:
            return

        tarefa = asyncio.create_task(
            self._tocar_aviso_de_demora(
                tarefa_execucao,
                nome,
            )
        )

        self.tarefas_aviso.add(tarefa)
        tarefa.add_done_callback(self.tarefas_aviso.discard)

    async def _tocar_aviso_de_demora(
        self,
        tarefa_execucao,
        nome,
    ):
        await asyncio.wait(
            {tarefa_execucao},
            timeout=aviso_ferramenta.LIMITE_SEGUNDOS,
        )

        if tarefa_execucao.done() or not self.ativo:
            return

        pcm = aviso_ferramenta.pcm_do_aviso(nome)

        if not pcm:
            print(
                f"[FERRAMENTA] '{nome}' está demorando, mas não há áudio "
                "de aviso gerado para ela (python -m "
                "jarvis.cerebro.gemini.gerador_avisos)."
            )

            return

        print(
            f"[FERRAMENTA] '{nome}' passou de "
            f"{aviso_ferramenta.LIMITE_SEGUNDOS:.1f}s — tocando o aviso "
            "de execução."
        )

        self.timestamp_ultima_atividade = time.monotonic()

        for inicio in range(0, len(pcm), TAMANHO_BLOCO_AVISO):
            await self.fila_saida_atual.put(
                pcm[inicio:inicio + TAMANHO_BLOCO_AVISO]
            )

    def _registrar_cancelamento(
        self,
        ids,
    ):
        ids = set(ids)

        ja_respondidas = [
            resposta
            for resposta in self.respostas_recentes
            if resposta.id in ids
        ]

        self.chamadas_canceladas.update(
            ids - {resposta.id for resposta in ja_respondidas}
        )

        print(
            f"[FERRAMENTA] O servidor cancelou {len(ids)} chamada(s) "
            "porque o usuário falou por cima — o resultado real será "
            "entregue ao modelo assim que estiver pronto."
        )

        if ja_respondidas:
            tarefa = asyncio.create_task(
                self._entregar_resultados_interrompidos(ja_respondidas)
            )

            self.tarefas_funcao_ativas.append(tarefa)
            tarefa.add_done_callback(self._ao_finalizar_tarefa_funcao)

    async def _entregar_resultados_interrompidos(
        self,
        respostas,
    ):
        partes = []

        for resposta in respostas:
            print(
                f"[FERRAMENTA] Entregando o resultado de '{resposta.name}', "
                "que o servidor tinha cancelado."
            )

            partes.append(
                types.Part(
                    text=prompts.RESULTADO_CHAMADA_INTERROMPIDA.format(
                        nome=resposta.name,
                        resultado=(resposta.response or {}).get("result", ""),
                    )
                )
            )

            for parte in resposta.parts or []:
                blob = parte.inline_data
                dados = getattr(blob, "data", None)

                if not dados:
                    continue

                partes.append(
                    types.Part(
                        inline_data=types.Blob(
                            data=(
                                base64.b64decode(dados)
                                if isinstance(dados, str)
                                else dados
                            ),
                            mime_type=blob.mime_type or "image/jpeg",
                        )
                    )
                )

        if not partes or not self.sessao:
            return

        await self._enviar_para_sessao(
            self.sessao.send_client_content(
                turns=[
                    types.Content(
                        role="user",
                        parts=partes,
                    )
                ],
                turn_complete=True,
            )
        )

    async def _enviar_respostas(
        self,
        sessao,
        respostas,
    ):
        pendentes = []
        interrompidas = []

        for resposta in respostas:
            if resposta.id in self.chamadas_canceladas:
                self.chamadas_canceladas.discard(resposta.id)
                interrompidas.append(resposta)

            else:
                pendentes.append(resposta)

        if pendentes:
            await self._enviar_para_sessao(
                sessao.send_tool_response(
                    function_responses=pendentes
                )
            )

            self.respostas_recentes.extend(pendentes)

        if interrompidas:
            await self._entregar_resultados_interrompidos(interrompidas)

    async def _enviar_resposta_funcao(
        self,
        sessao,
        function_responses,
        encerrar_depois,
    ):
        if function_responses:
            await self._enviar_respostas(
                sessao,
                function_responses,
            )

        if encerrar_depois:
            if self.tarefa_encerramento:
                self.tarefa_encerramento.cancel()

            self.tarefa_encerramento = asyncio.create_task(
                self.encerrar_apos_resposta()
            )

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
            await self._enviar_respostas(
                sessao,
                respostas,
            )

    async def processar_chamada_de_funcao(
        self,
        tool_call,
    ):
        function_responses = []
        encerrar_depois = False

        self.voltar_status_ouvindo = True

        for chamada in tool_call.function_calls:
            nome = chamada.name
            args = dict(
                chamada.args or {}
            )

            nome_exibido = (
                str(args.get("nome") or nome)
                if nome == "executar_ferramenta"
                else nome
            )

            rastrear = nome != "ler_instrucao_ferramenta"

            if rastrear:
                print(f"[FERRAMENTA] Executando '{nome_exibido}'.")

                self.status_recebido.emit(
                    f"Executando a ferramenta {nome_exibido}..."
                )

            if DEBUG_TIMING_DISPATCH:
                inicio_chamada = time.perf_counter()

            resultado_pacote = None
            imagem_resposta = None

            if nome in TOOLS_QUE_PRECISAM_DE_IMAGEM:
                origem_imagem = TOOLS_QUE_PRECISAM_DE_IMAGEM[nome]

                async with self._mutex_funcao_visual() as mutex_livre:
                    if not mutex_livre:
                        resultado_pacote = (
                            "Já existe uma captura de tela/câmera em "
                            "andamento — tente de novo em instantes."
                        )

                    else:
                        self.status_recebido.emit(
                            "Capturando imagem da tela..."
                            if origem_imagem == "tela"
                            else "Capturando imagem da câmera..."
                        )

                        captura = (
                            capturar_monitor_do_cursor_bytes
                            if origem_imagem == "tela"
                            else capturar_camera_bytes
                        )

                        args["imagem_bytes"] = await asyncio.to_thread(
                            captura
                        )

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

            if nome in TOOLS_SILENCIOSAS:
                self.silenciar_audio_ate_fim_turno = True

            despachar_para_pacotes = resultado_pacote is None

            async with contextlib.AsyncExitStack() as pilha_visual:
                if (
                    despachar_para_pacotes
                    and nome in TOOLS_QUE_CAPTURAM_SOZINHAS
                ):
                    mutex_livre = (
                        await pilha_visual.enter_async_context(
                            self._mutex_funcao_visual()
                        )
                    )

                    if not mutex_livre:
                        resultado_pacote = (
                            "Já existe uma captura de tela/câmera em "
                            "andamento — tente de novo em instantes."
                        )

                        despachar_para_pacotes = False

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
                resultado, imagem_resposta = await self.processar_funcao_visual(
                    nome
                )

            elif nome == "salvar_print_tela":
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

                        imagem_bytes = await asyncio.to_thread(
                            capturar_monitor_do_cursor_bytes
                        )

                        caminho_salvo = await asyncio.to_thread(
                            salvar_print_bytes,
                            imagem_bytes,
                        )

                        self.ultima_captura_caminho = caminho_salvo
                        self.ultima_captura_timestamp = time.monotonic()

                        resultado = f"Print da tela salvo em: {caminho_salvo}"

            elif nome == "tirar_foto_camera":
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

                        imagem_bytes = await asyncio.to_thread(
                            capturar_camera_bytes
                        )

                        caminho_salvo = await asyncio.to_thread(
                            salvar_foto_bytes,
                            imagem_bytes,
                        )

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

            elif nome == "encerrar_chamada":
                self.status_recebido.emit(
                    "Encerrando chamada por comando de voz..."
                )

                resultado = (
                    "Solicitação de encerramento recebida. "
                    "Diga de forma curta que a chamada será encerrada."
                )

                encerrar_depois = True

            elif nome == "pausar_chamada":
                self.status_recebido.emit(
                    "Chamada pausada — diga a frase de ativação para "
                    "continuar..."
                )

                self.hibernacao_solicitada = True

                resultado = (
                    "Chamada pausada. Diga ao usuário, de forma breve "
                    "e natural, que para falar com você de novo é só "
                    f"dizer '{NOME_ATIVACAO}'."
                )

                encerrar_depois = True

            else:
                resultado = (
                    "Função desconhecida. Nenhuma ação foi executada."
                )

            if DEBUG_TIMING_DISPATCH:
                duracao_chamada_ms = (
                    time.perf_counter() - inicio_chamada
                ) * 1000

                print(
                    f"[TIMING] '{nome}' processada em "
                    f"{duracao_chamada_ms:.1f}ms no total"
                )

            if rastrear:
                resumo = " ".join(str(resultado).split())

                print(
                    f"[FERRAMENTA] '{nome_exibido}' terminou: "
                    f"{resumo[:140]}"
                )

            function_responses.append(
                types.FunctionResponse(
                    id=chamada.id,
                    name=nome,
                    response={
                        "result": resultado
                    },
                    parts=_partes_imagem_resposta(imagem_resposta),
                )
            )

        return function_responses, encerrar_depois

    async def encerrar_apos_resposta(self):
        try:
            if self.hibernacao_solicitada:
                await self._aguardar_pausa_registrada()

            else:
                await asyncio.sleep(
                    2.8
                )

            if self.ativo:
                if self.hibernacao_solicitada:
                    self.hibernacao_solicitada = False

                    self.solicitou_hibernacao.emit()

                else:
                    self.solicitou_encerramento.emit()

        except asyncio.CancelledError:
            pass

    async def _aguardar_pausa_registrada(self):
        self.pausa_registrada = asyncio.Event()
        self.fase_pausa = "aguardando_turno"

        try:
            await asyncio.wait_for(
                self.pausa_registrada.wait(),
                timeout=LIMITE_ESPERA_PAUSA_SEGUNDOS,
            )

        except asyncio.TimeoutError:
            print(
                "[PAUSA] O servidor não confirmou a despedida em "
                f"{LIMITE_ESPERA_PAUSA_SEGUNDOS}s; pausando mesmo assim "
                "(a retomada pode repetir a despedida)."
            )

        finally:
            self.fase_pausa = None
            self.pausa_registrada = None

        limite = time.monotonic() + LIMITE_DESPEDIDA_TOCANDO_SEGUNDOS

        while self.alfred_falando and time.monotonic() < limite:
            await asyncio.sleep(
                0.1
            )

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

                await self._enviar_anuncio_espontaneo(
                    "que a chamada vai ser encerrada agora por "
                    "causa de um tempo sem atividade"
                )

                if self.tarefa_encerramento:
                    self.tarefa_encerramento.cancel()

                self.tarefa_encerramento = asyncio.create_task(
                    self.encerrar_apos_resposta()
                )

                break

        except asyncio.CancelledError:
            pass

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

    async def processar_funcao_visual(
        self,
        nome,
        origem="voz",
    ):
        self.voltar_status_ouvindo = True

        if self.executando_funcao_visual:
            return (
                "Uma análise visual já está em andamento. "
                "Use a última imagem recebida e responda ao usuário."
            ), None

        agora = time.monotonic()

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
            ), None

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

                if origem == "voz":
                    return prompts.ANALISE_IMAGEM_PONTUAL.format(
                        origem="tela"
                    ), await asyncio.to_thread(
                        capturar_monitor_do_cursor_bytes
                    )

                await self.enviar_tela_para_gemini(
                    origem="voz"
                )

                return (
                    "A tela foi capturada e enviada. "
                    "Responda usando exatamente a última imagem recebida."
                ), None

            if nome == "analisar_camera":
                self.status_recebido.emit(
                    "Comando de voz detectado: analisar câmera."
                    if origem == "voz"
                    else "Botão pressionado: analisar câmera."
                )

                if origem == "voz":
                    return prompts.ANALISE_IMAGEM_PONTUAL.format(
                        origem="câmera"
                    ), await asyncio.to_thread(
                        capturar_camera_bytes
                    )

                await self.enviar_camera_para_gemini(
                    origem="voz"
                )

                return (
                    "A câmera foi capturada e enviada. "
                    "Responda usando exatamente a última imagem recebida."
                ), None

            return "Função visual desconhecida.", None

        finally:
            self.executando_funcao_visual = False

    @contextlib.asynccontextmanager
    # Toda captura de tela/câmera fora de processar_funcao_visual passa por este mutex.
    async def _mutex_funcao_visual(self):
        if self.executando_funcao_visual:
            yield False
            return

        self.executando_funcao_visual = True

        try:
            yield True

        finally:
            self.executando_funcao_visual = False

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

    async def _visualizacao_continua_encerrada_por_timeout(
        self,
    ):
        self.monitor_tela_continuo = None

        self.status_recebido.emit(
            "Visualização contínua encerrada automaticamente "
            "por tempo limite."
        )

    async def iniciar_visualizacao_continua(
        self,
    ):
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
            funcao_captura=capturar_monitor_do_cursor_bytes,
        )

        await self.monitor_tela_continuo.iniciar()

        return (
            "Visualização contínua da tela iniciada. Continue "
            "ouvindo o usuário normalmente enquanto ele mostra "
            "o que precisa, sem chamar esta função novamente."
        )

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

    async def reproduzir_audio(
        self,
        fila_saida,
        fila_microfone,
    ):
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
        with sd.RawOutputStream(
            samplerate=TAXA_SAIDA,
            blocksize=BLOCO,
            dtype="int16",
            channels=CANAIS,
            latency=LATENCIA_SAIDA,
        ) as saida:
            while self.ativo:
                audio_bytes = await fila_saida.get()

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

                nivel = self.calcular_nivel_audio(
                    audio_bytes
                )

                self.nivel_audio.emit(
                    nivel
                )

                # Sem asyncio.sleep neste laço; o write fica em wait_for + executor dedicado (docs/gemini-live-worker.md).
                await asyncio.wait_for(
                    laco.run_in_executor(
                        executor_audio,
                        saida.write,
                        audio_bytes,
                    ),
                    timeout=TIMEOUT_ESCRITA_AUDIO_SEGUNDOS,
                )

                self.timestamp_ultima_reproducao = time.monotonic()

                if self.tarefa_liberar_microfone:
                    self.tarefa_liberar_microfone.cancel()

                self.tarefa_liberar_microfone = asyncio.create_task(
                    self.liberar_microfone_apos_fala()
                )

    @staticmethod
    def limpar_fila_microfone(
        fila_microfone,
    ):
        while True:
            try:
                fila_microfone.get_nowait()

            except asyncio.QueueEmpty:
                break

    @staticmethod
    def limpar_fila_saida(
        fila_saida,
    ):
        while True:
            try:
                fila_saida.get_nowait()

            except asyncio.QueueEmpty:
                break

    @staticmethod
    def calcular_nivel_audio(
        audio_bytes,
    ):
        if not audio_bytes:
            return 0.0

        try:
            amostras = array(
                "h",
                audio_bytes,
            )

            if not amostras:
                return 0.0

            pico = max(
                abs(amostra)
                for amostra in amostras
            )

            nivel = pico / 32768.0
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

    async def liberar_microfone_apos_fala(
        self,
    ):
        try:
            await asyncio.sleep(
                ATRASO_REABRIR_MICROFONE
            )

            self.alfred_falando = False
            self.timestamp_mic_reaberto = time.monotonic()

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

    def solicitar_analise_tela(
        self,
    ):
        if not self.loop or not self.sessao:
            self.erro_recebido.emit(
                "Sessão Gemini ainda não está pronta."
            )

            return

        asyncio.run_coroutine_threadsafe(
            self.processar_funcao_visual(
                "analisar_tela",
                origem="botão",
            ),
            self.loop,
        )

    async def enviar_tela_para_gemini(
        self,
        origem="botao",
    ):
        try:
            self.status_recebido.emit(
                "Capturando tela..."
            )

            imagem_bytes = await asyncio.to_thread(
                capturar_monitor_do_cursor_bytes
            )

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

    def solicitar_analise_camera(
        self,
    ):
        if not self.loop or not self.sessao:
            self.erro_recebido.emit(
                "Sessão Gemini ainda não está pronta."
            )

            return

        asyncio.run_coroutine_threadsafe(
            self.processar_funcao_visual(
                "analisar_camera",
                origem="botão",
            ),
            self.loop,
        )

    async def enviar_camera_para_gemini(
        self,
        origem="botao",
    ):
        try:
            self.status_recebido.emit(
                "Capturando imagem da câmera..."
            )

            imagem_bytes = await asyncio.to_thread(
                capturar_camera_bytes
            )

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

    def parar(self):
        self.ativo = False

        self.nivel_audio.emit(
            0.0
        )
