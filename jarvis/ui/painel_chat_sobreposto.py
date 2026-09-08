# Chat sobreposto à esfera: mostra, em texto, o que o assistente
# respondeu, sem tapar a animação.
#
# POR QUE UM FILHO SOLTO, E NÃO UM ITEM DE LAYOUT: a esfera
# (jarvis/ui/visualizador_alfred.py) é o único widget com peso de
# expansão na janela — pôr o chat num layout ao lado dela roubaria
# espaço da animação. Este painel é filho do PRÓPRIO visualizador,
# fora de qualquer layout, e se reposiciona sozinho acompanhando o
# tamanho do pai (ver _instalar_acompanhamento).
#
# TRANSPARÊNCIA: aqui ela simplesmente funciona, e vale registrar por
# quê, porque a pergunta natural é "e a composição com OpenGL?".
# A esfera NÃO é OpenGL nem Qt Quick 3D — é um QWidget comum que
# desenha QPixmap em cache com QPainter (o "3D" é ilusão feita com
# QRadialGradient). Não há superfície nativa separada, então não
# existe o problema clássico de sobrepor widget translúcido a conteúdo
# OpenGL, nem necessidade de WA_AlwaysStackOnTop. Tudo acontece no
# mesmo backing store, e o Qt compõe o filho não-opaco sobre o pai
# sozinho.
#
# O QUE REALMENTE PRECISA DE CUIDADO, e é a pegadinha desta tela:
#
#   1. WA_TranslucentBackground NÃO é usado. Esse atributo é para
#      JANELAS de topo; num widget filho ele não faz o que aparenta.
#      O fundo translúcido é pintado no paintEvent, com cor alfa.
#
#   2. QTextEdit é um QAbstractScrollArea: deixar o fundo transparente
#      no stylesheet do widget NÃO basta, porque quem pinta a área do
#      texto é o VIEWPORT, e ele continua opaco. Sem tratar o viewport
#      (ver _preparar_texto), aparece um retângulo sólido em cima da
#      esfera — exatamente o que este painel existe para evitar.
#
#   3. O painel fica ESCONDIDO enquanto não há resposta nenhuma. Antes
#      da primeira fala não há o que mostrar, e um retângulo vazio
#      sobre a esfera seria só sujeira.
#
# De onde vem o texto: jarvis/nucleo/sinalizador.py,
# resposta_texto_recebida — o mesmo sinal que a janela de chat já
# consome. Ele é emitido pelos TRÊS cérebros de voz, de dentro da
# thread do worker, então a conexão aqui é explicitamente enfileirada.
import collections

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import QTextEdit, QVBoxLayout, QWidget

from jarvis.nucleo.sinalizador import obter_sinalizador
from jarvis.ui import estilo


# ---------------------------------------------------------------- #
# AJUSTES DE APARÊNCIA
#
# Opacidades de 0.0 (invisível) a 1.0 (opaco). São os números para
# mexer quando o chat estiver tapando demais a esfera, ou de leitura
# difícil — nenhum outro valor de transparência existe neste arquivo.
# ---------------------------------------------------------------- #

# Fundo da caixa. É o que mais pesa na sensação de "estou vendo a
# esfera através do chat": 0.0 deixa só o texto flutuando, 1.0 tapa
# a esfera por completo.
OPACIDADE_FUNDO = 0.55

# Contorno da caixa. Um pouco mais forte que o fundo, para a caixa ter
# limite visível sem precisar escurecer o miolo.
OPACIDADE_BORDA = 0.70

# Texto das respostas. Alto de propósito: transparência no texto
# atrapalha a leitura muito antes de melhorar o visual.
OPACIDADE_TEXTO = 0.96

# Geometria, em fração da área da esfera. O painel fica na parte de
# baixo para não cobrir o centro, que é onde a esfera desenha o nome e
# o status.
FRACAO_ALTURA = 0.34
MARGEM_LATERAL = 18
MARGEM_INFERIOR = 18

# Raio dos cantos arredondados, em pixels.
RAIO_CANTO = 14

# Quantas respostas ficam visíveis. Um teto existe pelo mesmo motivo
# do painel de console: um chat que cresce sem limite acaba virando o
# problema que ele deveria ajudar a diagnosticar.
MAXIMO_RESPOSTAS = 30


def _com_alfa(hex_cor, opacidade):
    """
    Converte um token de jarvis/ui/estilo.py em QColor com alfa.

    Centralizado numa função só para que as constantes acima sejam
    realmente o único lugar onde a transparência é decidida.
    """
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
    """
    Caixa translúcida sobre a esfera com as respostas do assistente.

    Uso: instanciar passando a esfera como pai. Ele se conecta sozinho
    ao sinalizador e se reposiciona sozinho — quem cria não precisa
    fazer mais nada além de, opcionalmente, chamar limpar() ao começar
    uma chamada nova.
    """

    def __init__(self, pai):
        super().__init__(pai)

        # Sem isto o Qt trataria o widget como opaco e não pintaria a
        # esfera por baixo — o fundo alfa não teria com o que se
        # misturar. É o oposto de WA_OpaquePaintEvent, e é o que faz a
        # sobreposição funcionar.
        self.setAttribute(
            Qt.WA_NoSystemBackground,
            True,
        )

        # O painel é decoração: cliques, rolagem e foco continuam indo
        # para o que estiver embaixo. Sem isso ele roubaria eventos de
        # mouse de uma área grande da janela sem ter o que fazer com
        # eles.
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

        # As margens internas deixam o texto longe da borda pintada.
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

        # Conexão ENFILEIRADA de propósito: resposta_texto_recebida é
        # emitido de dentro do laço assíncrono do worker, que roda em
        # outra thread, e widget Qt só pode ser tocado na thread da
        # GUI. Mesmo princípio do painel de console.
        obter_sinalizador().resposta_texto_recebida.connect(
            self.adicionar_resposta,
            Qt.QueuedConnection,
        )

        # Começa escondido: antes da primeira resposta não há nada a
        # mostrar, e uma caixa vazia só atrapalharia a esfera.
        self.hide()

    # ---------------------------------------------------------- #
    # APARÊNCIA
    # ---------------------------------------------------------- #

    def _preparar_texto(self):
        self.texto.setReadOnly(True)

        # Os mesmos dois atributos do painel, repetidos aqui de
        # propósito: eles NÃO são herdados, e é o QTextEdit que ocupa
        # quase toda a área. Sem isto ele voltaria a aceitar clique e
        # foco por dentro de um painel que se anuncia como decoração —
        # e testes/auditar_estilo_desabilitado.py, que ignora widget de
        # exibição justamente por essas duas propriedades, voltaria a
        # cobrar dele um estado desabilitado que não existe.
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

        # A PEGADINHA: num QAbstractScrollArea quem pinta a área do
        # texto é o viewport, e ele é opaco por padrão. Deixar só o
        # QTextEdit transparente ainda desenharia um retângulo sólido
        # sobre a esfera.
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

        # objectName + regra :disabled pelo mesmo motivo do painel de
        # console: um seletor de TIPO não alcança um widget que já tem
        # estilo próprio por id, e testes/auditar_estilo_desabilitado.py
        # exige que todo widget deste tipo mude de aparência ao ser
        # desabilitado. Na prática este aqui nunca é desabilitado (é
        # somente leitura e transparente ao mouse), mas manter a regra
        # é mais honesto do que abrir exceção no auditor — que é o que
        # apodrece com o tempo.
        self.texto.setObjectName("chatSobreposto")

        # background: transparent nos DOIS (widget e viewport) — o
        # fundo visível é o que este painel pinta em paintEvent.
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
        """
        Desenha o fundo translúcido e o contorno.

        É aqui que a transparência acontece — e não em
        WA_TranslucentBackground, que serve para janelas de topo, não
        para um filho como este.
        """
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

    # ---------------------------------------------------------- #
    # POSICIONAMENTO
    # ---------------------------------------------------------- #

    def _instalar_acompanhamento(self, pai):
        """
        Faz o painel seguir o tamanho da esfera SEM que a esfera
        precise saber que ele existe.

        Um event filter no pai, em vez de um resizeEvent dentro de
        visualizador_alfred.py: assim o visualizador continua um widget
        de desenho puro, sem referência a nada da janela.
        """
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

    # ---------------------------------------------------------- #
    # CONTEÚDO
    # ---------------------------------------------------------- #

    def adicionar_resposta(self, texto):
        """
        Uma resposta falada do assistente entra no chat.

        Vale para os três cérebros: Gemini Live e OpenAI Realtime
        emitem no fim do turno, e o modo local emite quando o texto
        chega junto do áudio (user property "texto" do MQTT).
        """
        limpo = (texto or "").strip()

        if not limpo:
            return

        self._respostas.append(limpo)
        self._redesenhar_texto()

        if not self.isVisible():
            self.show()

        self.raise_()

    def limpar(self):
        """Esvazia o chat e some da tela — usado ao iniciar a chamada."""
        self._respostas.clear()
        self.texto.clear()
        self.hide()

    def _redesenhar_texto(self):
        # Reconstruído por inteiro a partir da deque, em vez de
        # append incremental: é o que faz o teto de MAXIMO_RESPOSTAS
        # valer de verdade (a deque descarta a mais antiga sozinha),
        # sem precisar mexer no documento do QTextEdit.
        self.texto.setPlainText(
            "\n\n".join(self._respostas)
        )

        # Rola para a resposta mais recente.
        barra = self.texto.verticalScrollBar()
        barra.setValue(
            barra.maximum()
        )
