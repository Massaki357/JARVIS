

# Qt fornece constantes do framework.
# Neste arquivo, é utilizado principalmente para alinhar textos ao centro.
from PySide6.QtCore import Qt, QTimer

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

# Provedor de IA ativo (.env, PROVEDOR_IA) — ver jarvis/nucleo/config.py.
from jarvis.nucleo.config import usar_provedor_openai

# Sinalizador genérico para abrir janelas extras fora da thread da
# GUI (ver jarvis/nucleo/sinalizador.py) — os botões de configurações
# e chat abaixo só EMITEM os mesmos sinais que os tools de voz
# abrir_configuracoes/abrir_chat já emitem; quem efetivamente cria as
# janelas continua sendo o slot conectado em main.py, nunca este
# arquivo.
from jarvis.nucleo.sinalizador import obter_sinalizador

# Console de diagnóstico exibido ao lado do registro de atividade —
# toda a lógica (captura de sys.stdout/sys.stderr, ponte de thread,
# limite de linhas) mora no próprio módulo.
from jarvis.ui.painel_console import PainelConsole

# Selects de microfone e alto-falante — toda a lógica (listar os
# aparelhos agrupando as duplicatas de host API, salvar no config.json
# e aplicar em sd.default.device) mora no próprio módulo.
from jarvis.ui.painel_dispositivos import PainelDispositivos

# Esfera animada que reage ao estado da chamada e ao volume da voz —
# veio do JARVIS COMPLETO (ui/alfred_visualizer.py). Todo o desenho
# (QPainter, cache de fundo/esfera, FPS adaptativo) mora no próprio
# módulo; aqui ela é só instanciada, posicionada e alimentada por
# definir_status/definir_ativo/definir_nivel_audio.
from jarvis.ui.visualizador_alfred import VisualizadorAlfred


# Devolve a CLASSE de worker do provedor configurado. Os dois workers
# expõem a mesma API pública (sinais, construtor e métodos), então
# daqui para baixo a janela não precisa saber qual deles está rodando.
#
# O import da OpenAI é feito aqui dentro, e não no topo do arquivo, de
# propósito: quem usa o Gemini não precisa ter o pacote openai
# instalado nem pagar o custo de importá-lo a cada abertura do app.
def _classe_do_worker():
    if usar_provedor_openai():
        from jarvis.openai_realtime import OpenAIRealtimeWorker

        return OpenAIRealtimeWorker

    return GeminiLiveWorker


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

        # Define o menor tamanho permitido para a janela. Largo
        # porque agora são TRÊS colunas: controles + registro de
        # atividade (330px), a esfera do visualizador (o que sobrar) e
        # o console de diagnóstico (340px).
        self.setMinimumSize(
            1180,
            560,
        )

        # Define o tamanho inicial da janela.
        self.resize(
            1380,
            760,
        )

        # Remove a referência da thread encerrada.
        self.live_worker = None

        # Estado da retomada de sessão (vem do JARVIS COMPLETO).
        #
        # session_handle: último token de retomada emitido pelo
        # servidor. Preservado APENAS entre reconexões automáticas; é
        # zerado em qualquer encerramento manual ou por voz, para a
        # próxima chamada do usuário começar limpa.
        self.session_handle = None

        # Transcrição acumulada da conversa, carregada de um worker
        # para o próximo numa reconexão automática — do lado do
        # servidor a conversa continua, então o histórico daqui
        # também precisa continuar (senão o resumo salvo no fim teria
        # só o trecho depois da última renovação).
        self.transcricao_preservada = []

        # Distinguem uma QUEDA de conexão (deve reabrir sozinho,
        # preservando a conversa) de um encerramento pedido pelo
        # usuário ou por voz (não deve reabrir nada).
        self.reconectar_automaticamente = False
        self.encerramento_manual = False

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

        # A janela tem três colunas: controles à esquerda, a esfera
        # animada no centro (o painel principal, como no JARVIS
        # COMPLETO) e o console de diagnóstico à direita.
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

        # Coluna da esquerda. Continua se chamando "layout" porque é
        # nela que todos os controles já existentes são adicionados.
        coluna_controles = QWidget()
        coluna_controles.setFixedWidth(
            330
        )

        layout = QVBoxLayout(
            coluna_controles
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

        # Layout horizontal para os botões de configurações e chat —
        # os dois abrem janelas que já existem hoje só por voz
        # (abrir_configuracoes/abrir_chat); estes botões só dão um
        # segundo jeito de pedir a mesma coisa, sem depender do
        # microfone nem de uma chamada ativa.
        layout_extras = QHBoxLayout()

        layout_extras.setSpacing(
            10
        )

        # Botão que abre a tela de configurações do jarvis.
        self.btn_configuracoes = QPushButton(
            "CONFIGURAÇÕES"
        )

        # Botão que abre o chat de texto do jarvis.
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

        # Selects de microfone e alto-falante. A troca vale para a
        # PRÓXIMA chamada (um stream já aberto não muda de aparelho no
        # meio); a ativação por voz, que segura o microfone entre as
        # chamadas, é reiniciada na hora pelo próprio painel.
        layout.addSpacing(
            8
        )

        self.painel_dispositivos = PainelDispositivos()

        layout.addWidget(
            self.painel_dispositivos
        )

        # Adiciona um espaço fixo entre grupos de componentes.
        layout.addSpacing(
            8
        )

        # Fim da coluna da esquerda: o registro de atividade, como
        # sempre foi — só que agora empilhado abaixo dos controles em
        # vez de dividir a largura da janela com o console.
        layout.addWidget(
            registro_titulo
        )

        layout.addWidget(
            self.log_box,
            1,
        )

        # Coluna do centro: a esfera. É o painel principal da
        # interface — mostra o status da chamada e reage ao volume da
        # voz do ALFRED (sinal nivel_audio do worker).
        self.visualizador = VisualizadorAlfred()

        # Coluna da direita: o console de diagnóstico. Ele duplica
        # sys.stdout/sys.stderr, então mostra em tempo real tudo que
        # antes só aparecia no terminal — interrupções de fala,
        # avisos do vigia, falhas de conexão e tracebacks. Toda a
        # lógica mora em jarvis/ui/painel_console.py; aqui só é
        # instanciado e posicionado.
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

        layout_console.addWidget(
            self.painel_console,
            1,
        )

        # A esfera é a única que recebe peso de expansão: as duas
        # colunas laterais têm largura fixa, então toda a sobra de
        # espaço da janela vai para ela.
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

        # Conecta os botões de configurações e chat aos métodos que
        # só emitem o sinalizador — a mesma janela que a voz já abre.
        self.btn_configuracoes.clicked.connect(
            self.abrir_configuracoes
        )

        self.btn_chat.clicked.connect(
            self.abrir_chat
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

        # O mesmo texto aparece dentro da esfera — ela é o painel
        # principal da janela, e o rótulo pequeno da lateral vira só
        # uma repetição de apoio.
        self.visualizador.definir_status(
            texto
        )

    # Decide entre iniciar ou encerrar a chamada.
    def alternar_chamada(self):
        # Se não existe worker, inicia uma nova chamada.
        if self.live_worker is None:
            # Uma chamada iniciada pelo usuário (botão ou palavra de
            # ativação) começa SEMPRE do zero: o token de retomada e a
            # transcrição preservada só valem para reconexão
            # automática. Ver preparar_reconexao_automatica.
            self.session_handle = None
            self.transcricao_preservada = []

            self.iniciar_chamada()

        # Se já existe worker, solicita o encerramento.
        else:
            # [DIAGNÓSTICO DE CONGELAMENTO — ver DEBUG_TIMING_CONGELAMENTO
            # em jarvis/gemini/cliente_live.py] self.live_worker só é
            # zerado (ver chamada_finalizada) quando o sinal
            # chamada_encerrada dispara, e esse sinal só dispara quando
            # GeminiLiveWorker.executar() retorna por completo — se a
            # limpeza de uma chamada anterior estiver travada/demorando,
            # este clique não inicia uma chamada nova nenhuma, só chama
            # parar() de novo (inofensivo, mas também sem efeito
            # visível). Este print confirma exatamente esse cenário
            # quando ele acontece.
            print(
                "[TIMING-CONGELAMENTO] alternar_chamada(): "
                "self.live_worker ainda não é None — este clique NÃO "
                "inicia uma chamada nova, só chama parar() de novo "
                "(a chamada anterior ainda não terminou de encerrar)."
            )

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

        # Uma abertura de chamada nova (ou reconexão) nunca é, ela
        # própria, um encerramento manual.
        self.encerramento_manual = False

        # A esfera entra em modo animado de "conectado".
        self.visualizador.definir_ativo(
            True
        )

        # Cria a thread responsável pela sessão Gemini. O
        # session_handle e a transcrição só vêm preenchidos numa
        # reconexão automática — ver preparar_reconexao_automatica.
        self.live_worker = _classe_do_worker()(
            session_handle=self.session_handle,
            transcricao_inicial=self.transcricao_preservada,
        )

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
            self.encerrar_chamada_por_voz
        )

        # O servidor pediu renovação do WebSocket (go_away): é
        # reconexão esperada, não erro.
        self.live_worker.solicitou_reconexao.connect(
            self.preparar_reconexao_automatica
        )

        # Guarda o token de retomada mais recente, para a reconexão
        # continuar a mesma conversa.
        self.live_worker.session_handle_atualizado.connect(
            self.salvar_session_handle
        )

        # Alimenta a animação da esfera com o volume da voz do ALFRED.
        self.live_worker.nivel_audio.connect(
            self.visualizador.definir_nivel_audio
        )

        # Inicia efetivamente a QThread.
        self.live_worker.start()

    # Solicita o encerramento da chamada ativa.
    def encerrar_chamada(self):
        # Só executa se existir uma thread ativa.
        if self.live_worker:
            # Encerramento pedido pelo usuário: não reabrir nada, e a
            # conversa atual termina aqui (o token de retomada é
            # descartado; só go_away/erro o preservam).
            self.encerramento_manual = True
            self.reconectar_automaticamente = False
            self.session_handle = None

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
        # Uma queda que o usuário não pediu deve reabrir a chamada
        # sozinha, preservando a conversa (o session_handle NÃO é
        # zerado aqui, ao contrário de encerrar_chamada).
        if not self.encerramento_manual:
            self.reconectar_automaticamente = True

        # Atualiza o status visual.
        self.definir_status(
            "ERRO"
        )

        self.visualizador.definir_nivel_audio(
            0.0
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
        # [DIAGNÓSTICO DE CONGELAMENTO] Ver o print em alternar_chamada.
        # Este é o momento em que self.live_worker finalmente volta a
        # ser None — cruzar com o horário do "[TIMING-CONGELAMENTO]
        # Encerramento concluído em..." no console pra confirmar que é
        # exatamente a limpeza de executar() que atrasa isto.
        print(
            "[TIMING-CONGELAMENTO] chamada_finalizada(): "
            "self.live_worker voltando a ser None agora."
        )

        # Antes de largar a referência: se a chamada vai reabrir
        # sozinha, leva a transcrição acumulada para o próximo worker.
        # Do lado do servidor a conversa continua (session_handle), e
        # sem isto o resumo salvo no fim teria só o trecho depois da
        # última renovação.
        if (
            self.live_worker is not None
            and self.reconectar_automaticamente
            and not self.encerramento_manual
        ):
            self.transcricao_preservada = list(
                self.live_worker.transcricao_conversa
            )

        else:
            self.transcricao_preservada = []

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

        # Zera a animação da esfera.
        self.visualizador.definir_ativo(
            False
        )

        self.visualizador.definir_nivel_audio(
            0.0
        )

        # Atualiza o status visual.
        self.definir_status(
            "OFFLINE"
        )

        # Reabre a chamada sozinha quando a queda não foi pedida pelo
        # usuário — usando o mesmo session_handle, então a conversa
        # continua de onde parou. O pequeno atraso deixa a thread
        # anterior terminar de morrer antes de abrir a próxima.
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

        # Registra o acontecimento na caixa de atividades.
        self.escrever_log(
            "Chamada encerrada."
        )

    # Encerramento pedido POR VOZ (sinal solicitou_encerramento).
    #
    # Existe separado de encerrar_chamada só por clareza: os dois
    # fazem a mesma coisa, e a limpeza do session_handle já acontece
    # lá dentro. Sem este método, o sinal de voz cairia direto em
    # encerrar_chamada e o comportamento seria idêntico — mas o log
    # não distinguiria "o usuário clicou" de "o usuário mandou
    # desligar".
    def encerrar_chamada_por_voz(self):
        self.escrever_log(
            "Encerramento solicitado por voz."
        )

        self.encerrar_chamada()

    # Conectado a solicitou_reconexao: o servidor avisou (go_away) que
    # vai fechar o WebSocket. Isso é renovação normal da sessão, não
    # erro — então a próxima abertura é marcada como esperada, e o
    # session_handle NÃO é descartado.
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

    # Conectado a session_handle_atualizado: guarda o token mais
    # recente de retomada emitido pelo servidor.
    def salvar_session_handle(self, handle):
        if handle:
            self.session_handle = handle

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

    # Abre a tela de configurações do jarvis — mesmo sinal que o tool
    # de voz abrir_configuracoes já emite (jarvis/pacotes/configuracoes/),
    # conectado em main.py ao slot que efetivamente cria a janela.
    # Funciona com ou sem chamada ativa.
    def abrir_configuracoes(self):
        obter_sinalizador().solicitou_abrir_configuracoes.emit()

    # Abre o chat de texto do jarvis — mesmo sinal que o tool de voz
    # abrir_chat já emite (jarvis/pacotes/chat_jarvis/). Se não houver
    # chamada ativa, a própria janela de chat avisa ao tentar enviar
    # (ver ChatWindow / _obter_worker_ativo em main.py).
    def abrir_chat(self):
        obter_sinalizador().solicitou_abrir_chat.emit()

    # Evento executado automaticamente ao fechar a janela.
    # Garante que a thread não continue rodando em segundo plano.
    def closeEvent(self, event):
        # Fechar a janela é encerramento manual: nada de reabrir a
        # chamada sozinha depois que o app já está fechando.
        self.encerramento_manual = True
        self.reconectar_automaticamente = False

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