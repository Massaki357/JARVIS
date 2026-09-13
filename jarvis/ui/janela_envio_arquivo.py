import mimetypes
from pathlib import Path

from pypdf import PdfReader

from jarvis.nucleo import prompts

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from jarvis.ui import estilo
from jarvis.ui.estilo import ESTILO_GLOBAL

_EXTENSOES_TEXTO = {".txt", ".md", ".csv", ".json", ".log"}

_LIMITE_CARACTERES_TEXTO = 12000


def processar_arquivo_para_sessao(caminho, worker):
    if worker is None:
        return False, (
            "Não há nenhuma chamada de voz ativa agora — inicie uma "
            "chamada antes de enviar um arquivo."
        )

    caminho = Path(caminho)

    if not caminho.is_file():
        return False, f"Arquivo não encontrado: {caminho}"

    tipo_mime, _codificacao = mimetypes.guess_type(str(caminho))

    if tipo_mime in ("image/jpeg", "image/png"):
        return _enviar_imagem(worker, caminho, tipo_mime)

    if tipo_mime == "application/pdf" or caminho.suffix.lower() == ".pdf":
        return _enviar_pdf(worker, caminho)

    if caminho.suffix.lower() in _EXTENSOES_TEXTO:
        return _enviar_texto_puro(worker, caminho)

    return False, (
        f"Formato de arquivo '{caminho.suffix or '(sem extensão)'}' "
        "ainda não é suportado pra envio como contexto — só imagens "
        "(JPEG/PNG), PDF e arquivos de texto (.txt, .md, .csv, "
        ".json, .log)."
    )


def _enviar_imagem(worker, caminho, tipo_mime):
    try:
        imagem_bytes = caminho.read_bytes()

    except OSError as erro:
        return False, f"Falha ao ler a imagem '{caminho.name}': {erro}"

    enviado = worker.enviar_imagem_da_ui(
        imagem_bytes,
        tipo_mime,
        texto_contexto=prompts.CONTEXTO_IMAGEM_ENVIADA.format(
            nome=caminho.name
        ),
    )

    if not enviado:
        return False, (
            "Não foi possível enviar a imagem — a chamada de voz "
            "não está mais ativa."
        )

    return True, f"Imagem '{caminho.name}' enviada como contexto da conversa."


def _enviar_pdf(worker, caminho):
    try:
        leitor = PdfReader(str(caminho))

        texto_extraido = "\n".join(
            pagina.extract_text() or ""
            for pagina in leitor.pages
        )

    except Exception as erro:
        return False, f"Falha ao ler o PDF '{caminho.name}': {erro}"

    if not texto_extraido.strip():
        return False, (
            f"Não consegui extrair texto do PDF '{caminho.name}' "
            "(pode ser um PDF de páginas escaneadas/imagens, sem "
            "texto selecionável)."
        )

    return _enviar_texto_como_contexto(worker, caminho.name, texto_extraido)


def _enviar_texto_puro(worker, caminho):
    try:
        texto_extraido = caminho.read_text(
            encoding="utf-8",
            errors="replace",
        )

    except OSError as erro:
        return False, f"Falha ao ler o arquivo '{caminho.name}': {erro}"

    return _enviar_texto_como_contexto(worker, caminho.name, texto_extraido)


def _enviar_texto_como_contexto(worker, nome_arquivo, texto_extraido):
    texto_truncado = texto_extraido[:_LIMITE_CARACTERES_TEXTO]

    aviso_truncamento = (
        " (texto truncado — o arquivo é maior que o limite enviado)"
        if len(texto_extraido) > _LIMITE_CARACTERES_TEXTO
        else ""
    )

    enviado = worker.enviar_texto_da_ui(
        prompts.CONTEXTO_ARQUIVO_ENVIADO.format(
            nome_arquivo=nome_arquivo,
            aviso_truncamento=aviso_truncamento,
            texto_truncado=texto_truncado,
        )
    )

    if not enviado:
        return False, (
            "Não foi possível enviar o arquivo — a chamada de voz "
            "não está mais ativa."
        )

    return True, (
        f"Arquivo '{nome_arquivo}' enviado como contexto da conversa "
        "(texto extraído)."
    )


class EnvioArquivoWindow(QWidget):
    def __init__(self, obter_worker_ativo, ao_fechar=None):
        super().__init__()

        self._obter_worker_ativo = obter_worker_ativo
        self._ao_fechar = ao_fechar

        self.setWindowTitle("Enviar arquivo para o jarvis")
        self.resize(420, 240)
        self.setAcceptDrops(True)
        self.setStyleSheet(ESTILO_GLOBAL)

        layout = QVBoxLayout(self)

        self._rotulo = QLabel(
            "Arraste um arquivo aqui, ou use o botão abaixo.\n\n"
            "Suportado: imagens (JPEG/PNG), PDF e arquivos de "
            "texto.\n\nA janela fecha sozinha assim que o arquivo "
            "for enviado."
        )
        self._rotulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._rotulo.setWordWrap(True)

        self._rotulo.setStyleSheet(
            f"color: {estilo.TEXTO_SECUNDARIO};"
            f"background-color: {estilo.FUNDO_PAINEL};"
            f"border: 2px dashed {estilo.BORDA};"
            "border-radius: 8px;"
            "padding: 24px;"
        )
        layout.addWidget(self._rotulo, stretch=1)

        botao_selecionar = QPushButton("Selecionar arquivo...")
        botao_selecionar.clicked.connect(self._selecionar_arquivo)
        layout.addWidget(botao_selecionar)

    def closeEvent(self, event):
        if self._ao_fechar:
            self._ao_fechar()

        super().closeEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()

        if not urls:
            return

        self._processar(urls[0].toLocalFile())

    def _selecionar_arquivo(self):
        caminho, _filtro = QFileDialog.getOpenFileName(
            self,
            "Selecionar arquivo para enviar",
        )

        if caminho:
            self._processar(caminho)

    def _processar(self, caminho):
        sucesso, mensagem = processar_arquivo_para_sessao(
            caminho,
            self._obter_worker_ativo(),
        )

        if sucesso:
            self.close()
            return

        QMessageBox.warning(
            self,
            "Envio de arquivo",
            mensagem,
        )
