from dotenv import set_key

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QWidget

from jarvis.caminhos import CAMINHO_ENV
from jarvis.nucleo.config import OPCOES_PROVEDOR, provedor_ativo

OPCOES = list(OPCOES_PROVEDOR)


def _ler_provedor_atual():
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
