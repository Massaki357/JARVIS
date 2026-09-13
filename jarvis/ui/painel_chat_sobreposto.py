import collections

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import QTextEdit, QVBoxLayout, QWidget

from jarvis.nucleo.sinalizador import obter_sinalizador
from jarvis.ui import estilo


OPACIDADE_FUNDO = 0.55

OPACIDADE_BORDA = 0.70

OPACIDADE_TEXTO = 0.96

FRACAO_ALTURA = 0.34
MARGEM_LATERAL = 18
MARGEM_INFERIOR = 18

RAIO_CANTO = 14

MAXIMO_RESPOSTAS = 30


def _com_alfa(hex_cor, opacidade):
    cor = QColor(hex_cor)
    cor.setAlpha(
        max(
            0,
            min(
                255,
                round(opacidade * 255),
            ),
        )
    )

    return cor


class PainelChatSobreposto(QWidget):
    def __init__(self, pai):
        super().__init__(pai)

        self.setAttribute(
            Qt.WA_NoSystemBackground,
            True,
        )

        self.setAttribute(
            Qt.WA_TransparentForMouseEvents,
            True,
        )

        self.setFocusPolicy(
            Qt.NoFocus
        )

        self._respostas = collections.deque(
            maxlen=MAXIMO_RESPOSTAS
        )

        layout = QVBoxLayout(self)

        layout.setContentsMargins(
            16,
            12,
            16,
            12,
        )

        self.texto = QTextEdit()
        self._preparar_texto()

        layout.addWidget(
            self.texto
        )

        self._instalar_acompanhamento(pai)

        obter_sinalizador().resposta_texto_recebida.connect(
            self.adicionar_resposta,
            Qt.QueuedConnection,
        )

        self.hide()

    def _preparar_texto(self):
        self.texto.setReadOnly(True)

        self.texto.setAttribute(
            Qt.WA_TransparentForMouseEvents,
            True,
        )

        self.texto.setFocusPolicy(
            Qt.NoFocus
        )

        self.texto.setFrameShape(
            QTextEdit.NoFrame
        )

        self.texto.setVerticalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff
        )

        self.texto.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff
        )

        self.texto.viewport().setAutoFillBackground(False)

        self.texto.viewport().setAttribute(
            Qt.WA_TranslucentBackground,
            True,
        )

        cor_texto = _com_alfa(
            estilo.TEXTO_PRIMARIO,
            OPACIDADE_TEXTO,
        )

        cor_apagada = _com_alfa(
            estilo.TEXTO_SECUNDARIO,
            OPACIDADE_TEXTO * 0.5,
        )

        self.texto.setObjectName("chatSobreposto")

        self.texto.setStyleSheet(
            "QTextEdit#chatSobreposto {"
            "  background: transparent;"
            f"  color: rgba({cor_texto.red()}, {cor_texto.green()},"
            f" {cor_texto.blue()}, {cor_texto.alpha()});"
            "  border: none;"
            "  font-size: 13px;"
            "}"
            "QTextEdit#chatSobreposto:disabled {"
            f"  color: rgba({cor_apagada.red()}, {cor_apagada.green()},"
            f" {cor_apagada.blue()}, {cor_apagada.alpha()});"
            "}"
            "QTextEdit#chatSobreposto > QWidget { background: transparent; }"
        )

    def paintEvent(self, event):
        painter = QPainter(self)

        painter.setRenderHint(
            QPainter.Antialiasing,
            True,
        )

        caminho = QPainterPath()

        caminho.addRoundedRect(
            self.rect().adjusted(0, 0, -1, -1),
            RAIO_CANTO,
            RAIO_CANTO,
        )

        painter.fillPath(
            caminho,
            _com_alfa(
                estilo.FUNDO_PAINEL,
                OPACIDADE_FUNDO,
            ),
        )

        painter.setPen(
            _com_alfa(
                estilo.BORDA,
                OPACIDADE_BORDA,
            )
        )

        painter.drawPath(caminho)

        painter.end()

    def _instalar_acompanhamento(self, pai):
        self._pai_observado = pai
        pai.installEventFilter(self)
        self._reposicionar()

    def eventFilter(self, objeto, evento):
        if objeto is self._pai_observado and evento.type() in (
            QEvent.Resize,
            QEvent.Show,
        ):
            self._reposicionar()

        return super().eventFilter(objeto, evento)

    def _reposicionar(self):
        pai = self.parentWidget()

        if pai is None:
            return

        largura = max(
            0,
            pai.width() - 2 * MARGEM_LATERAL,
        )

        altura = max(
            0,
            round(pai.height() * FRACAO_ALTURA),
        )

        self.setGeometry(
            MARGEM_LATERAL,
            pai.height() - altura - MARGEM_INFERIOR,
            largura,
            altura,
        )

    def adicionar_resposta(self, texto):
        limpo = (texto or "").strip()

        if not limpo:
            return

        self._respostas.append(limpo)
        self._redesenhar_texto()

        if not self.isVisible():
            self.show()

        self.raise_()

    def limpar(self):
        self._respostas.clear()
        self.texto.clear()
        self.hide()

    def _redesenhar_texto(self):
        self.texto.setPlainText(
            "\n\n".join(self._respostas)
        )

        barra = self.texto.verticalScrollBar()
        barra.setValue(
            barra.maximum()
        )
