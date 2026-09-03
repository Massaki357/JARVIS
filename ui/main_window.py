# [CURSO] Qt fornece constantes do framework PySide6.
# [CURSO] Neste arquivo, Qt.AlignCenter é usado para centralizar textos.
from PySide6.QtCore import Qt, QTimer

# [CURSO] Importa os componentes visuais usados pela janela:
# [CURSO] QFrame cria os painéis; QHBoxLayout e QVBoxLayout organizam os elementos;
# [CURSO] QLabel exibe textos; QPushButton cria botões; QTextEdit mostra o log;
# [CURSO] QSizePolicy controla expansão; QWidget funciona como container central.
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# [CURSO] Importa a thread que mantém a conexão em tempo real com o Gemini.
# [CURSO] Ela envia status, erros, áudio e sinais de encerramento para a interface.
from gemini.live_client import GeminiLiveWorker
# [CURSO] Importa o visualizador futurista que desenha a esfera,
# [CURSO] os anéis, o status e a animação de áudio.
from ui.alfred_visualizer import AlfredVisualizer


# [CURSO] A variável abaixo contém todo o QSS da interface.
# [CURSO] QSS é semelhante ao CSS e controla cores, bordas, fontes e estados.
# [CURSO] Nenhum comentário foi colocado dentro desta string para não alterar o estilo.
ESTILO_GLOBAL = """
QMainWindow {
    background-color: #050507;
}

QWidget {
    color: #f2f2f4;
    font-family: "Segoe UI";
}

QFrame#painelLateral {
    background-color: rgba(9, 9, 12, 242);
    border: 1px solid rgba(255, 35, 52, 70);
    border-radius: 18px;
}

QFrame#painelPrincipal {
    background-color: rgba(5, 5, 7, 246);
    border: 1px solid rgba(255, 35, 52, 55);
    border-radius: 22px;
}

QLabel#tituloPainel {
    color: #ffffff;
    font-size: 18px;
    font-weight: 700;
    letter-spacing: 3px;
}

QLabel#subtituloPainel {
    color: #8c8c94;
    font-size: 11px;
}

QPushButton {
    min-height: 46px;
    padding: 0 16px;
    color: #f5f5f6;
    background-color: rgba(18, 18, 22, 235);
    border: 1px solid rgba(255, 54, 71, 75);
    border-radius: 12px;
    font-size: 12px;
    font-weight: 600;
}

QPushButton:hover {
    background-color: rgba(55, 9, 16, 245);
    border: 1px solid rgba(255, 70, 86, 180);
}

QPushButton:pressed {
    background-color: rgba(120, 6, 22, 250);
    border: 1px solid #ff4057;
}

QPushButton#botaoChamada {
    min-height: 54px;
    color: #ffffff;
    background-color: #b90b26;
    border: 1px solid #ff425a;
    font-size: 13px;
    font-weight: 700;
}

QPushButton#botaoChamada:hover {
    background-color: #dd1232;
}

QPushButton#botaoChamada[encerrando="true"] {
    background-color: #2b2b31;
    border: 1px solid #696973;
    color: #b8b8be;
}

QTextEdit#logBox {
    color: #d7d7dc;
    background-color: rgba(2, 2, 4, 225);
    border: 1px solid rgba(255, 44, 63, 50);
    border-radius: 13px;
    padding: 10px;
    font-family: "Consolas";
    font-size: 10px;
    selection-background-color: #a10b23;
}

QScrollBar:vertical {
    width: 7px;
    background: transparent;
}

QScrollBar::handle:vertical {
    min-height: 30px;
    background: rgba(255, 48, 66, 115);
    border-radius: 3px;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0px;
}
"""


# [CURSO] Classe principal da interface futurista.
# [CURSO] Ela herda de QMainWindow, que fornece a estrutura base da janela.
class MainWindow(QMainWindow):

    # [CURSO] Inicializa a janela, define tamanho, estilo
    # [CURSO] e cria todos os componentes visuais.
    def __init__(self):
        # [CURSO] Inicializa corretamente a classe QMainWindow.
        super().__init__()

        # [CURSO] Define o título mostrado na barra superior da janela.
        self.setWindowTitle(
            "ALFRED // Neural Desktop Assistant"
        )

        # [CURSO] Impede que a janela seja reduzida abaixo deste tamanho.
        self.setMinimumSize(
            1000,
            680,
        )

        # [CURSO] Define o tamanho inicial da janela.
        self.resize(
            1180,
            760,
        )

        # [CURSO] Remove a referência da thread já finalizada.
        self.live_worker = None
        self.session_handle = None
        self.reconectar_automaticamente = False
        self.encerramento_manual = False

        # [CURSO] Aplica o QSS completo armazenado em ESTILO_GLOBAL.
        self.setStyleSheet(
            ESTILO_GLOBAL
        )

        # [CURSO] Chama o método que monta toda a interface.
        self._criar_interface()

    # [CURSO] Cria os painéis, layouts, textos, botões,
    # [CURSO] log e visualizador do ALFRED.
    def _criar_interface(self):
        # [CURSO] Container central que receberá o layout raiz.
        container = QWidget()

        # [CURSO] Remove margens internas do container.
        container.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        # [CURSO] Layout horizontal principal.
        # [CURSO] Coloca o painel lateral à esquerda e o painel visual à direita.
        layout_raiz = QHBoxLayout(
            container
        )

        # [CURSO] Define as margens externas da interface.
        layout_raiz.setContentsMargins(
            18,
            18,
            18,
            18,
        )

        # [CURSO] Define o espaço entre os dois painéis.
        layout_raiz.setSpacing(
            16
        )

        # [CURSO] Cria o painel lateral de controles e eventos.
        painel_lateral = QFrame()

        # [CURSO] Define o nome usado pelo seletor QSS QFrame#painelLateral.
        painel_lateral.setObjectName(
            "painelLateral"
        )

        # [CURSO] Mantém a largura do painel lateral fixa.
        painel_lateral.setFixedWidth(
            280
        )

        # [CURSO] Organiza verticalmente os itens do painel lateral.
        layout_lateral = QVBoxLayout(
            painel_lateral
        )

        # [CURSO] Define as margens internas do painel lateral.
        layout_lateral.setContentsMargins(
            18,
            20,
            18,
            18,
        )

        # [CURSO] Define o espaço entre os componentes laterais.
        layout_lateral.setSpacing(
            12
        )

        # [CURSO] Cria o título principal do painel lateral.
        titulo = QLabel(
            "SYSTEM CORE"
        )

        # [CURSO] Liga este QLabel ao estilo QLabel#tituloPainel.
        titulo.setObjectName(
            "tituloPainel"
        )

        # [CURSO] Centraliza o título horizontal e verticalmente.
        titulo.setAlignment(
            Qt.AlignCenter
        )

        # [CURSO] Cria o subtítulo descritivo do painel.
        subtitulo = QLabel(
            "Controle neural e telemetria local"
        )

        subtitulo.setObjectName(
            "subtituloPainel"
        )

        subtitulo.setAlignment(
            Qt.AlignCenter
        )

        # [CURSO] Permite quebra automática de linha no subtítulo.
        subtitulo.setWordWrap(
            True
        )

        # [CURSO] Botão principal para iniciar ou encerrar a conexão.
        self.btn_chamada = QPushButton(
            "INICIAR CONEXÃO"
        )

        # [CURSO] Liga o botão ao estilo QPushButton#botaoChamada.
        self.btn_chamada.setObjectName(
            "botaoChamada"
        )

        # [CURSO] Botão que solicita uma captura e análise da tela.
        self.btn_tela = QPushButton(
            "▣  ANALISAR TELA"
        )

        # [CURSO] Botão que solicita uma captura e análise da webcam.
        self.btn_camera = QPushButton(
            "◉  ANALISAR CÂMERA"
        )

        # [CURSO] Título da área de eventos do sistema.
        log_titulo = QLabel(
            "EVENT STREAM"
        )

        log_titulo.setObjectName(
            "subtituloPainel"
        )

        log_titulo.setAlignment(
            Qt.AlignCenter
        )

        # [CURSO] Caixa usada para mostrar mensagens de atividade.
        self.log_box = QTextEdit()

        # [CURSO] Liga a caixa ao estilo QTextEdit#logBox.
        self.log_box.setObjectName(
            "logBox"
        )

        # [CURSO] Impede que o usuário edite o registro manualmente.
        self.log_box.setReadOnly(
            True
        )

        # [CURSO] Mostra uma mensagem enquanto não houver eventos.
        self.log_box.setPlaceholderText(
            "Aguardando eventos do sistema..."
        )

        # [CURSO] Permite que o log se expanda para ocupar o espaço disponível.
        self.log_box.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding,
        )

        # [CURSO] Adiciona um widget ao layout lateral na ordem definida.
        layout_lateral.addWidget(
            titulo
        )

        # [CURSO] Adiciona um widget ao layout lateral na ordem definida.
        layout_lateral.addWidget(
            subtitulo
        )

        # [CURSO] Adiciona um espaço fixo entre grupos de componentes.
        layout_lateral.addSpacing(
            10
        )

        # [CURSO] Adiciona um widget ao layout lateral na ordem definida.
        layout_lateral.addWidget(
            self.btn_chamada
        )

        # [CURSO] Adiciona um widget ao layout lateral na ordem definida.
        layout_lateral.addWidget(
            self.btn_tela
        )

        # [CURSO] Adiciona um widget ao layout lateral na ordem definida.
        layout_lateral.addWidget(
            self.btn_camera
        )

        # [CURSO] Adiciona um espaço fixo entre grupos de componentes.
        layout_lateral.addSpacing(
            10
        )

        # [CURSO] Adiciona um widget ao layout lateral na ordem definida.
        layout_lateral.addWidget(
            log_titulo
        )

        # [CURSO] Adiciona um widget ao layout lateral na ordem definida.
        layout_lateral.addWidget(
            self.log_box,
            1,
        )

        # [CURSO] Cria o painel que receberá o visualizador futurista.
        painel_principal = QFrame()

        # [CURSO] Liga o painel ao estilo QFrame#painelPrincipal.
        painel_principal.setObjectName(
            "painelPrincipal"
        )

        # [CURSO] Cria o layout interno do painel principal.
        layout_principal = QVBoxLayout(
            painel_principal
        )

        # [CURSO] Define uma margem pequena ao redor do visualizador.
        layout_principal.setContentsMargins(
            8,
            8,
            8,
            8,
        )

        # [CURSO] Cria a animação visual do ALFRED.
        self.visualizador = AlfredVisualizer()

        # [CURSO] Insere o visualizador no painel principal.
        layout_principal.addWidget(
            self.visualizador
        )

        # [CURSO] Adiciona cada painel ao layout raiz.
        layout_raiz.addWidget(
            painel_lateral
        )

        # [CURSO] Adiciona cada painel ao layout raiz.
        layout_raiz.addWidget(
            painel_principal,
            1,
        )

        # [CURSO] Define o container como conteúdo central da QMainWindow.
        self.setCentralWidget(
            container
        )

        # [CURSO] Ao clicar no botão principal, chama alternar_chamada.
        self.btn_chamada.clicked.connect(
            self.alternar_chamada
        )

        # [CURSO] Liga o botão de tela ao método analisar_tela.
        self.btn_tela.clicked.connect(
            self.analisar_tela
        )

        # [CURSO] Liga o botão da câmera ao método analisar_camera.
        self.btn_camera.clicked.connect(
            self.analisar_camera
        )

    # [CURSO] Acrescenta uma mensagem ao registro de atividades.
    def escrever_log(self, texto):
        # [CURSO] append adiciona o texto ao final, em uma nova linha.
        self.log_box.append(
            f"> {texto}"
        )

    # [CURSO] Decide se deve iniciar ou encerrar a conexão.
    def alternar_chamada(self):
        # [CURSO] Sem worker ativo, inicia uma nova conexão.
        if self.live_worker is None:
            # Uma chamada iniciada manualmente pelo usuário deve começar limpa.
            # O session_handle só é preservado em reconexões automáticas.
            self.session_handle = None
            self.iniciar_chamada()

        # [CURSO] Com worker ativo, solicita o encerramento.
        else:
            self.encerrar_chamada()

    # [CURSO] Atualiza a interface, cria o worker,
    # [CURSO] conecta os sinais e inicia a thread Gemini.
    def iniciar_chamada(self):
        # [CURSO] Troca o texto do botão para indicar que agora ele encerra.
        self.btn_chamada.setText(
            "ENCERRAR CONEXÃO"
        )

        # [CURSO] Define a propriedade dinâmica usada pelo QSS.
        # [CURSO] O valor True ativa o seletor [encerrando="true"].
        self.btn_chamada.setProperty(
            "encerrando",
            True,
        )

        # [CURSO] Remove temporariamente o estilo atual do botão.
        self.btn_chamada.style().unpolish(
            self.btn_chamada
        )

        # [CURSO] Reaplica o estilo considerando a nova propriedade.
        self.btn_chamada.style().polish(
            self.btn_chamada
        )

        # [CURSO] Ativa o modo animado do visualizador.
        self.visualizador.definir_ativo(
            True
        )

        # [CURSO] Atualiza o texto de status da esfera.
        self.visualizador.definir_status(
            "CONECTANDO"
        )

        # [CURSO] Cria a thread responsável pela chamada Gemini Live.
        self.encerramento_manual = False
        self.live_worker = GeminiLiveWorker(
            session_handle=self.session_handle
        )

        # [CURSO] Encaminha mensagens de status para atualizar_status.
        self.live_worker.status_recebido.connect(
            self.atualizar_status
        )

        # [CURSO] Encaminha erros para mostrar_erro.
        self.live_worker.erro_recebido.connect(
            self.mostrar_erro
        )

        # [CURSO] Chama chamada_finalizada quando a thread termina.
        self.live_worker.chamada_encerrada.connect(
            self.chamada_finalizada
        )

        # [CURSO] Permite que o comando de voz encerre a conexão.
        self.live_worker.solicitou_encerramento.connect(
            self.encerrar_chamada_por_voz
        )

        # O GoAway é uma renovação normal solicitada pelo servidor.
        # Não deve aparecer como erro nem como encerramento manual.
        self.live_worker.solicitou_reconexao.connect(
            self.preparar_reconexao_automatica
        )

        self.live_worker.session_handle_atualizado.connect(
            self.salvar_session_handle
        )

        # [CURSO] Verifica se esta versão do worker possui o sinal nivel_audio.
        if hasattr(
            self.live_worker,
            "nivel_audio",
        ):
            # [CURSO] Liga o volume da voz à animação do visualizador.
            self.live_worker.nivel_audio.connect(
                self.visualizador.definir_nivel_audio
            )

        # [CURSO] Inicia efetivamente a QThread.
        self.live_worker.start()

    def encerrar_chamada_por_voz(self):
        """
        Encerra definitivamente a conversa atual por comando de voz.

        O token da sessão é apagado para que a próxima chamada iniciada
        pelo usuário não retome o comando antigo de encerramento.
        """

        self.session_handle = None
        self.encerrar_chamada()

    # [CURSO] Solicita o encerramento controlado da conexão.
    def encerrar_chamada(self):
        # [CURSO] Só executa se houver worker ativo.
        if self.live_worker:
            self.encerramento_manual = True
            self.reconectar_automaticamente = False

            # Encerramento solicitado pelo usuário finaliza a conversa atual.
            # Apenas GoAway/erro automático preserva o session_handle.
            self.session_handle = None
            self.visualizador.definir_status(
                "ENCERRANDO CONEXÃO"
            )

            # [CURSO] Altera o estado interno do worker para finalizar os loops.
            self.live_worker.parar()

    # [CURSO] Atualiza o status visual e registra a mesma mensagem no log.
    def atualizar_status(self, texto):
        # [CURSO] Atualiza o texto de status da esfera.
        self.visualizador.definir_status(
            texto
        )

        self.escrever_log(
            texto
        )

    # [CURSO] Exibe o estado de erro, zera a animação
    # [CURSO] de áudio e registra os detalhes.
    def mostrar_erro(self, erro):
        if not self.encerramento_manual:
            self.reconectar_automaticamente = True

        # [CURSO] Atualiza o texto de status da esfera.
        self.visualizador.definir_status(
            "ERRO NA CONEXÃO"
        )

        # [CURSO] Zera a reação visual de áudio.
        self.visualizador.definir_nivel_audio(
            0.0
        )

        self.escrever_log(
            f"Erro: {erro}"
        )

    # [CURSO] Restaura toda a interface após o fim da chamada.
    def chamada_finalizada(self):
        # [CURSO] Remove a referência da thread já finalizada.
        self.live_worker = None

        # [CURSO] Troca o texto do botão para indicar que agora ele encerra.
        self.btn_chamada.setText(
            "INICIAR CONEXÃO"
        )

        # [CURSO] Define a propriedade dinâmica usada pelo QSS.
        # [CURSO] O valor True ativa o seletor [encerrando="true"].
        self.btn_chamada.setProperty(
            "encerrando",
            False,
        )

        # [CURSO] Remove temporariamente o estilo atual do botão.
        self.btn_chamada.style().unpolish(
            self.btn_chamada
        )

        # [CURSO] Reaplica o estilo considerando a nova propriedade.
        self.btn_chamada.style().polish(
            self.btn_chamada
        )

        # [CURSO] Ativa o modo animado do visualizador.
        self.visualizador.definir_ativo(
            False
        )

        # [CURSO] Atualiza o texto de status da esfera.
        self.visualizador.definir_status(
            "OFFLINE"
        )

        # [CURSO] Zera a reação visual de áudio.
        self.visualizador.definir_nivel_audio(
            0.0
        )

        if self.reconectar_automaticamente and not self.encerramento_manual:
            self.reconectar_automaticamente = False
            self.escrever_log(
                "Reconectando automaticamente sem perder a conversa..."
            )
            QTimer.singleShot(450, self.iniciar_chamada)
        else:
            self.escrever_log(
                "Chamada encerrada."
            )

    def preparar_reconexao_automatica(self):
        """
        Marca a próxima abertura como renovação normal da sessão.
        O worker atual será fechado de forma limpa e a interface
        iniciará outro usando o mesmo session_handle.
        """

        if self.encerramento_manual:
            return

        self.reconectar_automaticamente = True
        self.visualizador.definir_status(
            "RENOVANDO CONEXÃO"
        )

        self.escrever_log(
            "Renovando a conexão sem perder a conversa..."
        )

    def salvar_session_handle(self, handle):
        if handle:
            self.session_handle = handle

    # [CURSO] Solicita ao worker a captura e análise da tela.
    def analisar_tela(self):
        # [CURSO] Impede a ação quando não há conexão ativa.
        if not self.live_worker:
            self.escrever_log(
                "Inicie a conexão antes de analisar a tela."
            )

            return

        self.escrever_log(
            "Solicitando análise da tela..."
        )

        # [CURSO] Encaminha o pedido de tela para a thread Gemini.
        self.live_worker.solicitar_analise_tela()

    # [CURSO] Solicita ao worker a captura e análise da câmera.
    def analisar_camera(self):
        # [CURSO] Impede a ação quando não há conexão ativa.
        if not self.live_worker:
            self.escrever_log(
                "Inicie a conexão antes de analisar a câmera."
            )

            return

        self.escrever_log(
            "Solicitando análise da câmera..."
        )

        # [CURSO] Encaminha o pedido de câmera para a thread Gemini.
        self.live_worker.solicitar_analise_camera()

    # [CURSO] Evento executado automaticamente ao fechar a janela.
    # [CURSO] Ele garante que a thread não permaneça rodando em segundo plano.
    def closeEvent(self, event):
        # [CURSO] Só executa se houver worker ativo.
        if self.live_worker:
            # [CURSO] Altera o estado interno do worker para finalizar os loops.
            self.live_worker.parar()

            # [CURSO] Aguarda por até 3 segundos o encerramento da thread.
            self.live_worker.wait(
                3000
            )

        # [CURSO] Autoriza o fechamento definitivo da janela.
        event.accept()