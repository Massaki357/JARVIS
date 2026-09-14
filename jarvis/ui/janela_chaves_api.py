from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from jarvis.nucleo import chaves_api
from jarvis.ui.estilo import ESTILO_GLOBAL, TEXTO_SECUNDARIO


class _CampoChave(QWidget):
    def __init__(self, nome, parent=None):
        super().__init__(parent)

        self.nome = nome
        titulo, ajuda = chaves_api.DESCRICOES.get(nome, (nome, ""))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 10)
        layout.setSpacing(4)

        rotulo = QLabel(f"{titulo} ({nome})")
        rotulo.setWordWrap(True)
        rotulo.setStyleSheet("font-weight: 600;")
        layout.addWidget(rotulo)

        if ajuda:
            texto_ajuda = QLabel(ajuda)
            texto_ajuda.setWordWrap(True)
            texto_ajuda.setStyleSheet(f"color: {TEXTO_SECUNDARIO};")
            layout.addWidget(texto_ajuda)

        linha = QHBoxLayout()

        # Valor sensível nunca aparece fora deste campo mascarado (CLAUDE.md).
        self.campo = QLineEdit()
        self.campo.setEchoMode(QLineEdit.EchoMode.Password)
        self.campo.setPlaceholderText("Cole a chave aqui")
        linha.addWidget(self.campo)

        botao_mostrar = QPushButton("Mostrar")
        botao_mostrar.setCheckable(True)
        botao_mostrar.setFixedWidth(90)
        botao_mostrar.toggled.connect(self._alternar_visibilidade)
        linha.addWidget(botao_mostrar)

        layout.addLayout(linha)

    def _alternar_visibilidade(self, mostrar):
        self.campo.setEchoMode(
            QLineEdit.EchoMode.Normal
            if mostrar
            else QLineEdit.EchoMode.Password
        )

    def valor(self):
        return self.campo.text().strip()


class JanelaChavesApi(QDialog):
    def __init__(self, faltando, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Chaves de API faltando")
        self.setStyleSheet(ESTILO_GLOBAL)
        self.setMinimumWidth(520)

        self.salvas = {}
        self.campos = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)

        aviso = QLabel(
            "Para o funcionamento básico, estas chaves de API precisam "
            "estar no arquivo .env e ainda não estão. Preencha e salve "
            "para continuar."
        )
        aviso.setWordWrap(True)
        aviso.setStyleSheet("padding-bottom: 12px;")
        layout.addWidget(aviso)

        for nome in faltando:
            campo = _CampoChave(nome)
            self.campos.append(campo)
            layout.addWidget(campo)

        botoes = QHBoxLayout()
        botoes.addStretch()

        botao_pular = QPushButton("Continuar sem salvar")
        botao_pular.clicked.connect(self.reject)
        botoes.addWidget(botao_pular)

        botao_salvar = QPushButton("Salvar e continuar")
        botao_salvar.setDefault(True)
        botao_salvar.clicked.connect(self._salvar)
        botoes.addWidget(botao_salvar)

        layout.addLayout(botoes)

    def _salvar(self):
        from jarvis.pacotes.configuracoes import env_io

        preenchidos = {c.nome: c.valor() for c in self.campos if c.valor()}

        if not preenchidos:
            QMessageBox.warning(
                self,
                "Chaves de API",
                "Nenhuma chave foi preenchida.",
            )
            return

        try:
            for nome, valor in preenchidos.items():
                env_io.salvar_valor(nome, valor)

        except OSError as erro:
            QMessageBox.critical(
                self,
                "Chaves de API",
                f"Não consegui gravar o .env: {erro}",
            )
            return

        self.salvas = preenchidos
        self.accept()


def garantir_chaves_api():
    faltando = chaves_api.chaves_faltando()

    if not faltando:
        return []

    print(
        "[CHAVES] Faltando no .env para o funcionamento básico: "
        + ", ".join(faltando)
    )

    janela = JanelaChavesApi(faltando)
    janela.setWindowModality(Qt.WindowModality.ApplicationModal)
    janela.exec()

    if janela.salvas:
        chaves_api.aplicar_no_processo(janela.salvas)

        print(
            "[CHAVES] Gravadas no .env: " + ", ".join(sorted(janela.salvas))
        )

    return chaves_api.chaves_faltando()
