# Janela de chat de texto — fora de qualquer arquivo _basic. Conecta
# na MESMA sessão Gemini Live já em andamento (não uma conversa
# separada) através da ponte thread-safe exposta pelo worker
# (GeminiLiveWorker.enviar_texto_da_ui/enviar_imagem_da_ui em
# gemini/live_client_basic.py) — ver INTEGRATION.md, seção
# "chat_jarvis", pra como essa ponte funciona por dentro.
from PySide6.QtWidgets import (
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.envio_arquivo_window import processar_arquivo_para_sessao


class ChatWindow(QWidget):

    def __init__(self, obter_worker_ativo, ao_fechar=None):
        super().__init__()

        # Chamado toda vez que uma mensagem/arquivo precisa ser
        # enviado — nunca guardamos uma referência fixa ao worker,
        # porque a instância de GeminiLiveWorker é recriada a cada
        # chamada de voz (ver ui/main_window_basic.py). Ler
        # window.live_worker de novo a cada envio (é isso que este
        # getter faz, definido em main_basic.py) garante que a
        # janela de chat continua funcionando mesmo que a chamada
        # termine e uma nova comece enquanto ela está aberta.
        self._obter_worker_ativo = obter_worker_ativo
        self._ao_fechar = ao_fechar

        self.setWindowTitle("Chat com o jarvis")
        self.resize(480, 560)
        self.setAcceptDrops(True)

        layout = QVBoxLayout(self)

        self._historico = QTextEdit()
        self._historico.setReadOnly(True)
        layout.addWidget(self._historico, stretch=1)

        self._campo_texto = QLineEdit()
        self._campo_texto.setPlaceholderText(
            "Digite uma mensagem ou arraste um arquivo aqui..."
        )
        self._campo_texto.returnPressed.connect(self._enviar_mensagem)
        layout.addWidget(self._campo_texto)

        botao_enviar = QPushButton("Enviar")
        botao_enviar.clicked.connect(self._enviar_mensagem)
        layout.addWidget(botao_enviar)

    def closeEvent(self, event):
        if self._ao_fechar:
            self._ao_fechar()

        super().closeEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()

        if not urls:
            return

        # Mesma função usada pela janela dedicada de envio de
        # arquivo — não duplicada aqui.
        _sucesso, mensagem = processar_arquivo_para_sessao(
            urls[0].toLocalFile(),
            self._obter_worker_ativo(),
        )

        self._adicionar_linha("Sistema", mensagem)

    def _enviar_mensagem(self):
        texto = self._campo_texto.text().strip()

        if not texto:
            return

        worker = self._obter_worker_ativo()

        if worker is None:
            self._adicionar_linha(
                "Sistema",
                "Não há nenhuma chamada de voz ativa agora.",
            )
            return

        enviado = worker.enviar_texto_da_ui(texto)

        if not enviado:
            self._adicionar_linha(
                "Sistema",
                "Não foi possível enviar — a chamada de voz não "
                "está mais ativa.",
            )
            return

        self._adicionar_linha("Você", texto)
        self._campo_texto.clear()

    # Chamado (na thread principal — a conexão em main_basic.py já
    # garante isso) sempre que um turno de resposta falada do Gemini
    # termina, com a transcrição completa daquele turno. Ver
    # interfaces_extras/sinalizador.py (resposta_texto_recebida) e
    # GeminiLiveWorker.receber_audio.
    def adicionar_resposta_assistente(self, texto):
        self._adicionar_linha("jarvis", texto)

    def _adicionar_linha(self, remetente, texto):
        self._historico.append(
            f"<b>{remetente}:</b> {texto}"
        )
