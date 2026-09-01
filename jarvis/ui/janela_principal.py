

# Qt fornece constantes do framework.
# Neste arquivo, é utilizado principalmente para alinhar textos ao centro.
from PySide6.QtCore import Qt

# Importa os componentes visuais utilizados pela janela:
# QHBoxLayout organiza itens horizontalmente.
# QLabel exibe textos.
# QMainWindow cria a janela principal.
# QPushButton cria botões.
# QTextEdit cria a área de registro.
# QVBoxLayout organiza itens verticalmente.
# QWidget funciona como container central.
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# Importa a thread responsável pela conexão com o Gemini Live.
# Essa classe cuida do áudio, da visão e da comunicação em tempo real.
from jarvis.gemini.cliente_live import GeminiLiveWorker

# Console de diagnóstico exibido ao lado do registro de atividade —
# toda a lógica (captura de sys.stdout/sys.stderr, ponte de thread,
# limite de linhas) mora no próprio módulo.
from jarvis.ui.painel_console import PainelConsole


# QSS é a linguagem de estilos do Qt.
# Ela possui sintaxe parecida com CSS e define cores,
# fontes, bordas, tamanhos e estados dos componentes.
ESTILO_GLOBAL = """
# Define o estilo da janela principal.
QMainWindow {
    background-color: #ffffff;
}

# Define o estilo padrão de todos os widgets.
QWidget {
    color: #222222;
    font-family: "Segoe UI";
}

# Aplica estilo somente ao QLabel cujo objectName é "titulo".
QLabel#titulo {
    color: #111111;
    font-size: 22px;
    font-weight: 600;
}

# Estilo específico do subtítulo.
QLabel#subtitulo {
    color: #666666;
    font-size: 11px;
}

# Estilo usado nos títulos de pequenas seções.
QLabel#statusTitulo {
    color: #555555;
    font-size: 11px;
    font-weight: 600;
}

# Estilo do valor atual do status.
QLabel#statusValor {
    color: #b00020;
    font-size: 13px;
    font-weight: 600;
}

# Estilo padrão aplicado a todos os botões.
QPushButton {
    min-height: 40px;
    padding: 0 14px;
    color: #222222;
    background-color: #f2f2f2;
    border: 1px solid #cccccc;
    border-radius: 4px;
    font-size: 11px;
}

# Estilo aplicado quando o mouse passa sobre o botão.
QPushButton:hover {
    background-color: #e8e8e8;
}

# Estilo aplicado enquanto o botão está pressionado.
QPushButton:pressed {
    background-color: #dddddd;
}

# Estilo específico do botão principal de chamada.
QPushButton#botaoChamada {
    color: #ffffff;
    background-color: #b00020;
    border: 1px solid #8f001a;
    font-weight: 600;
}

QPushButton#botaoChamada:hover {
    background-color: #98001c;
}

# Estilo aplicado quando a propriedade personalizada
# "encerrando" estiver definida como true.
QPushButton#botaoChamada[encerrando="true"] {
    color: #ffffff;
    background-color: #555555;
    border: 1px solid #444444;
}

# Estilo da caixa que exibe o registro de atividades.
QTextEdit#registro {
    color: #222222;
    background-color: #ffffff;
    border: 1px solid #cccccc;
    border-radius: 3px;
    padding: 8px;
    font-family: "Consolas";
    font-size: 10px;
}


"""


# Classe principal da interface básica do ALFRED.
# Ela herda de QMainWindow, que fornece estrutura de janela,
# barra de título e área central.
class MainWindow(QMainWindow):

    # Construtor da janela.
    # Configura tamanho, título, estilo e componentes.
    def __init__(self):
        # Inicializa a classe QMainWindow.
        super().__init__()

        # Define o texto exibido na barra superior da janela.
        self.setWindowTitle(
            "ALFRED"
        )

        # Define o menor tamanho permitido para a janela. Mais largo
        # do que era antes porque agora existem DUAS colunas embaixo
        # (registro de atividade e console), e espremer as duas em
        # 560px deixaria as duas ilegíveis.
        self.setMinimumSize(
            900,
            460,
        )

        # Define o tamanho inicial da janela.
        self.resize(
            1040,
            560,
        )

        # Remove a referência da thread encerrada.
        self.live_worker = None

        # Aplica o estilo QSS em toda a janela.
        self.setStyleSheet(
            ESTILO_GLOBAL
        )

        # Cria e organiza todos os componentes visuais.
        self._criar_interface()

        # A partir daqui, tudo que o app imprimir (de qualquer thread
        # ou pacote) também aparece no console da direita, em tempo
        # real. O terminal continua recebendo tudo igual.
        self.painel_console.capturar_saida_padrao()

        self.painel_console.acrescentar(
            "Console pronto. Interrupções de fala, avisos e erros "
            "aparecem aqui.",
            "info",
        )

    # Monta a interface completa da janela.
    def _criar_interface(self):
        # Cria o widget central que receberá o layout principal.
        container = QWidget()

        # Cria um layout vertical dentro do container.
        layout = QVBoxLayout(
            container
        )

        # Define as margens internas:
        # esquerda, superior, direita e inferior.
        layout.setContentsMargins(
            30,
            25,
            30,
            25,
        )

        # Define a distância padrão entre os componentes.
        layout.setSpacing(
            12
        )

        # Cria o texto principal da interface.
        titulo = QLabel(
            "ALFRED"
        )

        # Define o objectName usado pelo estilo QSS.
        titulo.setObjectName(
            "titulo"
        )

        # Centraliza o texto dentro do QLabel.
        titulo.setAlignment(
            Qt.AlignCenter
        )

        # Cria o subtítulo da aplicação.
        subtitulo = QLabel(
            "Assistente de Inteligência Artificial"
        )

        subtitulo.setObjectName(
            "subtitulo"
        )

        subtitulo.setAlignment(
            Qt.AlignCenter
        )

        # Cria o texto fixo "Status".
        status_titulo = QLabel(
            "Status"
        )

        status_titulo.setObjectName(
            "statusTitulo"
        )

        status_titulo.setAlignment(
            Qt.AlignCenter
        )

        # Cria o rótulo que mostrará o estado atual.
        # É salvo em self porque será atualizado depois.
        self.status_valor = QLabel(
            "OFFLINE"
        )

        self.status_valor.setObjectName(
            "statusValor"
        )

        self.status_valor.setAlignment(
            Qt.AlignCenter
        )

        # Cria o botão principal para iniciar ou encerrar a chamada.
        self.btn_chamada = QPushButton(
            "INICIAR CHAMADA"
        )

        # Define o nome usado pelo estilo específico do botão.
        self.btn_chamada.setObjectName(
            "botaoChamada"
        )

        # Layout horizontal para os dois botões de visão.
        layout_visao = QHBoxLayout()

        # Define o espaço entre os botões de tela e câmera.
        layout_visao.setSpacing(
            10
        )

        # Botão que solicita a análise da tela.
        self.btn_tela = QPushButton(
            "ANALISAR TELA"
        )

        # Botão que solicita a análise da webcam.
        self.btn_camera = QPushButton(
            "ANALISAR CÂMERA"
        )

        # Adiciona um botão ao layout horizontal.
        layout_visao.addWidget(
            self.btn_tela
        )

        # Adiciona um botão ao layout horizontal.
        layout_visao.addWidget(
            self.btn_camera
        )

        # Cria o título da área de registro.
        registro_titulo = QLabel(
            "Registro de atividade"
        )

        registro_titulo.setObjectName(
            "statusTitulo"
        )

        # Cria a caixa de texto que exibirá os eventos.
        self.log_box = QTextEdit()

        # Define o nome usado pelo estilo QSS.
        self.log_box.setObjectName(
            "registro"
        )

        # Impede que o usuário edite manualmente o registro.
        self.log_box.setReadOnly(
            True
        )

        # Exibe uma mensagem enquanto o registro estiver vazio.
        self.log_box.setPlaceholderText(
            "Aguardando eventos..."
        )

        # Adiciona um componente ao layout vertical.
        layout.addWidget(
            titulo
        )

        # Adiciona um componente ao layout vertical.
        layout.addWidget(
            subtitulo
        )

        # Adiciona um espaço fixo entre grupos de componentes.
        layout.addSpacing(
            8
        )

        # Adiciona um componente ao layout vertical.
        layout.addWidget(
            status_titulo
        )

        # Adiciona um componente ao layout vertical.
        layout.addWidget(
            self.status_valor
        )

        # Adiciona um espaço fixo entre grupos de componentes.
        layout.addSpacing(
            6
        )

        # Adiciona um componente ao layout vertical.
        layout.addWidget(
            self.btn_chamada
        )

        # Adiciona o layout horizontal dentro do layout principal.
        layout.addLayout(
            layout_visao
        )

        # Adiciona um espaço fixo entre grupos de componentes.
        layout.addSpacing(
            8
        )

        # Coluna da esquerda: o registro de atividade, como sempre foi.
        coluna_registro = QVBoxLayout()
        coluna_registro.setContentsMargins(0, 0, 0, 0)
        coluna_registro.setSpacing(6)

        coluna_registro.addWidget(
            registro_titulo
        )

        coluna_registro.addWidget(
            self.log_box,
            1,
        )

        # Coluna da direita: o console de diagnóstico. Ele duplica
        # sys.stdout/sys.stderr, então mostra em tempo real tudo que
        # antes só aparecia no terminal — interrupções de fala,
        # avisos do vigia, falhas de conexão e tracebacks. Toda a
        # lógica mora em jarvis/ui/painel_console.py; aqui só é
        # instanciado e posicionado.
        self.painel_console = PainelConsole()

        # Os dois lado a lado, com o mesmo peso.
        area_inferior = QHBoxLayout()
        area_inferior.setSpacing(12)

        area_inferior.addLayout(
            coluna_registro,
            1,
        )

        area_inferior.addWidget(
            self.painel_console,
            1,
        )

        layout.addLayout(
            area_inferior,
            1,
        )

        # Define o container como área central da QMainWindow.
        self.setCentralWidget(
            container
        )

        # Conecta o clique do botão principal
        # ao método que alterna entre iniciar e encerrar.
        self.btn_chamada.clicked.connect(
            self.alternar_chamada
        )

        # Conecta o botão de tela ao método analisar_tela.
        self.btn_tela.clicked.connect(
            self.analisar_tela
        )

        # Conecta o botão da câmera ao método analisar_camera.
        self.btn_camera.clicked.connect(
            self.analisar_camera
        )

    # Adiciona uma nova mensagem ao registro de atividade.
    def escrever_log(self, texto):
        # append adiciona o texto em uma nova linha.
        self.log_box.append(
            f"> {texto}"
        )

    # Atualiza o texto do status exibido na interface.
    def definir_status(self, texto):
        # Converte para texto e mostra em letras maiúsculas.
        self.status_valor.setText(
            str(texto).upper()
        )

    # Decide entre iniciar ou encerrar a chamada.
    def alternar_chamada(self):
        # Se não existe worker, inicia uma nova chamada.
        if self.live_worker is None:
            self.iniciar_chamada()

        # Se já existe worker, solicita o encerramento.
        else:
            self.encerrar_chamada()

    # Prepara a interface e inicia a thread do Gemini Live.
    def iniciar_chamada(self):
        # Troca o texto do botão para indicar encerramento.
        self.btn_chamada.setText(
            "ENCERRAR CHAMADA"
        )

        # Volta a propriedade "encerrando" para False.
        self.btn_chamada.setProperty(
            "encerrando",
            True,
        )

        # Remove temporariamente o estilo atual do botão.
        self.btn_chamada.style().unpolish(
            self.btn_chamada
        )

        # Reaplica o estilo para considerar a nova propriedade.
        self.btn_chamada.style().polish(
            self.btn_chamada
        )

        # Atualiza o status visual.
        self.definir_status(
            "CONECTANDO"
        )

        # Registra o acontecimento na caixa de atividades.
        self.escrever_log(
            "Iniciando conexão..."
        )

        # Cria a thread responsável pela sessão Gemini.
        self.live_worker = GeminiLiveWorker()

        # Recebe mensagens de status vindas da thread.
        self.live_worker.status_recebido.connect(
            self.atualizar_status
        )

        # Recebe erros emitidos pela thread.
        self.live_worker.erro_recebido.connect(
            self.mostrar_erro
        )

        # Executa a limpeza da interface quando a thread termina.
        self.live_worker.chamada_encerrada.connect(
            self.chamada_finalizada
        )

        # Permite que um comando de voz encerre a chamada.
        self.live_worker.solicitou_encerramento.connect(
            self.encerrar_chamada
        )

        # Inicia efetivamente a QThread.
        self.live_worker.start()

    # Solicita o encerramento da chamada ativa.
    def encerrar_chamada(self):
        # Só executa se existir uma thread ativa.
        if self.live_worker:
            self.definir_status(
                "ENCERRANDO"
            )

            self.escrever_log(
                "Encerrando chamada..."
            )

            # Altera o estado interno do worker para encerrar os loops.
            self.live_worker.parar()

    # Recebe uma mensagem do worker e atualiza
    # tanto o status quanto o registro.
    def atualizar_status(self, texto):
        # Atualiza o status visual.
        self.definir_status(
            texto
        )

        # Registra o acontecimento na caixa de atividades.
        self.escrever_log(
            texto
        )

    # Exibe um erro recebido da thread.
    def mostrar_erro(self, erro):
        # Atualiza o status visual.
        self.definir_status(
            "ERRO"
        )

        # Registra o acontecimento na caixa de atividades.
        self.escrever_log(
            f"Erro: {erro}"
        )

        # E também no console, em vermelho. Os erros vindos do worker
        # chegam por Signal (erro_recebido) e não passam por print,
        # então sem esta linha eles não apareceriam ali — justamente
        # as mensagens mais importantes do painel.
        self.painel_console.acrescentar(
            f"ERRO: {erro}",
            "erro",
        )

    # Restaura a interface quando a chamada termina.
    def chamada_finalizada(self):
        # Remove a referência da thread encerrada.
        self.live_worker = None

        # Troca o texto do botão para indicar encerramento.
        self.btn_chamada.setText(
            "INICIAR CHAMADA"
        )

        # Volta a propriedade "encerrando" para False.
        self.btn_chamada.setProperty(
            "encerrando",
            False,
        )

        # Remove temporariamente o estilo atual do botão.
        self.btn_chamada.style().unpolish(
            self.btn_chamada
        )

        # Reaplica o estilo para considerar a nova propriedade.
        self.btn_chamada.style().polish(
            self.btn_chamada
        )

        # Atualiza o status visual.
        self.definir_status(
            "OFFLINE"
        )

        # Registra o acontecimento na caixa de atividades.
        self.escrever_log(
            "Chamada encerrada."
        )

    # Solicita ao worker uma captura e análise da tela.
    def analisar_tela(self):
        # Impede a análise quando não existe sessão ativa.
        if not self.live_worker:
            self.escrever_log(
                "Inicie a chamada antes de analisar a tela."
            )

            return

        # Registra o acontecimento na caixa de atividades.
        self.escrever_log(
            "Solicitando análise da tela..."
        )

        # Chama o método público da thread responsável pela tela.
        self.live_worker.solicitar_analise_tela()

    # Solicita ao worker uma captura e análise da câmera.
    def analisar_camera(self):
        # Impede a análise quando não existe sessão ativa.
        if not self.live_worker:
            self.escrever_log(
                "Inicie a chamada antes de analisar a câmera."
            )

            return

        # Registra o acontecimento na caixa de atividades.
        self.escrever_log(
            "Solicitando análise da câmera..."
        )

        # Chama o método público da thread responsável pela webcam.
        self.live_worker.solicitar_analise_camera()

    # Evento executado automaticamente ao fechar a janela.
    # Garante que a thread não continue rodando em segundo plano.
    def closeEvent(self, event):
        # Só executa se existir uma thread ativa.
        if self.live_worker:
            # Altera o estado interno do worker para encerrar os loops.
            self.live_worker.parar()

            # Aguarda até 3 segundos para a thread finalizar.
            self.live_worker.wait(
                3000
            )

        # Devolve sys.stdout/sys.stderr ao que eram. Sem isto, um
        # print de despedida de qualquer thread ainda tentaria escrever
        # num widget já destruído.
        self.painel_console.restaurar_saida_padrao()

        # Autoriza o fechamento da janela.
        event.accept()