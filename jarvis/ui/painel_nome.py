from dotenv import dotenv_values, set_key

from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QWidget

from jarvis.caminhos import CAMINHO_ENV

NOME_PADRAO = "ALFRED"

LIMITE_CARACTERES = 30


def _ler_nome_atual():
    if not CAMINHO_ENV.exists():
        return NOME_PADRAO

    valores = dotenv_values(CAMINHO_ENV)

    return (valores.get("NOME_JARVIS") or NOME_PADRAO).strip() or NOME_PADRAO


def _salvar_nome(nome):
    CAMINHO_ENV.touch(exist_ok=True)

    set_key(
        str(CAMINHO_ENV),
        "NOME_JARVIS",
        nome,
        quote_mode="never",
    )


class PainelNome(QWidget):
    def __init__(self, ao_alterar=None, parent=None):
        super().__init__(parent)

        self._ao_alterar = ao_alterar

        self._ultimo_valor_salvo = _ler_nome_atual()

        self._montar()

    def _montar(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        rotulo = QLabel("Nome")
        rotulo.setObjectName("statusTitulo")

        self.campo = QLineEdit(self._ultimo_valor_salvo)
        self.campo.setPlaceholderText(NOME_PADRAO)
        self.campo.setMaxLength(LIMITE_CARACTERES)

        layout.addWidget(rotulo)
        layout.addWidget(self.campo, 1)

        self.campo.editingFinished.connect(self._ao_terminar_edicao)

    def _ao_terminar_edicao(self):
        nome = self.campo.text().strip() or NOME_PADRAO

        self.campo.setText(nome)

        if nome == self._ultimo_valor_salvo:
            return

        try:
            _salvar_nome(nome)

        except OSError as erro:
            print(
                f"[NOME] Não consegui salvar no .env: {erro}"
            )

            return

        self._ultimo_valor_salvo = nome

        print(
            f"[NOME] Nome de identidade: {nome} "
            "(já atualizado na tela e válido já na próxima chamada)."
        )

        if self._ao_alterar:
            self._ao_alterar(nome)
