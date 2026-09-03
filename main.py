# Ativar o ambiente virtual:
# .\venv\Scripts\Activate.ps1

# [CURSO] sys fornece acesso aos argumentos da linha de comando
# [CURSO] e permite finalizar corretamente a aplicação.
import sys

# [CURSO] qInstallMessageHandler permite interceptar mensagens internas do Qt.
# [CURSO] Neste projeto ele é usado para ocultar apenas um aviso conhecido de DPI.
from PySide6.QtCore import qInstallMessageHandler

# [CURSO] QApplication é o núcleo de qualquer aplicação Qt.
# [CURSO] Ela controla o loop de eventos da interface.
from PySide6.QtWidgets import QApplication

# [CURSO] Importa a janela principal da versão futurista.
from ui.main_window import MainWindow


# [CURSO] Esta função recebe todas as mensagens emitidas pelo Qt.
# [CURSO] O objetivo é esconder apenas um aviso específico,
# [CURSO] mantendo todos os demais avisos e erros visíveis.
def filtro_mensagens_qt(
    tipo,
    contexto,
    mensagem,
):
    """
    Oculta somente o aviso conhecido de DPI do Qt no Windows.
    Outros avisos e erros continuam aparecendo normalmente.
    """

    # [CURSO] Garante que a mensagem seja tratada como texto.
    mensagem = str(
        mensagem
    )

    # [CURSO] Se a mensagem for exatamente o aviso conhecido de DPI,
    # [CURSO] simplesmente encerramos a função sem exibi-la.
    if (
        "SetProcessDpiAwarenessContext() failed"
        in mensagem
    ):
        return

    # [CURSO] Todas as demais mensagens continuam sendo enviadas
    # [CURSO] normalmente para a saída de erro do terminal.
    sys.stderr.write(
        mensagem + "\n"
    )


# [CURSO] Função principal da aplicação.
def main():
    # [CURSO] Instala o filtro ANTES da criação do QApplication.
    # [CURSO] Assim qualquer mensagem emitida pelo Qt já passará
    # [CURSO] por este filtro desde o início.
    qInstallMessageHandler(
        filtro_mensagens_qt
    )

    # [CURSO] Cria a aplicação Qt.
    app = QApplication(
        sys.argv
    )

    # [CURSO] Cria a janela principal.
    window = MainWindow()

    # [CURSO] Exibe a janela na tela.
    window.show()

    # [CURSO] Inicia o loop de eventos do Qt.
    # [CURSO] A aplicação permanece executando até o usuário fechá-la.
    sys.exit(
        app.exec()
    )


# [CURSO] Este bloco garante que a função main()
# [CURSO] seja executada apenas quando este arquivo
# [CURSO] for iniciado diretamente.
if __name__ == "__main__":
    main()