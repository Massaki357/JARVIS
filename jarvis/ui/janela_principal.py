from PySide6.QtCore import Qt, QTimer

from PySide6.QtGui import QFont

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from jarvis.cerebro.gemini.cliente_live import GeminiLiveWorker

from jarvis.nucleo.config import provedor_ativo

from jarvis.nucleo.sinalizador import obter_sinalizador

from jarvis.ui.painel_console import PainelConsole

from jarvis.ui.painel_dispositivos import PainelDispositivos

from jarvis.ui.painel_provedor import PainelProvedor

from jarvis.ui.painel_nome import PainelNome

from jarvis.nucleo.config import obter_nome_jarvis

from jarvis.ui.painel_chat_sobreposto import PainelChatSobreposto
from jarvis.ui.visualizador_alfred import VisualizadorAlfred

from jarvis.ui.estilo import ESTILO_GLOBAL


# Único lugar que escolhe o cérebro de voz (CLAUDE.md).
def _classe_do_worker():
    provedor = provedor_ativo()

    if provedor == "openai":
        from jarvis.cerebro.openai_realtime import OpenAIRealtimeWorker

        return OpenAIRealtimeWorker

    if provedor == "local":
        from jarvis.cerebro.voz_local import VozLocalWorker

        return VozLocalWorker

    return GeminiLiveWorker


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle(
            obter_nome_jarvis()
        )

        self.setMinimumSize(
            1180,
            560,
        )

        self.resize(
            1380,
            760,
        )

        self.live_worker = None

        self.session_handle = None

        self.transcricao_preservada = []

        self.slug_perfil_chamada = None

        self.reconectar_automaticamente = False
        self.encerramento_manual = False

        self.hibernando_por_voz = False

        self.ativado_por_voz = False

        self.setStyleSheet(
            ESTILO_GLOBAL
        )

        self._criar_interface()

        self.painel_console.capturar_saida_padrao()

        self.painel_console.acrescentar(
            "Console pronto. Interrupções de fala, avisos e erros "
            "aparecem aqui.",
            "info",
        )

    def _criar_interface(self):
        container = QWidget()

        layout_raiz = QHBoxLayout(
            container
        )

        layout_raiz.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        layout_raiz.setSpacing(
            0
        )

        coluna_controles = QWidget()
        coluna_controles.setFixedWidth(
            330
        )

        layout = QVBoxLayout(
            coluna_controles
        )

        layout.setContentsMargins(
            30,
            25,
            30,
            25,
        )

        layout.setSpacing(
            12
        )

        self.titulo_label = QLabel(
            obter_nome_jarvis()
        )

        self.titulo_label.setObjectName(
            "titulo"
        )

        self.titulo_label.setAlignment(
            Qt.AlignCenter
        )

        fonte_titulo = self.titulo_label.font()

        fonte_titulo.setLetterSpacing(
            QFont.SpacingType.AbsoluteSpacing,
            2,
        )

        self.titulo_label.setFont(
            fonte_titulo
        )

        subtitulo = QLabel(
            "Assistente de Inteligência Artificial"
        )

        subtitulo.setObjectName(
            "subtitulo"
        )

        subtitulo.setAlignment(
            Qt.AlignCenter
        )

        status_titulo = QLabel(
            "Status"
        )

        status_titulo.setObjectName(
            "statusTitulo"
        )

        status_titulo.setAlignment(
            Qt.AlignCenter
        )

        self.status_valor = QLabel(
            "OFFLINE"
        )

        self.status_valor.setObjectName(
            "statusValor"
        )

        self.status_valor.setAlignment(
            Qt.AlignCenter
        )

        self.btn_chamada = QPushButton(
            "INICIAR CHAMADA"
        )

        self.btn_chamada.setObjectName(
            "botaoChamada"
        )

        layout_visao = QHBoxLayout()

        layout_visao.setSpacing(
            10
        )

        self.btn_tela = QPushButton(
            "ANALISAR TELA"
        )

        self.btn_camera = QPushButton(
            "ANALISAR CÂMERA"
        )

        self.btn_tela.setObjectName(
            "botaoVisao"
        )

        self.btn_camera.setObjectName(
            "botaoVisao"
        )

        layout_visao.addWidget(
            self.btn_tela
        )

        layout_visao.addWidget(
            self.btn_camera
        )

        registro_titulo = QLabel(
            "Registro de atividade"
        )

        registro_titulo.setObjectName(
            "statusTitulo"
        )

        self.log_box = QTextEdit()

        self.log_box.setObjectName(
            "registro"
        )

        self.log_box.setReadOnly(
            True
        )

        self.log_box.setPlaceholderText(
            "Aguardando eventos..."
        )

        layout.addWidget(
            self.titulo_label
        )

        layout.addWidget(
            subtitulo
        )

        layout.addSpacing(
            8
        )

        layout.addWidget(
            status_titulo
        )

        layout.addWidget(
            self.status_valor
        )

        layout.addSpacing(
            6
        )

        layout.addWidget(
            self.btn_chamada
        )

        layout.addLayout(
            layout_visao
        )

        layout_extras = QHBoxLayout()

        layout_extras.setSpacing(
            10
        )

        self.btn_configuracoes = QPushButton(
            "CONFIGURAÇÕES"
        )

        self.btn_chat = QPushButton(
            "CHAT"
        )

        layout_extras.addWidget(
            self.btn_configuracoes
        )

        layout_extras.addWidget(
            self.btn_chat
        )

        layout.addLayout(
            layout_extras
        )

        layout_extras2 = QHBoxLayout()

        layout_extras2.setSpacing(
            10
        )

        self.btn_camera_ao_vivo = QPushButton(
            "CÂMERA AO VIVO"
        )

        self.btn_envio_arquivo = QPushButton(
            "ENVIAR ARQUIVO"
        )

        layout_extras2.addWidget(
            self.btn_camera_ao_vivo
        )

        layout_extras2.addWidget(
            self.btn_envio_arquivo
        )

        layout.addLayout(
            layout_extras2
        )

        self.btn_perfil = QPushButton(
            "PERFIL"
        )

        layout.addWidget(
            self.btn_perfil
        )

        for botao_nav in (
            self.btn_configuracoes,
            self.btn_chat,
            self.btn_camera_ao_vivo,
            self.btn_envio_arquivo,
            self.btn_perfil,
        ):
            botao_nav.setObjectName(
                "botaoNav"
            )

        layout.addSpacing(
            8
        )

        self.painel_nome = PainelNome(
            ao_alterar=self._aplicar_nome_novo
        )

        layout.addWidget(
            self.painel_nome
        )

        layout.addSpacing(
            8
        )

        self.painel_provedor = PainelProvedor()

        layout.addWidget(
            self.painel_provedor
        )

        layout.addSpacing(
            8
        )

        self.painel_dispositivos = PainelDispositivos()

        layout.addWidget(
            self.painel_dispositivos
        )

        layout.addStretch(
            1
        )

        self.visualizador = VisualizadorAlfred()

        self.chat_sobreposto = PainelChatSobreposto(
            self.visualizador
        )

        self.painel_console = PainelConsole()

        coluna_console = QWidget()
        coluna_console.setFixedWidth(
            340
        )

        layout_console = QVBoxLayout(
            coluna_console
        )

        layout_console.setContentsMargins(
            0,
            25,
            30,
            25,
        )

        layout_console.setSpacing(
            8
        )

        layout_console.addWidget(
            registro_titulo
        )

        layout_console.addWidget(
            self.log_box,
            1,
        )

        layout_console.addSpacing(
            12
        )

        layout_console.addWidget(
            self.painel_console,
            1,
        )

        layout_raiz.addWidget(
            coluna_controles
        )

        layout_raiz.addWidget(
            self.visualizador,
            1,
        )

        layout_raiz.addWidget(
            coluna_console
        )

        self.setCentralWidget(
            container
        )

        self.btn_chamada.clicked.connect(
            self.alternar_chamada
        )

        self.btn_tela.clicked.connect(
            self.analisar_tela
        )

        self.btn_camera.clicked.connect(
            self.analisar_camera
        )

        self.btn_configuracoes.clicked.connect(
            self.abrir_configuracoes
        )

        self.btn_chat.clicked.connect(
            self.abrir_chat
        )

        self.btn_camera_ao_vivo.clicked.connect(
            self.abrir_camera_ao_vivo
        )

        self.btn_envio_arquivo.clicked.connect(
            self.abrir_envio_arquivo
        )

        self.btn_perfil.clicked.connect(
            self.abrir_perfil
        )

    def escrever_log(self, texto):
        self.log_box.append(
            f"> {texto}"
        )

    def definir_status(self, texto):
        self.status_valor.setText(
            str(texto).upper()
        )

        self.visualizador.definir_status(
            texto
        )

    def _aplicar_nome_novo(self, nome):
        self.setWindowTitle(
            nome
        )

        self.titulo_label.setText(
            nome
        )

        self.visualizador.definir_nome(
            nome
        )

    def alternar_chamada(self):
        if self.live_worker is None:
            self.session_handle = None
            self.transcricao_preservada = []
            self.ativado_por_voz = False

            self.slug_perfil_chamada = None

            self.iniciar_chamada()

        else:
            print(
                "[TIMING-CONGELAMENTO] alternar_chamada(): "
                "self.live_worker ainda não é None — este clique NÃO "
                "inicia uma chamada nova, só chama parar() de novo "
                "(a chamada anterior ainda não terminou de encerrar)."
            )

            self.encerrar_chamada()

    def iniciar_chamada_por_voz(self):
        if self.live_worker is not None:
            return

        self.ativado_por_voz = True

        self.iniciar_chamada()

    def iniciar_chamada(self):
        self.btn_chamada.setText(
            "ENCERRAR CHAMADA"
        )

        self.btn_chamada.setProperty(
            "encerrando",
            True,
        )

        self.btn_chamada.style().unpolish(
            self.btn_chamada
        )

        self.btn_chamada.style().polish(
            self.btn_chamada
        )

        self.definir_status(
            "CONECTANDO"
        )

        self.escrever_log(
            "Iniciando conexão..."
        )

        self.encerramento_manual = False

        self.chat_sobreposto.limpar()

        self.visualizador.definir_ativo(
            True
        )

        self.live_worker = _classe_do_worker()(
            session_handle=self.session_handle,
            transcricao_inicial=self.transcricao_preservada,
            ativado_por_voz=self.ativado_por_voz,
            slug_perfil=self.slug_perfil_chamada,
        )

        self.ativado_por_voz = False

        self.live_worker.status_recebido.connect(
            self.atualizar_status
        )

        self.live_worker.erro_recebido.connect(
            self.mostrar_erro
        )

        self.live_worker.chamada_encerrada.connect(
            self.chamada_finalizada
        )

        self.live_worker.solicitou_encerramento.connect(
            self.encerrar_chamada_por_voz
        )

        self.live_worker.solicitou_reconexao.connect(
            self.preparar_reconexao_automatica
        )

        self.live_worker.solicitou_hibernacao.connect(
            self.preparar_hibernacao
        )

        self.live_worker.session_handle_atualizado.connect(
            self.salvar_session_handle
        )

        self.live_worker.nivel_audio.connect(
            self.visualizador.definir_nivel_audio
        )

        self.live_worker.start()

    def encerrar_chamada(self):
        if self.live_worker:
            self.encerramento_manual = True
            self.reconectar_automaticamente = False
            self.session_handle = None

            self.definir_status(
                "ENCERRANDO"
            )

            self.escrever_log(
                "Encerrando chamada..."
            )

            self.live_worker.parar()

    def atualizar_status(self, texto):
        self.definir_status(
            texto
        )

        self.escrever_log(
            texto
        )

    def mostrar_erro(self, erro):
        if not self.encerramento_manual:
            self.reconectar_automaticamente = True

        self.definir_status(
            "ERRO"
        )

        self.visualizador.definir_nivel_audio(
            0.0
        )

        self.escrever_log(
            f"Erro: {erro}"
        )

        self.painel_console.acrescentar(
            f"ERRO: {erro}",
            "erro",
        )

    def chamada_finalizada(self):
        print(
            "[TIMING-CONGELAMENTO] chamada_finalizada(): "
            "self.live_worker voltando a ser None agora."
        )

        if (
            self.live_worker is not None
            and self.reconectar_automaticamente
            and not self.encerramento_manual
        ):
            self.transcricao_preservada = list(
                self.live_worker.transcricao_conversa
            )

            self.slug_perfil_chamada = self.live_worker.slug_perfil

        else:
            self.transcricao_preservada = []
            self.slug_perfil_chamada = None

        self.live_worker = None

        self.btn_chamada.setText(
            "INICIAR CHAMADA"
        )

        self.btn_chamada.setProperty(
            "encerrando",
            False,
        )

        self.btn_chamada.style().unpolish(
            self.btn_chamada
        )

        self.btn_chamada.style().polish(
            self.btn_chamada
        )

        self.visualizador.definir_ativo(
            False
        )

        self.visualizador.definir_nivel_audio(
            0.0
        )

        self.definir_status(
            "OFFLINE"
        )

        if self.hibernando_por_voz:
            self.hibernando_por_voz = False
            self.reconectar_automaticamente = False

            self.definir_status(
                "PAUSADO — DIGA A FRASE DE ATIVAÇÃO"
            )

            self.escrever_log(
                "Chamada pausada — diga a frase de ativação para "
                "continuar."
            )

            return

        if self.reconectar_automaticamente and not self.encerramento_manual:
            self.reconectar_automaticamente = False

            self.escrever_log(
                "Reconectando automaticamente sem perder a conversa..."
            )

            QTimer.singleShot(
                450,
                self.iniciar_chamada,
            )

            return

        self.escrever_log(
            "Chamada encerrada."
        )

    def encerrar_chamada_por_voz(self):
        self.escrever_log(
            "Encerramento solicitado por voz."
        )

        self.encerrar_chamada()

    def preparar_reconexao_automatica(self):
        if self.encerramento_manual:
            return

        self.reconectar_automaticamente = True

        self.definir_status(
            "RENOVANDO CONEXÃO"
        )

        self.escrever_log(
            "Renovando a conexão sem perder a conversa..."
        )

    def preparar_hibernacao(self):
        if self.encerramento_manual:
            return

        self.hibernando_por_voz = True
        self.reconectar_automaticamente = True

        self.definir_status(
            "PAUSANDO CHAMADA..."
        )

        self.escrever_log(
            "Pausando a chamada por pedido do usuário..."
        )

        if self.live_worker:
            self.live_worker.parar()

    def salvar_session_handle(self, handle):
        if handle:
            self.session_handle = handle

    def analisar_tela(self):
        if not self.live_worker:
            self.escrever_log(
                "Inicie a chamada antes de analisar a tela."
            )

            return

        self.escrever_log(
            "Solicitando análise da tela..."
        )

        self.live_worker.solicitar_analise_tela()

    def analisar_camera(self):
        if not self.live_worker:
            self.escrever_log(
                "Inicie a chamada antes de analisar a câmera."
            )

            return

        self.escrever_log(
            "Solicitando análise da câmera..."
        )

        self.live_worker.solicitar_analise_camera()

    def abrir_configuracoes(self):
        obter_sinalizador().solicitou_abrir_configuracoes.emit()

    def abrir_chat(self):
        obter_sinalizador().solicitou_abrir_chat.emit()

    def abrir_camera_ao_vivo(self):
        obter_sinalizador().solicitou_abrir_camera.emit()

    def abrir_envio_arquivo(self):
        obter_sinalizador().solicitou_abrir_envio_arquivo.emit()

    def abrir_perfil(self):
        obter_sinalizador().solicitou_abrir_perfil.emit()

    def closeEvent(self, event):
        self.encerramento_manual = True
        self.reconectar_automaticamente = False

        if self.live_worker:
            self.live_worker.parar()

            self.live_worker.wait(
                3000
            )

        self.painel_console.restaurar_saida_padrao()

        event.accept()
