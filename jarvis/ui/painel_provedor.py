# Select do cérebro de voz ativo (PROVEDOR_IA) na página inicial —
# antes só existia dentro da tela de configurações
# (jarvis/pacotes/configuracoes/), junto com dezenas de outras
# variáveis de .env, difícil de achar rápido. É uma troca frequente o
# bastante pra merecer atalho direto na tela principal.
#
# ESCREVE no .env com a MESMA técnica de
# jarvis/pacotes/configuracoes/env_io.py (set_key atualiza uma variável
# sem tocar no resto do arquivo) — copiada, não importada, porque
# aquele módulo é escopado deliberadamente só pra tela de
# configurações (ver o comentário no topo dele). A LEITURA, essa sim,
# vem de jarvis/nucleo/config.py::provedor_ativo(), que é a mesma
# função que o resto do app usa para decidir o cérebro — duplicar a
# leitura foi justamente o que deixou este select desatualizado.
#
# A troca não precisa reiniciar o app: jarvis/nucleo/config.py::
# provedor_ativo() relê o .env do disco a cada chamada, e
# jarvis/ui/janela_principal.py::_classe_do_worker() só é chamado no
# início de cada chamada — então o valor novo já vale na PRÓXIMA
# chamada, nunca no meio de uma que já está em andamento.
from dotenv import set_key

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QWidget

from jarvis.caminhos import CAMINHO_ENV
from jarvis.nucleo.config import OPCOES_PROVEDOR, provedor_ativo

# IMPORTADAS, nunca copiadas. Este arquivo já teve a própria cópia com
# dois itens, e o comentário dela dizia que existia justamente "pra não
# virar uma segunda fonte de verdade divergente" — mas quando o
# terceiro cérebro (servidor local) entrou, ele foi acrescentado só na
# lista de jarvis/nucleo/config.py e este select seguiu oferecendo dois,
# sem nenhum erro visível. Duas listas que "devem" ser iguais divergem;
# uma lista não tem como divergir.
OPCOES = list(OPCOES_PROVEDOR)


def _ler_provedor_atual():
    # provedor_ativo() já lê o .env do disco a cada chamada e já
    # devolve "gemini" para qualquer valor não reconhecido — era essa
    # regra que este arquivo reimplementava à mão, com a lista de
    # válidos também desatualizada.
    return provedor_ativo()


def _salvar_provedor(valor):
    CAMINHO_ENV.touch(exist_ok=True)

    set_key(
        str(CAMINHO_ENV),
        "PROVEDOR_IA",
        valor,
        quote_mode="never",
    )


class PainelProvedor(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self._montar()

    def _montar(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        rotulo = QLabel("Cérebro")
        rotulo.setObjectName("statusTitulo")

        self.combo = QComboBox()
        self.combo.setObjectName("comboDispositivo")
        self.combo.setCursor(Qt.CursorShape.PointingHandCursor)

        # Mesmo ajuste de tamanho de jarvis/ui/painel_dispositivos.py —
        # a cor base vem do ESTILO_GLOBAL por cascata (este painel é
        # filho de MainWindow), só o tamanho é local.
        self.combo.setStyleSheet(
            "QComboBox#comboDispositivo {"
            "    min-height: 0px;"
            "    padding: 4px 8px;"
            "    font-size: 10px;"
            "}"
        )

        atual = _ler_provedor_atual()
        indice_selecionado = 0

        for indice, (valor, rotulo_opcao) in enumerate(OPCOES):
            self.combo.addItem(rotulo_opcao, valor)

            if valor == atual:
                indice_selecionado = indice

        self.combo.setCurrentIndex(indice_selecionado)

        layout.addWidget(rotulo)
        layout.addWidget(self.combo, 1)

        # Conectado DEPOIS de setCurrentIndex acima, então montar o
        # painel nunca dispara uma escrita no .env sozinho.
        self.combo.currentIndexChanged.connect(self._ao_trocar)

    def _ao_trocar(self, _indice):
        valor = self.combo.currentData()

        try:
            _salvar_provedor(valor)

        except OSError as erro:
            print(
                f"[PROVEDOR] Não consegui salvar no .env: {erro}"
            )

            return

        print(
            f"[PROVEDOR] Cérebro de voz: {valor} "
            "(vale já na próxima chamada, chamadas em andamento "
            "não são afetadas)."
        )
