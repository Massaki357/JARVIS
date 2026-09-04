# Select do cérebro de voz ativo (PROVEDOR_IA: "gemini" ou "openai") na
# página inicial — antes só existia dentro da tela de configurações
# (jarvis/pacotes/configuracoes/), junto com dezenas de outras
# variáveis de .env, difícil de achar rápido. É uma troca frequente o
# bastante pra merecer atalho direto na tela principal.
#
# Lê/escreve o .env com a MESMA técnica de
# jarvis/pacotes/configuracoes/env_io.py (dotenv_values só lê, set_key
# atualiza uma variável sem tocar no resto do arquivo) — copiada, não
# importada, porque aquele módulo é escopado deliberadamente só pra
# tela de configurações (ver o comentário no topo dele). Mesmo
# princípio de duplicação por módulo já usado em outros pares deste
# projeto (ex: jarvis/pacotes/admin_terminal/notificacoes.py copia,
# não importa, jarvis/pacotes/rede_jarvis/notificacoes.py).
#
# A troca não precisa reiniciar o app: jarvis/nucleo/config.py::
# usar_provedor_openai() relê o .env do disco a cada chamada, e
# jarvis/ui/janela_principal.py::_classe_do_worker() só é chamado no
# início de cada chamada — então o valor novo já vale na PRÓXIMA
# chamada, nunca no meio de uma que já está em andamento.
from dotenv import dotenv_values, set_key

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QWidget

from jarvis.caminhos import CAMINHO_ENV

# Mesmas duas opções — e na mesma ordem — que
# jarvis/nucleo/config.py::config_schema() já expõe pra tela de
# configurações, pra não virar uma segunda fonte de verdade divergente
# sobre quais valores são válidos.
OPCOES = [
    ("gemini", "Gemini"),
    ("openai", "OpenAI"),
]


def _ler_provedor_atual():
    if not CAMINHO_ENV.exists():
        return "gemini"

    valores = dotenv_values(CAMINHO_ENV)
    valor = (valores.get("PROVEDOR_IA") or "gemini").strip().lower()

    # Mesma regra de segurança de usar_provedor_openai(): qualquer
    # valor que não seja um dos dois reconhecidos cai no Gemini, nunca
    # tenta adivinhar.
    return valor if valor in ("gemini", "openai") else "gemini"


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
