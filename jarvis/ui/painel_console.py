import sys
from datetime import datetime

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from jarvis.ui import estilo

MAXIMO_LINHAS = 600

COR_ERRO = "#ff3044"
COR_AVISO = "#c9862c"
COR_INFO = "#8f8388"

MARCADORES_ERRO = (
    "[CONEXÃO]",
    "[MICROFONE]",
    "[RECEPÇÃO]",
    "[REPRODUÇÃO]",
    "[VIGIA]",
    "Traceback",
    "Error",
    "Erro",
)

MARCADORES_AVISO = (
    "[INTERRUPÇÃO]",
    "[RESERVA]",
    "[PRIORIDADE]",
    "Aviso",
)


class _PonteSaida(QObject):
    linha_recebida = Signal(str, str)


class _RedirecionadorSaida:
    def __init__(self, original, ponte, nivel):
        self._original = original
        self._ponte = ponte
        self._nivel = nivel
        self._buffer = ""

    def write(self, texto):
        if self._original is not None:
            try:
                self._original.write(texto)

            except Exception:
                pass

        self._buffer += texto

        while "\n" in self._buffer:
            linha, self._buffer = self._buffer.split("\n", 1)

            if linha.strip():
                self._ponte.linha_recebida.emit(linha, self._nivel)

        return len(texto)

    def flush(self):
        if self._original is not None:
            try:
                self._original.flush()

            except Exception:
                pass

    def isatty(self):
        try:
            return self._original.isatty()

        except Exception:
            return False

    def fileno(self):
        return self._original.fileno()


class PainelConsole(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self._stdout_original = None
        self._stderr_original = None

        self._ponte = _PonteSaida()

        # Prints chegam de várias threads: só cruzam por Signal com QueuedConnection.
        self._ponte.linha_recebida.connect(
            self.acrescentar,
            Qt.ConnectionType.QueuedConnection,
        )

        self._montar()

    def _montar(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        cabecalho = QHBoxLayout()

        titulo = QLabel("Console")
        titulo.setObjectName("statusTitulo")

        self.botao_limpar = QPushButton("Limpar")
        self.botao_limpar.setObjectName("botaoConsole")
        self.botao_limpar.setCursor(Qt.CursorShape.PointingHandCursor)

        self.botao_limpar.setStyleSheet(
            "QPushButton#botaoConsole {"
            "    min-height: 0px;"
            "    padding: 3px 12px;"
            "    font-size: 10px;"
            "}"
        )
        self.botao_limpar.clicked.connect(self.limpar)

        cabecalho.addWidget(titulo)
        cabecalho.addStretch(1)
        cabecalho.addWidget(self.botao_limpar)

        self.caixa = QTextEdit()
        self.caixa.setObjectName("console")
        self.caixa.setReadOnly(True)

        self.caixa.setStyleSheet(
            "QTextEdit#console {"
            f"    color: {estilo.TEXTO_PRIMARIO};"
            f"    background-color: {estilo.FUNDO_PAINEL};"
            f"    border: 1px solid {estilo.BORDA};"
            "    border-radius: 3px;"
            "    padding: 8px;"
            '    font-family: "Consolas";'
            "    font-size: 10px;"
            "}"
            "QTextEdit#console:disabled {"
            "    color: #4d4348;"
            "    background-color: #0a0709;"
            "    border: 1px solid #1a0b0e;"
            "}"
        )
        self.caixa.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.caixa.setPlaceholderText(
            "Interrupções, avisos e erros aparecem aqui em tempo real."
        )

        self.caixa.document().setMaximumBlockCount(MAXIMO_LINHAS)

        layout.addLayout(cabecalho)
        layout.addWidget(self.caixa, 1)

    def acrescentar(self, texto, nivel="info"):
        if nivel == "auto" or not nivel:
            nivel = self.classificar(texto)

        cor = {
            "erro": COR_ERRO,
            "aviso": COR_AVISO,
        }.get(nivel, COR_INFO)

        horario = datetime.now().strftime("%H:%M:%S")

        barra = self.caixa.verticalScrollBar()
        estava_no_fim = barra.value() >= barra.maximum() - 4

        texto_seguro = (
            texto.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

        self.caixa.append(
            f'<span style="color:#999999">{horario}</span> '
            f'<span style="color:{cor}">{texto_seguro}</span>'
        )

        if estava_no_fim:
            barra.setValue(barra.maximum())

    def escrever_de_qualquer_thread(self, texto, nivel="auto"):
        self._ponte.linha_recebida.emit(texto, nivel)

    @staticmethod
    def classificar(texto):
        for marcador in MARCADORES_ERRO:
            if marcador in texto:
                return "erro"

        for marcador in MARCADORES_AVISO:
            if marcador in texto:
                return "aviso"

        return "info"

    def limpar(self):
        self.caixa.clear()

    def capturar_saida_padrao(self):
        if self._stdout_original is not None:
            return

        self._stdout_original = sys.stdout
        self._stderr_original = sys.stderr

        sys.stdout = _RedirecionadorSaida(
            self._stdout_original,
            self._ponte,
            "auto",
        )

        sys.stderr = _RedirecionadorSaida(
            self._stderr_original,
            self._ponte,
            "erro",
        )

    def restaurar_saida_padrao(self):
        if self._stdout_original is None:
            return

        sys.stdout = self._stdout_original
        sys.stderr = self._stderr_original

        self._stdout_original = None
        self._stderr_original = None
