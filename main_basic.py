
# Ativar o ambiente virtual:
# .\venv\Scripts\Activate.ps1

# [CURSO] sys fornece acesso aos argumentos da linha de comando
# [CURSO] e também é utilizado para encerrar corretamente a aplicação.
import sys

# [CURSO] QApplication é o núcleo de qualquer aplicação Qt.
# [CURSO] Ela cria o loop principal responsável pela interface gráfica.
from PySide6.QtWidgets import QApplication

# [CURSO] Importa a janela principal da versão básica do ALFRED.
# [CURSO] Toda a interface será criada por essa classe.
from ui.main_window_basic import MainWindow


# [CURSO] Função principal da aplicação.
# [CURSO] Ela inicializa o Qt, cria a janela e inicia o loop de eventos.
def main():

    # [CURSO] Cria a aplicação Qt.
    # [CURSO] sys.argv permite que o Qt receba argumentos
    # [CURSO] passados pela linha de comando, quando existirem.
    app = QApplication(sys.argv)

    # [CURSO] Cria uma instância da janela principal.
    window = MainWindow()

    # [CURSO] Torna a janela visível para o usuário.
    window.show()

    # [CURSO] Inicia o loop de eventos do Qt.
    # [CURSO] A aplicação permanecerá aberta até que a janela seja fechada.
    # [CURSO] sys.exit garante que o código de encerramento
    # [CURSO] seja devolvido corretamente ao sistema operacional.
    sys.exit(app.exec())


# [CURSO] Este bloco garante que a função main()
# [CURSO] seja executada somente quando este arquivo
# [CURSO] for iniciado diretamente.
# [CURSO] Caso ele seja apenas importado por outro módulo,
# [CURSO] a função não será executada automaticamente.
if __name__ == "__main__":
    main()