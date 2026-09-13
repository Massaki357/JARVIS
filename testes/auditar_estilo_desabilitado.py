import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

sys.stdout = io.TextIOWrapper(
    sys.stdout.buffer, encoding="utf-8", errors="replace"
)

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTextEdit,
    QWidget,
)

TIPOS_INTERATIVOS = (
    QPushButton,
    QComboBox,
    QLineEdit,
    QTextEdit,
    QListWidget,
)


def imagem_bytes(widget):
    imagem = widget.grab().toImage()

    if imagem.isNull():
        return None, 0, 0

    bits = imagem.constBits()

    if bits is None:
        return None, 0, 0

    return bits.tobytes(), imagem.width(), imagem.height()


def auditar_janela(janela, nome_janela, app, achados, inconclusivos):
    janela.show()
    app.processEvents()

    total = 0

    for widget in janela.findChildren(QWidget):
        if not isinstance(widget, TIPOS_INTERATIVOS):
            continue

        if widget.width() < 2 or widget.height() < 2:
            continue

        if (
            widget.testAttribute(Qt.WA_TransparentForMouseEvents)
            and widget.focusPolicy() == Qt.NoFocus
        ):
            continue

        nome_objeto = widget.objectName() or "(sem objectName)"
        estava_habilitado = widget.isEnabled()

        widget.clearFocus()

        widget.setEnabled(True)
        app.processEvents()
        antes, largura, altura = imagem_bytes(widget)

        app.processEvents()
        controle, _lc, _ac = imagem_bytes(widget)

        widget.setEnabled(False)
        app.processEvents()
        depois, _l, _a = imagem_bytes(widget)

        widget.setEnabled(estava_habilitado)
        app.processEvents()

        if antes is None or depois is None or controle is None:
            continue

        total += 1

        identificacao = (
            nome_janela,
            f"{type(widget).__name__}#{nome_objeto}",
            f"{largura}x{altura}",
        )

        if antes != controle:
            inconclusivos.append(identificacao)
            continue

        if antes == depois:
            achados.append(identificacao)

    return total


def auditar_estado_encerrando(janela_principal, app, achados):
    botao = janela_principal.btn_chamada

    botao.clearFocus()
    app.processEvents()

    def repintar(valor):
        botao.setProperty("encerrando", valor)
        botao.style().unpolish(botao)
        botao.style().polish(botao)
        app.processEvents()

    repintar(False)
    normal, _l, _a = imagem_bytes(botao)

    repintar(True)
    encerrando, _l2, _a2 = imagem_bytes(botao)

    repintar(False)

    if normal is not None and normal == encerrando:
        achados.append(
            (
                "janela_principal",
                'QPushButton#botaoChamada[encerrando="true"]',
                "propriedade dinâmica sem efeito visual",
            )
        )

    return 1


def main():
    app = QApplication.instance() or QApplication(sys.argv)

    achados = []
    inconclusivos = []
    total_geral = 0

    from jarvis.ui.janela_principal import MainWindow
    from jarvis.ui.janela_perfil import JanelaPerfil
    from jarvis.ui.janela_chat import ChatWindow
    from jarvis.ui.janela_envio_arquivo import EnvioArquivoWindow

    principal = MainWindow()

    janelas = [
        (principal, "janela_principal (+ painéis)"),
        (JanelaPerfil(), "janela_perfil"),
        (ChatWindow(obter_worker_ativo=lambda: None), "janela_chat"),
        (
            EnvioArquivoWindow(obter_worker_ativo=lambda: None),
            "janela_envio_arquivo",
        ),
    ]

    from unittest.mock import patch

    with patch(
        "jarvis.ui.janela_camera.abrir_camera_compartilhada",
        return_value=False,
    ):
        from jarvis.ui.janela_camera import JanelaCamera

        janelas.append((JanelaCamera(), "janela_camera"))

    try:
        from jarvis.pacotes.configuracoes.window import (
            ConfiguracoesWindow,
        )

        janelas.append((ConfiguracoesWindow(), "configuracoes/window"))

    except Exception as erro:
        print(f"(configuracoes/window não pôde ser construída: {erro})")

    for janela, nome in janelas:
        antes_achados = len(achados)
        antes_inconclusivos = len(inconclusivos)

        total = auditar_janela(
            janela, nome, app, achados, inconclusivos
        )
        total_geral += total

        problemas = (
            len(achados)
            - antes_achados
            + len(inconclusivos)
            - antes_inconclusivos
        )

        print(
            f"{'!! ' if problemas else '   '}{nome}: {total} widget(s) "
            f"auditado(s), {problemas} problema(s)"
        )

    total_geral += auditar_estado_encerrando(principal, app, achados)

    print()

    if achados:
        print("SEM EFEITO VISUAL AO DESABILITAR:")
        for nome_janela, alvo, detalhe in achados:
            print(f"  - {nome_janela}: {alvo} ({detalhe})")

    if inconclusivos:
        print("INCONCLUSIVOS (a própria medição ficou instável):")
        for nome_janela, alvo, detalhe in inconclusivos:
            print(f"  - {nome_janela}: {alvo} ({detalhe})")

    if not achados and not inconclusivos:
        print(
            "Todo widget interativo muda de aparência ao ser "
            "desabilitado."
        )

    print()
    print(
        f"{total_geral} verificação(ões), {len(achados)} falha(s), "
        f"{len(inconclusivos)} inconclusiva(s)."
    )

    for janela, _nome in janelas:
        try:
            if hasattr(janela, "encerramento_manual"):
                janela.encerramento_manual = True

            janela.close()

        except Exception:
            pass

    return 1 if (achados or inconclusivos) else 0


if __name__ == "__main__":
    sys.exit(main())
