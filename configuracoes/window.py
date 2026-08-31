# Janela de configurações — mostra e permite editar as variáveis do
# .env, agrupadas por pacote. Cada pacote descreve seus próprios
# campos via config_schema() (ver configuracoes/pacotes.py); esta
# janela não conhece o nome de nenhuma variável de antemão.
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from . import env_io
from .pacotes import PACOTES_COM_CONFIG


# Uma linha de campo: rótulo + QLineEdit. Para campos sensíveis,
# adiciona um botão "Mostrar"/"Ocultar" ao lado — o campo começa
# mascarado (EchoMode.Password) por padrão.
class _CampoConfig:

    def __init__(self, entrada, valor_atual):
        self.nome = entrada["nome"]
        self.sensivel = bool(entrada.get("sensivel", False))
        self.valor_original = valor_atual or ""

        self.campo = QLineEdit(self.valor_original)

        if self.sensivel:
            self.campo.setEchoMode(QLineEdit.EchoMode.Password)

        self.widget_linha = QWidget()
        layout_linha = QHBoxLayout(self.widget_linha)
        layout_linha.setContentsMargins(0, 0, 0, 0)
        layout_linha.addWidget(self.campo)

        if self.sensivel:
            botao_mostrar = QPushButton("Mostrar")
            botao_mostrar.setCheckable(True)
            botao_mostrar.setFixedWidth(80)
            botao_mostrar.toggled.connect(self._alternar_visibilidade)
            layout_linha.addWidget(botao_mostrar)

    def _alternar_visibilidade(self, mostrar):
        self.campo.setEchoMode(
            QLineEdit.EchoMode.Normal
            if mostrar
            else QLineEdit.EchoMode.Password
        )

    def valor_alterado(self):
        return self.campo.text() != self.valor_original

    def valor_atual(self):
        return self.campo.text()


class ConfiguracoesWindow(QWidget):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Configurações do jarvis")
        self.resize(560, 640)

        self._campos = []

        layout_principal = QVBoxLayout(self)

        aviso = QLabel(
            "Estes valores vêm e vão direto para o arquivo .env. "
            "Campos em branco significam que a variável ainda não "
            "está definida.\n"
            "Algumas mudanças só valem depois de reiniciar o jarvis "
            "— pacotes que já abriram uma conexão nesta sessão (ex: "
            "MQTT da Rede Jarvis) não recarregam a configuração "
            "sozinhos."
        )
        aviso.setWordWrap(True)
        aviso.setStyleSheet("color: #a05a00; padding: 4px;")
        layout_principal.addWidget(aviso)

        area_rolagem = QScrollArea()
        area_rolagem.setWidgetResizable(True)
        layout_principal.addWidget(area_rolagem)

        conteudo = QWidget()
        layout_conteudo = QVBoxLayout(conteudo)
        area_rolagem.setWidget(conteudo)

        valores_atuais = env_io.ler_valores()

        for rotulo_secao, modulo_config in PACOTES_COM_CONFIG:
            grupo = self._montar_secao(
                rotulo_secao, modulo_config, valores_atuais
            )
            layout_conteudo.addWidget(grupo)

        layout_conteudo.addStretch()

        botao_salvar = QPushButton("Salvar")
        botao_salvar.clicked.connect(self._salvar)
        layout_principal.addWidget(
            botao_salvar, alignment=Qt.AlignmentFlag.AlignRight
        )

    def _montar_secao(self, rotulo_secao, modulo_config, valores_atuais):
        grupo = QGroupBox(rotulo_secao)
        formulario = QFormLayout(grupo)

        schema = modulo_config.config_schema()

        for entrada in schema:
            campo = _CampoConfig(
                entrada, valores_atuais.get(entrada["nome"])
            )
            self._campos.append(campo)

            rotulo_campo = entrada.get("rotulo", entrada["nome"])

            if entrada.get("obrigatoria"):
                rotulo_campo += " *"

            formulario.addRow(rotulo_campo, campo.widget_linha)

        return grupo

    def _salvar(self):
        campos_alterados = [c for c in self._campos if c.valor_alterado()]

        if not campos_alterados:
            QMessageBox.information(
                self,
                "Configurações",
                "Nenhum campo foi alterado.",
            )
            self.close()
            return

        try:
            for campo in campos_alterados:
                env_io.salvar_valor(campo.nome, campo.valor_atual())

        except OSError as erro:
            QMessageBox.critical(
                self,
                "Configurações",
                f"Falha ao salvar o .env: {erro}",
            )
            return

        QMessageBox.information(
            self,
            "Configurações",
            f"{len(campos_alterados)} variável(is) salva(s) no .env.\n"
            "Algumas mudanças só valem depois de reiniciar o jarvis.",
        )

        self.close()
