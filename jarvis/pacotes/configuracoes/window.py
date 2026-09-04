# Janela de configurações — mostra e permite editar as variáveis do
# .env, agrupadas por pacote. Cada pacote descreve seus próprios
# campos via config_schema() (ver jarvis/pacotes/configuracoes/pacotes.py); esta
# janela não conhece o nome de nenhuma variável de antemão.
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
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


# Seção recolhível de uma categoria de configuração — substitui o
# QGroupBox simples de antes. Com muitos pacotes registrados, a tela
# de configurações virou uma lista longa demais pra achar um campo
# específico; agora cada categoria começa FECHADA, e um clique no
# cabeçalho abre só aquela (as outras continuam como estavam).
class _SecaoRecolhivel(QWidget):

    def __init__(self, titulo, parent=None):
        super().__init__(parent)

        self._titulo_base = titulo

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(0)

        # O próprio texto do botão carrega o indicador de estado (▸
        # fechado / ▾ aberto) — mais simples que desenhar uma seta à
        # parte, e já dá o feedback visual de clique do QPushButton
        # (estado "pressionado" quando checked=True).
        self.botao_titulo = QPushButton()
        self.botao_titulo.setCheckable(True)
        self.botao_titulo.setChecked(False)
        self.botao_titulo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.botao_titulo.setStyleSheet(
            "QPushButton {"
            "    text-align: left;"
            "    padding: 8px 10px;"
            "    font-weight: 600;"
            "    border: 1px solid #999999;"
            "    border-radius: 3px;"
            "}"
            "QPushButton:checked {"
            "    border-bottom-left-radius: 0px;"
            "    border-bottom-right-radius: 0px;"
            "}"
        )
        self.botao_titulo.clicked.connect(self._alternar)

        # Conteúdo (o formulário com os campos da categoria) — começa
        # invisível, exatamente como o botão começa desmarcado.
        self.conteudo = QWidget()
        self.conteudo.setVisible(False)
        self.conteudo.setStyleSheet(
            "border: 1px solid #999999; border-top: none;"
        )

        self.layout_conteudo = QFormLayout(self.conteudo)
        self.layout_conteudo.setContentsMargins(12, 10, 12, 10)

        layout.addWidget(self.botao_titulo)
        layout.addWidget(self.conteudo)

        self._atualizar_texto_botao()

    def _alternar(self):
        aberto = self.botao_titulo.isChecked()

        self.conteudo.setVisible(aberto)

        self._atualizar_texto_botao()

    def _atualizar_texto_botao(self):
        seta = "▾" if self.botao_titulo.isChecked() else "▸"

        self.botao_titulo.setText(
            f"{seta}  {self._titulo_base}"
        )

    def form(self):
        return self.layout_conteudo


# Uma linha de campo. Duas variantes, conforme a entrada do schema:
#
# - "opcoes" presente: campo de SELEÇÃO (QComboBox) — pra variáveis
#   com um conjunto fixo e conhecido de valores válidos (ex:
#   PROVEDOR_IA), em vez de texto livre onde um erro de digitação
#   passaria despercebido até o app já estar rodando com o valor
#   errado. Cada opção é (valor_salvo_no_env, rótulo_exibido).
# - Caso contrário: QLineEdit, como sempre foi — campos sensíveis
#   ganham um botão "Mostrar"/"Ocultar" ao lado, começando mascarados
#   (EchoMode.Password).
class _CampoConfig:

    def __init__(self, entrada, valor_atual):
        self.nome = entrada["nome"]
        self.sensivel = bool(entrada.get("sensivel", False))
        self.opcoes = entrada.get("opcoes")
        self.valor_original = valor_atual or ""

        self.widget_linha = QWidget()
        layout_linha = QHBoxLayout(self.widget_linha)
        layout_linha.setContentsMargins(0, 0, 0, 0)

        if self.opcoes:
            self.campo = QComboBox()

            valor_normalizado = self.valor_original.strip().lower()
            indice_selecionado = 0

            for indice, (valor, rotulo) in enumerate(self.opcoes):
                self.campo.addItem(rotulo, valor)

                if valor.strip().lower() == valor_normalizado:
                    indice_selecionado = indice

            self.campo.setCurrentIndex(indice_selecionado)

            layout_linha.addWidget(self.campo)

            return

        self.campo = QLineEdit(self.valor_original)

        if self.sensivel:
            self.campo.setEchoMode(QLineEdit.EchoMode.Password)

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

    # O valor "original" de um campo de opções é normalizado contra
    # a própria lista de opções antes de comparar — assim, um .env
    # com "Gemini" (maiúscula) ou em branco não aparece como
    # "alterado" só porque o usuário deixou o combo na opção que já
    # equivalia ao valor real (mesma normalização de
    # config.PROVEDOR_IA: .strip().lower()).
    def _valor_original_normalizado(self):
        if not self.opcoes:
            return self.valor_original

        valor_normalizado = self.valor_original.strip().lower()

        for valor, _rotulo in self.opcoes:
            if valor.strip().lower() == valor_normalizado:
                return valor

        return self.opcoes[0][0]

    def valor_alterado(self):
        return self.valor_atual() != self._valor_original_normalizado()

    def valor_atual(self):
        if self.opcoes:
            return self.campo.currentData()

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
        secao = _SecaoRecolhivel(rotulo_secao)
        formulario = secao.form()

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

        return secao

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
