from PySide6.QtWidgets import (
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from jarvis.ui.janela_envio_arquivo import processar_arquivo_para_sessao

from jarvis.ui.estilo import ESTILO_GLOBAL


class ChatWindow(QWidget):
    def __init__(self, obter_worker_ativo, ao_fechar=None):
        super().__init__()

        self._obter_worker_ativo = obter_worker_ativo
        self._ao_fechar = ao_fechar

        self.setWindowTitle("Chat com o jarvis")
        self.resize(480, 560)
        self.setAcceptDrops(True)
        self.setStyleSheet(ESTILO_GLOBAL)

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

    def adicionar_resposta_assistente(self, texto):
        self._adicionar_linha("jarvis", texto)

    def _adicionar_linha(self, remetente, texto):
        self._historico.append(
            f"<b>{remetente}:</b> {texto}"
        )
