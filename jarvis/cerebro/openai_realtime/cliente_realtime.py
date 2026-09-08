"""
Worker equivalente a jarvis/cerebro/gemini/cliente_live.py, usando a Realtime
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
    obter_nome_jarvis,
)

from jarvis.nucleo import perfis
from jarvis.nucleo import prompts
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

# Frase de ativação por voz atual — usada pela tool pausar_chamada,
# mesmo motivo e mesma convenção de jarvis/cerebro/gemini/cliente_live.py.
from jarvis.pacotes.ativacao_voz.config import NOME_ATIVACAO
from jarvis.pacotes import admin_terminal
from jarvis.pacotes import discord_jarvis
from jarvis.pacotes import memoria_obsidian
from jarvis.pacotes import rede_jarvis

from jarvis.cerebro.openai_realtime import esquema


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
# jarvis/cerebro/gemini/cliente_live.py.
TIMEOUTS_FUNCAO_POR_NOME = {
    "executar_comando_admin": (
        admin_terminal.config.TIMEOUT_COMANDO_LONGO_SEGUNDOS + 30
    ),
    "confirmar_comando_admin": (
        admin_terminal.config.TIMEOUT_COMANDO_LONGO_SEGUNDOS + 30
    ),
}

# Tempo máximo, em segundos, que QUALQUER envio para a sessão da
# Realtime API pode esperar antes de ser considerado travado. Mesma
# constante, mesmo valor e mesmo motivo de TIMEOUT_ENVIO_SESSAO_SEGUNDOS
# em jarvis/cerebro/gemini/cliente_live.py — mas aqui o risco é PIOR,
# porque todos os envios deste worker passam por self.lock_envio: um
# envio pendurado nunca devolve a trava, e aí TODA chamada de função
# seguinte fica esperando para sempre para responder o próprio
# function_call_output. Como o protocolo não deixa o modelo voltar a
# falar sem essa resposta, a chamada fica viva e muda ao mesmo tempo,
# e as três tarefas centrais continuam sem levantar nada — ou seja, a
# supervisão de executar() não vê problema nenhum. Ver
# _enviar_para_sessao/self.conexao_travada.
TIMEOUT_ENVIO_SESSAO_SEGUNDOS = 10

# Quantas chamadas de função podem rodar ao mesmo tempo. Mesma
# constante e mesmo motivo de LIMITE_TAREFAS_FUNCAO_SIMULTANEAS em
# jarvis/cerebro/gemini/cliente_live.py: cada chamada vira sua própria
# asyncio.Task para não bloquear o laço de recepção, e o limite existe
# só para a lista não crescer sem controle se o modelo pedir muitas
# funções rápido demais. Ver receber_eventos/_ao_finalizar_tarefa_funcao.
LIMITE_TAREFAS_FUNCAO_SIMULTANEAS = 4

# Espera antes de encerrar de fato depois de encerrar_chamada, para a
# despedida terminar de tocar.
ATRASO_ENCERRAMENTO_SEGUNDOS = 2.8

# Quantas mensagens do transcript da conversa ficam guardadas — mesmo
# valor e mesmo motivo da constante de mesmo nome em
# jarvis/cerebro/gemini/cliente_live.py.
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

    # O usuário pediu pra pausar a chamada por voz (tool
    # pausar_chamada) — mesmo contrato do GeminiLiveWorker: a janela
    # preserva session_handle/transcricao_preservada (aqui o handle
    # nunca é usado de fato, ver acima, mas a transcrição sim) e só
    # reconecta quando ativacao_voz detectar a frase de novo.
    solicitou_hibernacao = Signal()

    # Mesma assinatura do GeminiLiveWorker. session_handle e
    # transcricao_inicial são aceitos para a janela poder criar
    # qualquer um dos dois workers do mesmo jeito; o handle é ignorado
    # (ver acima), a transcrição não. ativado_por_voz: mesmo motivo do
    # GeminiLiveWorker — True só quando esta chamada veio da detecção
    # da frase de ativação, controla a saudação logo após conectar.
    def __init__(
        self,
        session_handle=None,
        transcricao_inicial=None,
        ativado_por_voz=False,
        slug_perfil=None,
    ):
        super().__init__()

        self.ativo = True

        # Perfil que vale para ESTA chamada — prompt de sistema e
        # subconjunto de ferramentas. Resolvido AGORA, na construção
        # do worker (que acontece no clique de INICIAR CHAMADA), e
        # nunca relido depois: é isso que garante que trocar de perfil
        # na tela não mexe numa chamada já em andamento. Mesma regra e
        # mesma linha do GeminiLiveWorker.
        self.slug_perfil = slug_perfil or perfis.perfil_ativo()
        self.loop = None
        self.conexao = None
        self.session_handle = session_handle
        self.ativado_por_voz = ativado_por_voz
        self.hibernacao_solicitada = False

        # Trava de envio: vários pontos podem escrever na conexão
        # (microfone, resposta de ferramenta, imagem avulsa) e a
        # Realtime API não gosta de escritas concorrentes.
        self.lock_envio = None

        # Ligado por _enviar_para_sessao quando um envio estoura o
        # timeout ou falha. O laço de supervisão de executar() checa
        # essa flag a cada volta e encerra a chamada, em vez de
        # deixá-la viva e muda. Mesma ideia do self.conexao_travada +
        # monitorar_conexao do GeminiLiveWorker, aproveitando o laço
        # que já existe aqui em vez de criar uma tarefa nova só para
        # isso.
        self.conexao_travada = False

        # Chamadas de função em andamento. Guardar a referência é
        # OBRIGATÓRIO, não organização: o asyncio só mantém referência
        # FRACA a uma task rodando, então uma task criada e esquecida
        # pode ser coletada pelo garbage collector no meio da execução
        # — e aí o function_call_output daquele call_id nunca é
        # enviado, e o modelo fica esperando por ele para sempre. Ver
        # receber_eventos/_ao_finalizar_tarefa_funcao.
        self.tarefas_funcao_ativas = []

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
