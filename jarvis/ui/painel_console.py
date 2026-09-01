# Painel de console ao lado do registro de atividade.
#
# O registro de atividade mostra o que o jarvis está FAZENDO (status
# de alto nível: "Capturando tela...", "Chamada iniciada"). Este
# painel mostra o que está ACONTECENDO por baixo: interrupções de
# fala, avisos do vigia, falhas de conexão, erros e tracebacks — tudo
# que até agora só existia no terminal, onde ninguém está olhando na
# hora em que o problema acontece.
#
# Como ele captura tudo sem precisar alterar cada print do projeto:
# redireciona sys.stdout e sys.stderr. Toda mensagem já existente
# ([INTERRUPÇÃO], [VIGIA], [CONEXÃO], [MICROFONE], [RESERVA]...) e
# qualquer traceback aparecem aqui automaticamente, inclusive os
# vindos de pacotes isolados. O terminal continua recebendo tudo
# normalmente — a saída original nunca é substituída, só duplicada.
#
# Detalhe de thread que torna isso seguro: os prints vêm de várias
# threads (worker do Gemini, listener MQTT, detector de voz, threads
# de pacotes), e widget Qt só pode ser tocado na thread da GUI. Por
# isso a escrita passa por um Signal (_PonteSaida), que o Qt entrega
# na thread certa por conexão enfileirada — mesmo princípio já usado
# em jarvis/nucleo/sinalizador.py.
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

# Máximo de linhas mantidas no painel. Passando disso, as mais antigas
# são descartadas: sem esse limite, uma chamada longa (ou um print em
# laço) faria o QTextEdit crescer sem parar e travar a interface —
# seria absurdo um painel de diagnóstico virar a causa do próximo
# travamento.
MAXIMO_LINHAS = 600

COR_ERRO = "#c0392b"
COR_AVISO = "#b9770e"
COR_INFO = "#555555"

# Marcadores que o projeto já usa nos prints, classificados por
# gravidade. A classificação é só visual — nada de comportamento
# depende dela.
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


# Ponte de thread: qualquer thread pode emitir, o slot roda na GUI.
class _PonteSaida(QObject):
    linha_recebida = Signal(str, str)


# Substitui sys.stdout/sys.stderr sem perder o original: escreve nos
# dois lugares. Acumula até a quebra de linha porque print() faz mais
# de uma chamada a write() por linha (o texto e depois o "\n"), e
# emitir cada pedaço geraria linhas picotadas no painel.
class _RedirecionadorSaida:
    def __init__(self, original, ponte, nivel):
        self._original = original
        self._ponte = ponte
        self._nivel = nivel
        self._buffer = ""

    def write(self, texto):
        # O terminal continua recebendo tudo, exatamente como antes.
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

    # Alguns módulos checam isatty/fileno antes de escrever; repassar
    # evita que um print quebre por causa do redirecionamento.
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

        # QueuedConnection explícito: a emissão vem de outra thread na
        # maioria das vezes, e é isso que garante a entrega na GUI.
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

        # Mesmo motivo do estilo da caixa acima.
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

        # O estilo é aplicado AQUI, no próprio widget, e não no
        # ESTILO_GLOBAL da janela principal — por dois motivos:
        #
        # 1) Encapsulamento: o painel se veste sozinho, como o resto
        #    da lógica dele.
        # 2) Necessidade real: o ESTILO_GLOBAL usa cerquilha para
        #    comentar, e QSS não tem esse tipo de comentário (só o de
        #    bloco, no estilo do CSS). Cada linha dessas vira um
        #    seletor de id e engole a regra seguinte. Medido: das 16
        #    regras de lá, 13 estão mortas por isso. Uma regra do
        #    console colocada naquele arquivo morreria junto —
        #    confirmado testando a mesma regra isolada (aplica) e
        #    dentro do ESTILO_GLOBAL (não aplica).
        self.caixa.setStyleSheet(
            "QTextEdit#console {"
            "    color: #dddddd;"
            "    background-color: #1e1e1e;"
            "    border: 1px solid #3a3a3a;"
            "    border-radius: 3px;"
            "    padding: 8px;"
            '    font-family: "Consolas";'
            "    font-size: 10px;"
            "}"
        )
        self.caixa.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.caixa.setPlaceholderText(
            "Interrupções, avisos e erros aparecem aqui em tempo real."
        )

        # document().setMaximumBlockCount faz o descarte das linhas
        # antigas no próprio Qt, sem custo de manipular texto na mão.
        self.caixa.document().setMaximumBlockCount(MAXIMO_LINHAS)

        layout.addLayout(cabecalho)
        layout.addWidget(self.caixa, 1)

    # Escreve uma linha. nivel: "erro", "aviso" ou "info".
    # Só pode ser chamado na thread da GUI — de outra thread, use
    # escrever_de_qualquer_thread().
    def acrescentar(self, texto, nivel="info"):
        if nivel == "auto" or not nivel:
            nivel = self.classificar(texto)

        cor = {
            "erro": COR_ERRO,
            "aviso": COR_AVISO,
        }.get(nivel, COR_INFO)

        horario = datetime.now().strftime("%H:%M:%S")

        # Rolagem automática só quando o usuário já está no fim: se
        # ele subiu para ler algo, o painel não puxa a barra de volta
        # no meio da leitura.
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

    # Segura para chamar de qualquer thread.
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

    # Começa a duplicar sys.stdout/sys.stderr para este painel.
    # Idempotente: chamar duas vezes não empilha redirecionamentos.
    def capturar_saida_padrao(self):
        if self._stdout_original is not None:
            return

        # Sob pythonw.exe (sem console) sys.stdout pode ser None —
        # nesse caso o painel vira o ÚNICO destino, que é justamente
        # quando ele é mais útil.
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
