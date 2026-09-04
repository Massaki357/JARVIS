# Auditoria de estilo: todo widget interativo do app tem que MUDAR de
# aparência ao ser desabilitado.
#
# Como rodar (com o venv ativo, na raiz do projeto):
#
#     python testes/auditar_estilo_desabilitado.py
#
# Sai com código 1 se achar qualquer widget que não muda, ou qualquer
# medição inconclusiva. Nenhuma dependência além do que o app já usa.
#
# A CLASSE DE BUG QUE ISTO EXISTE PRA PEGAR
# =========================================
#
# jarvis/ui/estilo.py sobrescreve a aparência padrão do sistema para
# quase todo widget. O visual de "desabilitado" que o Windows daria de
# graça vai junto — então, se o QSS não define explicitamente a
# variante :disabled daquele widget, ele fica IDÊNTICO habilitado e
# desabilitado, e o usuário só descobre que não pode clicar tentando.
#
# Isso aconteceu de verdade duas vezes, por dois motivos diferentes:
#
# 1. ESPECIFICIDADE. Um seletor de ID (QPushButton#botaoNav) é mais
#    específico que a pseudo-classe :disabled num seletor de tipo
#    (QPushButton:disabled). Ter a regra genérica no arquivo não basta:
#    ela não alcança nenhum widget com objectName estilizado. Cada um
#    precisa da sua "#id:disabled".
# 2. AUSÊNCIA. QTextEdit, QLineEdit e QComboBox simplesmente não
#    tinham regra :disabled nenhuma no projeto inteiro.
#
# POR QUE MEDIR PIXEL, E NÃO LER O QSS
# ====================================
#
# Um teste que procurasse a string "#botaoNav:disabled" dentro de
# estilo.py provaria só que alguém escreveu aquela linha — não que ela
# vence a cascata, não que ela alcança o widget certo, e não pegaria
# um widget estilizado no próprio arquivo dele (painel_console.py,
# painel_dispositivos.py, painel_provedor.py estilizam a si mesmos, e
# a regra deles vence a global). Renderizar os dois estados e comparar
# os bytes responde a pergunta que interessa: o usuário vê diferença?
#
# A MEDIDA DE CONTROLE NÃO É OPCIONAL
# ===================================
#
# Habilitar/desabilitar um widget pode mover o foco para um irmão, e
# foco muda a borda neste app. Isso já produziu um falso negativo
# real: o #registro apareceu numa rodada e sumiu na seguinte. Por isso
# cada widget é medido três vezes — habilitado, habilitado de novo
# (controle) e desabilitado. Se os dois primeiros já diferem, a
# medição é INCONCLUSIVA e falha, nunca "passa".
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

sys.stdout = io.TextIOWrapper(
    sys.stdout.buffer, encoding="utf-8", errors="replace"
)

from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTextEdit,
    QWidget,
)

# Tipos com que o usuário interage e que, portanto, têm um estado
# desabilitado perceptível. QLabel fica de fora de propósito: não é
# interativo, e o app não desabilita rótulo.
#
# QListWidget entrou depois das outras, e por um motivo concreto: a
# lista de ferramentas da tela de perfil pinta cada item com
# setForeground, e cor por item VENCE o QSS — a regra
# QListWidget:disabled não apagava aquele vermelho, e a lista travada
# ficava idêntica à editável. É a mesma família de bug com uma origem
# a mais (cor por item, não só especificidade de seletor).
TIPOS_INTERATIVOS = (
    QPushButton,
    QComboBox,
    QLineEdit,
    QTextEdit,
    QListWidget,
)


def imagem_bytes(widget):
    """
    Bytes do widget renderizado, ou None quando o Qt não consegue
    rasterizar (widget dentro de uma seção recolhida, por exemplo) —
    nesse caso ele é pulado, nunca comparado com lixo.
    """
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

        # Widget interno criado pelo próprio Qt (o popup do QComboBox,
        # por exemplo) não é widget do app.
        if widget.width() < 2 or widget.height() < 2:
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
    """
    O botão de chamada tem um SEGUNDO estado visual, que não é
    :disabled: a propriedade dinâmica encerrando="true"
    (jarvis/ui/janela_principal.py). Propriedade dinâmica em QSS só
    reaplica depois de unpolish/polish — esquecer isso faz o botão
    trocar de texto e não trocar de cor. Mesma família de bug, então é
    medida aqui do mesmo jeito.
    """
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
        # MainWindow carrega PainelConsole, PainelDispositivos,
        # PainelNome e PainelProvedor como filhos — os quatro entram
        # nesta varredura junto com ela.
        (principal, "janela_principal (+ painéis)"),
        (JanelaPerfil(), "janela_perfil"),
        (ChatWindow(obter_worker_ativo=lambda: None), "janela_chat"),
        (
            EnvioArquivoWindow(obter_worker_ativo=lambda: None),
            "janela_envio_arquivo",
        ),
    ]

    # JanelaCamera: a webcam é neutralizada de propósito. A janela só
    # precisa ser construída e desenhada, nunca filmar nada — abrir o
    # dispositivo de verdade num teste roubaria a câmera de quem
    # estivesse usando.
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
            # MainWindow encerra a chamada no closeEvent; marcar como
            # encerramento manual evita a reconexão automática.
            if hasattr(janela, "encerramento_manual"):
                janela.encerramento_manual = True

            janela.close()

        except Exception:
            pass

    return 1 if (achados or inconclusivos) else 0


if __name__ == "__main__":
    sys.exit(main())
